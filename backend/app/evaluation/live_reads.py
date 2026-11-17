"""Reading Live Verdicts for other modules: which Conversations to keep by their replies' Live
Verdicts, and how many of each Conversation's replies failed theirs (the Conversations viewer,
spec 15); the failed ones of an Agent Version in a time range (the evidence of a Suggestion run,
spec 16); and the Live Verdicts of given Messages.

The Live Verdict table stays this module's own.
"""

import enum
import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, Message, MessageRole
from app.evaluation.models import LiveStatus, LiveVerdict


class LiveVerdictFilter(enum.StrEnum):
    """Which Conversations to keep by their replies' Live Verdicts: with a reply that passed,
    failed, or couldn't be judged (an error), or with a reply that wasn't chosen to be judged.
    A reply still pending, or skipped because its text was Purged first, is none of these."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    NOT_JUDGED = "not_judged"


def _failed() -> ColumnElement[bool]:
    return (LiveVerdict.status == LiveStatus.JUDGED) & LiveVerdict.passed.is_(False)


def with_live_verdict(state: LiveVerdictFilter) -> ColumnElement[bool]:
    """Keeps the Conversations with a reply whose Live Verdict is ``state``."""
    if state is LiveVerdictFilter.NOT_JUDGED:
        unjudged = (
            select(Message.conversation_id)
            .outerjoin(LiveVerdict, LiveVerdict.message_id == Message.id)
            .where(Message.role == MessageRole.ASSISTANT, LiveVerdict.id.is_(None))
        )
        return Conversation.id.in_(unjudged)
    condition = {
        LiveVerdictFilter.PASSED: (LiveVerdict.status == LiveStatus.JUDGED)
        & LiveVerdict.passed.is_(True),
        LiveVerdictFilter.FAILED: _failed(),
        LiveVerdictFilter.ERROR: LiveVerdict.status == LiveStatus.ERROR,
    }[state]
    judged = (
        select(Message.conversation_id)
        .join(LiveVerdict, LiveVerdict.message_id == Message.id)
        .where(condition)
    )
    return Conversation.id.in_(judged)


async def failed_live_verdicts(
    session: AsyncSession, conversation_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """How many of each Conversation's replies failed their Live Verdict; a Conversation with
    none is left out."""
    return dict(
        (
            await session.execute(
                select(Message.conversation_id, func.count())
                .join(LiveVerdict, LiveVerdict.message_id == Message.id)
                .where(Message.conversation_id.in_(conversation_ids), _failed())
                .group_by(Message.conversation_id)
            )
        ).all()
    )


@dataclass(frozen=True)
class FailedReplies:
    # The most recent first, at most the limit asked for (all of them without one).
    replies: list[tuple[Message, LiveVerdict]]
    # How many there are in all.
    total: int


async def failed_replies(
    session: AsyncSession,
    agent_version_id: uuid.UUID,
    start: datetime,
    end: datetime,
    *,
    limit: int | None = None,
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
