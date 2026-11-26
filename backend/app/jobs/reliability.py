"""Job reliability (ADR-0020): the claim, the heartbeat and the sweeper.

The database row is the record that a job must run; the broker's message only wakes a worker.

- **The claim.** A job takes its row with one conditional update: the row is queued, or in
  progress with a stale heartbeat. The update marks it in progress under a new claim, so a
  second message for the same row, or a second copy of the job, can't claim it and exits.
- **The heartbeat.** While a job holds its claim, a background task writes the time to its row
  every ``heartbeat_seconds``, whatever the job is busy with (conversion runs in a thread, model
  calls await), so a live job is never mistaken for a dead one.
- **Holding the claim.** The job's final write, and any step that settles its row, first checks
  the row still carries its claim (``holds``): a copy that was given up for dead and replaced
  can't write over the copy that replaced it.
- **The sweeper.** Every minute (and once when a worker starts), under an advisory lock so two
  sweeps never overlap: rows queued for longer than ``queued_too_long``, or waiting for an
  automatic retry whose time has passed (the row records when it is due, so a retry whose
  message was lost still happens), are sent again, and rows in progress with no heartbeat for
  ``dead_after`` are handed to their job type's policy (for ingestion: back to queued, and sent
  again). Each recovery is recorded in the traces.

A job type supplies only its policy (``JobPolicy``): which tables hold its rows, what their
queued and in-progress statuses are, what to do with a stale row and how to send the job again.
Job code never reads the heartbeat columns itself.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

import logfire
from sqlalchemy import ColumnElement, and_, false, or_, select, text, true, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import Clock
from app.core.settings import Settings

# The key of the sweeper's Postgres advisory lock (an arbitrary constant: "sweep" in ASCII).
SWEEPER_LOCK_KEY = 0x7377656570

QUEUED_TOO_LONG = "queued too long"
RETRY_DUE = "retry due"
NO_HEARTBEAT = "no heartbeat"


@dataclass(frozen=True)
class Timings:
    """How often a heartbeat is written, and how long before a job counts as dead or as queued
    for too long."""

    heartbeat_seconds: float = 30.0
    dead_after: timedelta = timedelta(minutes=5)
    queued_too_long: timedelta = timedelta(minutes=15)

    @classmethod
    def from_settings(cls, settings: Settings) -> "Timings":
        return cls(
            heartbeat_seconds=settings.job_heartbeat_seconds,
            dead_after=timedelta(seconds=settings.job_dead_after_seconds),
            queued_too_long=timedelta(seconds=settings.job_queued_too_long_seconds),
        )


class JobRow(Protocol):
    """The columns a table of job rows has: its status, when it was last queued, the claim that
    holds it and that claim's last heartbeat."""

    status: Any
    queued_at: Any
    claim_id: Any
    heartbeat_at: Any


