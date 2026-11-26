"""Live Verdicts as a job type of the job reliability module (``app.jobs.reliability``, ADR-0020).

A Live Verdict is Pending from when its reply is chosen until a copy of its job settles it, and
the job is under two minutes (the judge times out first), so no heartbeat is needed: one still
Pending ``live_verdict_pending_seconds`` after its job was sent had its job lost, or its worker
died. The sweeper then sends the job again, clearing the dead copy's claim so the new copy can
claim it, up to ``live_verdict_resends`` times; one still Pending after that is an Error, which
the Live score leaves out. Re-sending never judges twice: the job claims the verdict before it
asks the judge, and stores the outcome and its spend in one conditional update
(``app.evaluation.live``).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, and_, false, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import load_settings
from app.evaluation.models import LiveStatus, LiveVerdict
from app.jobs.reliability import JobTable, Timings
from app.worker.celery_app import LIVE_VERDICT_TASK
from app.worker.publisher import current_publisher

PENDING_TOO_LONG = "pending too long"

LOST = (
    "Judging was lost and sent again without finishing; this reply is left out of the Live score."
)


@dataclass(frozen=True)
class LiveVerdictRows(JobTable):
    """Live Verdicts: stale once Pending for ``pending_for`` since their job was last sent
    (since they were created, until the sweeper sends it again); never merely overdue."""

    pending_for: timedelta = timedelta(minutes=5)

    def stale_rows(self, now: datetime, timings: Timings) -> ColumnElement[bool]:
        return and_(
            LiveVerdict.status == LiveStatus.PENDING,
            func.coalesce(LiveVerdict.queued_at, LiveVerdict.created_at) <= now - self.pending_for,
        )

    def overdue_rows(self, now: datetime, timings: Timings) -> ColumnElement[bool]:
        return false()


class LiveVerdictPolicy:
    """What the sweeper does with Live Verdicts."""

    job = LIVE_VERDICT_TASK

    @property
    def tables(self) -> Sequence[JobTable]:
        pending_for = timedelta(seconds=load_settings().live_verdict_pending_seconds)
        return (
            LiveVerdictRows(
                LiveVerdict,
                LiveVerdict.id,
                queued=LiveStatus.PENDING,
                in_progress=LiveStatus.PENDING,
                stale_reason=PENDING_TOO_LONG,
                pending_for=pending_for,
            ),
        )

    async def recover(
        self, session: AsyncSession, table: JobTable, row_id: uuid.UUID, now: datetime
    ) -> None:
        """Sent again while it has re-sends left, with the dead copy's claim cleared; otherwise
        an Error, and the message the sweeper sends finds nothing to judge."""
        resends = (
            await session.execute(select(LiveVerdict.resends).where(LiveVerdict.id == row_id))
        ).scalar_one()
        if resends < load_settings().live_verdict_resends:
            values: dict[str, object] = {
                "resends": LiveVerdict.resends + 1,
                "queued_at": now,
                "claim_id": None,
            }
        else:
            values = {"status": LiveStatus.ERROR, "error_reason": LOST}
        await session.execute(
            update(LiveVerdict)
            .where(LiveVerdict.id == row_id)
            .values(**values)
            .execution_options(synchronize_session=False)
        )

    async def resend(self, row_id: uuid.UUID) -> None:
        await current_publisher().judge_live_verdict(row_id)


LIVE_VERDICTS = LiveVerdictPolicy()
