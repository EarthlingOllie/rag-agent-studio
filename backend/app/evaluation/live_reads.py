"""Reading Live Verdicts for other modules: the failed ones of an Agent Version in a time range
(the evidence of a Suggestion run, spec 16), and the Live Verdicts of given Messages."""

import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Message
from app.evaluation.models import LiveStatus, LiveVerdict


@dataclass(frozen=True)
class FailedReplies:
    # The most recent first, at most the limit asked for.
    replies: list[tuple[Message, LiveVerdict]]
    # How many there are in all.
    total: int


async def failed_replies(
    session: AsyncSession,
    agent_version_id: uuid.UUID,
    start: datetime,
    end: datetime,
    *,
    limit: int,
) -> FailedReplies:
    """The Agent Version's Visitor replies given from ``start`` up to ``end`` whose Live Verdict
    was judged and failed, leaving out Purged ones."""
    where = (
        LiveVerdict.agent_version_id == agent_version_id,
        LiveVerdict.status == LiveStatus.JUDGED,
        LiveVerdict.passed.is_(False),
        Message.created_at >= start,
        Message.created_at < end,
        Message.purged_at.is_(None),
    )
    joined = select(Message, LiveVerdict).join(LiveVerdict, LiveVerdict.message_id == Message.id)
    rows = await session.execute(
        joined.where(*where).order_by(Message.created_at.desc(), Message.seq.desc()).limit(limit)
    )
    total = await session.scalar(
        select(func.count())
        .select_from(Message)
        .join(LiveVerdict, LiveVerdict.message_id == Message.id)
        .where(*where)
    )
    return FailedReplies([(message, verdict) for message, verdict in rows.all()], total or 0)


async def live_verdicts_of(
    session: AsyncSession, message_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, LiveVerdict]:
    """The Live Verdict of each of the Messages that has one, by Message."""
    verdicts = await session.scalars(
        select(LiveVerdict).where(LiveVerdict.message_id.in_(message_ids))
    )
    return {verdict.message_id: verdict for verdict in verdicts}