@dataclass(frozen=True)
class JobTable:
    """A table whose rows are jobs: its mapped class, the column that identifies a row, and the
    statuses that mean queued and in progress. A job type that retries automatically names the
    column that records when a queued row's next attempt is due (``retry_at``). A job whose stale
    rows are never restarted (a paid job, which its policy ends instead) claims queued rows only
    (``reclaims_stale``). A job type whose rows go stale by other rules overrides ``stale_rows``
    and ``overdue_rows``, and names its reason for the traces.

    A job type whose rows have one status for both (a Re-embed is ``running`` throughout) gives
    it as both: the claim then tells them apart, a row without one being queued. One whose rows
    move through several in-progress statuses (a Suggestion run's phases) claims into the first
    and overrides ``_in_progress`` to take them all."""

    model: type[Any]
    key: Any
    queued: str
    in_progress: str
    retry_at: Any = None
    reclaims_stale: bool = True
    stale_reason: str = NO_HEARTBEAT

    def stale_rows(self, now: datetime, timings: Timings) -> ColumnElement[bool]:
        """The rows the sweeper hands to the policy's ``recover``: by default, in progress with
        no heartbeat for ``dead_after``."""
        return self._stale(now - timings.dead_after)

    def overdue_rows(self, now: datetime, timings: Timings) -> ColumnElement[bool]:
        """The rows the sweeper sends again as they are: by default, queued for longer than
        ``queued_too_long``, or waiting for an automatic retry that is due."""
        return self._overdue(now, timings.queued_too_long)

    def _queued(self) -> ColumnElement[bool]:
        status: ColumnElement[bool] = self.model.status == self.queued
        if self.queued == self.in_progress:
            return and_(status, self.model.claim_id.is_(None))
        return status

    def _in_progress(self) -> ColumnElement[bool]:
        status: ColumnElement[bool] = self.model.status == self.in_progress
        if self.queued == self.in_progress:
            return and_(status, self.model.claim_id.is_not(None))
        return status

    def _stale(self, before: datetime) -> ColumnElement[bool]:
        model = self.model
        return and_(
            self._in_progress(),
            or_(model.heartbeat_at.is_(None), model.heartbeat_at < before),
        )

    def _retry_due(self, now: datetime) -> ColumnElement[bool]:
        """A queued row whose automatic retry is due and hasn't been sent since it fell due."""
        if self.retry_at is None:
            return false()
        model = self.model
        return and_(
            self.retry_at.is_not(None),
            self.retry_at <= now,
            or_(model.queued_at.is_(None), model.queued_at < self.retry_at),
        )

    def _overdue(self, now: datetime, queued_too_long: timedelta) -> ColumnElement[bool]:
        """A queued row to send again: its retry is due, or it has been queued too long (and
        isn't waiting for a retry that isn't due yet)."""
        model = self.model
        waited = or_(model.queued_at.is_(None), model.queued_at < now - queued_too_long)
        not_waiting = (
            true() if self.retry_at is None else or_(self.retry_at.is_(None), self.retry_at <= now)
        )
        return and_(
            self._queued(),
            or_(self._retry_due(now), and_(waited, not_waiting)),
        )


@dataclass(frozen=True)
class Claim:
    """A job's hold on its row, from a successful ``claim`` until the row is settled."""

    table: JobTable
    row_id: uuid.UUID
    claim_id: uuid.UUID


async def claim(
    session: AsyncSession,
    table: JobTable,
    row_id: uuid.UUID,
    *,
    now: datetime,
    dead_after: timedelta,
    values: dict[str, Any] | None = None,
) -> Claim | None:
    """Claims the row with one conditional update, in the caller's transaction: a queued row, or
    (when the table ``reclaims_stale``) an in-progress one whose heartbeat is older than
    ``dead_after``. It becomes in progress under a new claim, with ``values`` set too (such as an
    attempt count). ``None`` if the row isn't there or another job holds it; the job then exits
    without doing anything."""
    claim_id = uuid.uuid4()
    model = table.model
    claimable = table._queued()
    if table.reclaims_stale:
        claimable = or_(claimable, table._stale(now - dead_after))
    claimed = await session.scalar(
        update(model)
        .where(table.key == row_id, claimable)
        .values(status=table.in_progress, claim_id=claim_id, heartbeat_at=now, **(values or {}))
        .returning(table.key)
        .execution_options(synchronize_session=False)
    )
    return None if claimed is None else Claim(table, row_id, claim_id)


def holding(found: Claim) -> ColumnElement[bool]:
    """The condition that the claim's row still carries it."""
    return and_(
        found.table.key == found.row_id,
        found.table.model.claim_id == found.claim_id,
        found.table._in_progress(),
    )


async def holds(session: AsyncSession, found: Claim) -> bool:
    """Whether the job still holds its claim, locking its row until the caller's transaction
    ends, so the final write or settle step that follows is made under the claim."""
    held = await session.scalar(select(found.table.key).where(holding(found)).with_for_update())
    return held is not None


def queued_values(now: datetime) -> dict[str, Any]:
    """What a row put back on queued carries: when it was queued, and no claim."""
    return {"queued_at": now, "claim_id": None, "heartbeat_at": None}


def released(row: JobRow) -> None:
    """Clears the claim columns of a row the job has just settled (finished or failed)."""
    row.claim_id = None
    row.heartbeat_at = None


async def beat(session: AsyncSession, found: Claim, now: datetime) -> None:
    """Writes a heartbeat in the caller's transaction, if the row still carries the claim (a copy
    given up for dead and replaced changes nothing): for a job that also beats as it commits
    each step."""
    await session.execute(
        update(found.table.model)
        .where(holding(found))
        .values(heartbeat_at=now)
        .execution_options(synchronize_session=False)
    )


