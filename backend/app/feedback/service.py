"""Message Feedback rules. A Visitor gives one thumbs up or down, with an optional comment, on
an Agent reply in their own Conversation; giving it again replaces it, and removing deletes it.
The feedback takes the reply's Agent Version when written."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, Message, MessageRole
from app.feedback.models import MessageFeedback, Thumb


class ReplyNotFoundError(Exception):
    """No Agent reply with that ID in the Conversation."""


@dataclass(frozen=True)
class Feedback:
    rating: Thumb
    comment: str | None


async def _reply(
    session: AsyncSession, conversation: Conversation, message_id: uuid.UUID
) -> Message:
    message = await session.scalar(
        select(Message).where(
            Message.id == message_id,
            Message.conversation_id == conversation.id,
            Message.role == MessageRole.ASSISTANT,
        )
    )
    if message is None:
        raise ReplyNotFoundError
    return message


async def give(
    session: AsyncSession,
    conversation: Conversation,
    message_id: uuid.UUID,
    feedback: Feedback,
    *,
    now: datetime,
) -> Feedback:
    """Gives (or replaces) the feedback on the Conversation's reply ``message_id``."""
    message = await _reply(session, conversation, message_id)
    values = {
        "rating": feedback.rating.value,
        "comment": feedback.comment,
        "agent_version_id": message.agent_version_id,
        "updated_at": now,
    }
    await session.execute(
        insert(MessageFeedback)
        .values(
            id=uuid.uuid4(),
            organisation_id=message.organisation_id,
            message_id=message.id,
            **values,
        )
        .on_conflict_do_update(index_elements=[MessageFeedback.message_id], set_=values)
    )
    await session.commit()
    return feedback


async def remove(session: AsyncSession, conversation: Conversation, message_id: uuid.UUID) -> None:
    """Removes the feedback on the Conversation's reply ``message_id``, if there is any."""
    message = await _reply(session, conversation, message_id)
    await session.execute(delete(MessageFeedback).where(MessageFeedback.message_id == message.id))
    await session.commit()


async def feedback_on(
    session: AsyncSession, message_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, MessageFeedback]:
    """The feedback on each of the Messages that has some, by Message ID."""
    rows = await session.scalars(
        select(MessageFeedback).where(MessageFeedback.message_id.in_(list(message_ids)))
    )
    return {row.message_id: row for row in rows}
