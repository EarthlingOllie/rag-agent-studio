"""Reading Live Verdicts for the Conversations viewer (spec 15): which Conversations to keep by
their replies' Live Verdicts, and how many of each Conversation's replies failed theirs.

The Conversations module filters and counts through these, so the Live Verdict table stays this
module's own.
"""

import enum
import uuid

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