async def _beat(sessionmaker: async_sessionmaker[AsyncSession], found: Claim, clock: Clock) -> None:
    async with sessionmaker() as session, session.begin():
        await beat(session, found, clock.now())


@asynccontextmanager
async def heartbeat(
    sessionmaker: async_sessionmaker[AsyncSession],
    found: Claim,
    clock: Clock,
    interval_seconds: float,
) -> AsyncIterator[None]:
    """Writes the claim's heartbeat every ``interval_seconds`` while the block runs, in a
    background task on the job's event loop. If writing a beat fails, the beats stop and the
    sweeper later takes the job for dead, which is safe: it is restarted, and this copy loses
    its claim."""

    async def beat() -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            await _beat(sessionmaker, found, clock)

    task = asyncio.create_task(beat())
    try:
        yield
    finally:
        task.cancel()


class JobPolicy(Protocol):
    """What one job type tells the sweeper."""

    @property
    def job(self) -> str:
        """The job's name, for the traces (its task name)."""
        ...

    @property
    def tables(self) -> Sequence[JobTable]:
        """The tables its rows are in."""
        ...

    async def recover(
        self, session: AsyncSession, table: JobTable, row_id: uuid.UUID, now: datetime
    ) -> None:
        """Deals with a row in progress whose heartbeat stopped, in the sweeper's transaction.
        The sweeper sends the job again once that commits: if the row is queued again, the job
        restarts; if not, the message finds nothing to claim and does nothing."""
        ...

    async def resend(self, row_id: uuid.UUID) -> None:
        """Sends the job for the row again."""
        ...


@dataclass(frozen=True)
class Recovery:
    job: str
    row_id: uuid.UUID
    reason: str


def _record(recovery: Recovery) -> None:
    logfire.info(
        "Sweeper recovered {job} {job_id}: {reason}",
        job=recovery.job,
        job_id=str(recovery.row_id),
        reason=recovery.reason,
    )


async def _sweep_policy(
    session: AsyncSession, policy: JobPolicy, now: datetime, timings: Timings
) -> tuple[list[Recovery], list[uuid.UUID]]:
    recoveries: list[Recovery] = []
    to_send: list[uuid.UUID] = []
    for table in policy.tables:
        stale = (
            await session.scalars(
                select(table.key)
                .where(table.stale_rows(now, timings))
                .with_for_update(skip_locked=True)
            )
        ).all()
        for row_id in stale:
            recoveries.append(Recovery(policy.job, row_id, table.stale_reason))
            await policy.recover(session, table, row_id, now)
            to_send.append(row_id)
        overdue = (
            await session.execute(
                select(table.key, table._retry_due(now))
                .where(table.overdue_rows(now, timings))
                .with_for_update(skip_locked=True)
            )
        ).all()
        if overdue:
            await session.execute(
                update(table.model)
                .where(table.key.in_([row_id for row_id, _ in overdue]))
                .values(queued_at=now)
                .execution_options(synchronize_session=False)
            )
        for row_id, retry_due in overdue:
            recoveries.append(
                Recovery(policy.job, row_id, RETRY_DUE if retry_due else QUEUED_TOO_LONG)
            )
            to_send.append(row_id)
    return recoveries, list(dict.fromkeys(to_send))


async def sweep(
    sessionmaker: async_sessionmaker[AsyncSession],
    policies: Sequence[JobPolicy],
    *,
    now: datetime,
    timings: Timings,
) -> list[Recovery] | None:
    """One sweep over every job type. ``None`` if another sweep holds the lock; otherwise the
    recoveries made. Rows are changed and committed before their jobs are sent again, so a job
    sent again always finds its row queued."""
    async with sessionmaker() as locked:
        acquired = await locked.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": SWEEPER_LOCK_KEY}
        )
        if not acquired:
            await locked.rollback()
            return None
        try:
            recoveries: list[Recovery] = []
            sends: list[tuple[JobPolicy, uuid.UUID]] = []
            for policy in policies:
                async with sessionmaker() as session, session.begin():
                    found, to_send = await _sweep_policy(session, policy, now, timings)
                recoveries.extend(found)
                sends.extend((policy, row_id) for row_id in to_send)
            for recovery in recoveries:
                _record(recovery)
            for policy, row_id in sends:
                await policy.resend(row_id)
            return recoveries
        finally:
            await locked.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": SWEEPER_LOCK_KEY})
            await locked.commit()
