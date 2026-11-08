"""The ``usage_daily`` rollup, run hourly by Beat.

Each run recomputes the current UTC day (its rollup is partial until the day is over) and
finalises every day before it that isn't final yet, for each Organisation: normally just the
previous day, but days a stopped Beat missed are caught up too. A final day is never recomputed
by later runs. Every day's rollup is recomputed from the raw tables in full and replaces what
was there, so running twice gives the same rollups (idempotent). After the rollup, each Agent's
block rate is checked for a spike (``app.analytics.alerts``)."""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, exists, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analytics.alerts import check_block_rates
from app.analytics.models import UsageDaily, UsageRollupState
from app.analytics.usage import Only, day_bounds, usage_on
from app.conversations.models import Conversation, Message, MessageRole
from app.mail.port import Mailer

# Serialises concurrent runs (an hourly run overlapping a slow one, or a manual run).
_LOCK_KEY = 707_04


async def _recompute(session: AsyncSession, day: date) -> None:
    """Replaces the day's rollup rows of every Organisation whose day isn't final."""
    final = exists().where(
        UsageRollupState.organisation_id == UsageDaily.organisation_id,
        UsageRollupState.finalised_through >= day,
    )
    await session.execute(delete(UsageDaily).where(UsageDaily.day == day, ~final))
    usage = await usage_on(session, day, Only(unfinalised=True))
    session.add_all(
        entry.usage.row(entry.organisation_id, entry.agent_id, version_id, day)
        for version_id, entry in usage.items()
    )
    await session.flush()


async def _pending(session: AsyncSession, today: date) -> dict[uuid.UUID, date]:
    """Each Organisation with Visitor replies on days before ``today`` that aren't final: the
    first such day."""
    start, _ = day_bounds(today)
    finalised = (
        select(UsageRollupState.finalised_through)
        .where(UsageRollupState.organisation_id == Message.organisation_id)
        .scalar_subquery()
    )
    after = func.coalesce(finalised + 1, date.min)
    first_day = func.min(func.timezone("UTC", Message.created_at))
    rows = await session.execute(
        select(Message.organisation_id, first_day)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Message.role == MessageRole.ASSISTANT,
            Message.agent_version_id.is_not(None),
            Conversation.is_playground.is_(False),
            Message.created_at < start,
            func.timezone("UTC", Message.created_at) >= after,
        )
        .group_by(Message.organisation_id)
    )
    return {organisation_id: first.date() for organisation_id, first in rows}


async def roll_up(
    sessionmaker: async_sessionmaker[AsyncSession],
    at: datetime,
    *,
    mailer: Mailer,
    studio_url: str,
) -> None:
    """Rolls usage up as of ``at``: finalises the days before its UTC day that aren't final,
    then recomputes its day. Then checks every Agent's block rate for a spike (the Block rate
    alert), emailing Owners through ``mailer``."""
    today = at.astimezone(UTC).date()
    yesterday = today - timedelta(days=1)
    async with sessionmaker() as session, session.begin():
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _LOCK_KEY})
        pending = await _pending(session, today)
        day = min(pending.values(), default=today)
        while day <= yesterday:
            await _recompute(session, day)
            day += timedelta(days=1)
        for organisation_id in pending:
            await session.execute(
                insert(UsageRollupState)
                .values(
                    organisation_id=organisation_id, finalised_through=yesterday, finalised_at=at
                )
                .on_conflict_do_update(
                    index_elements=[UsageRollupState.organisation_id],
                    set_={"finalised_through": yesterday, "finalised_at": at},
                )
            )
        await _recompute(session, today)
    async with sessionmaker() as session:
        await check_block_rates(session, at, mailer=mailer, studio_url=studio_url)
