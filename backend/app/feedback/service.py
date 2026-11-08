"""Message Feedback and Conversation Rating rules.

A Visitor gives one thumbs up or down, with an optional comment, on an Agent reply in their own
Conversation; giving it again replaces it, and removing deletes it. The feedback takes the
reply's Agent Version when written.

A Visitor rates their Conversation from 1 to 5 once the Agent has replied, and can change the
rating; the first rating and each change go into the change log. A rating (and each change)
takes the Agent Version of the last reply before it when written. Dismissing the rating prompt
is saved, so the widget doesn't ask again."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, Message, MessageRole
from app.feedback.models import (
    ConversationRating,
    ConversationRatingChange,
    MessageFeedback,
    Thumb,
)


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


class NothingToRateError(Exception):
    """The Agent hasn't replied in the Conversation yet."""


@dataclass(frozen=True)
class RatingState:
    """What the widget needs: the current score (None when not rated) and whether the Visitor
    dismissed the rating prompt."""

    score: int | None
    prompt_dismissed: bool


def _state(row: ConversationRating | None) -> RatingState:
    if row is None:
        return RatingState(None, False)
    return RatingState(row.score, row.prompt_dismissed_at is not None)


async def rating_of(session: AsyncSession, conversation_id: uuid.UUID) -> ConversationRating | None:
    """The Conversation's rating row (its score and dismissal), if either was ever given."""
    return await session.scalar(
        select(ConversationRating).where(ConversationRating.conversation_id == conversation_id)
    )


async def rating_state(session: AsyncSession, conversation: Conversation) -> RatingState:
    return _state(await rating_of(session, conversation.id))


async def rate(
    session: AsyncSession, conversation: Conversation, score: int, *, now: datetime
) -> RatingState:
    """Rates the Conversation (or changes its rating), attributed to the Agent Version of its
    last reply. A new score is logged; giving the same score again changes nothing."""
    last_reply = await session.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.role == MessageRole.ASSISTANT)
        .order_by(Message.seq.desc())
        .limit(1)
    )
    if last_reply is None:
        raise NothingToRateError
    await session.execute(
        insert(ConversationRating)
        .values(
            id=uuid.uuid4(),
            organisation_id=conversation.organisation_id,
            conversation_id=conversation.id,
        )
        .on_conflict_do_nothing(index_elements=[ConversationRating.conversation_id])
    )
    row = (
        await session.scalars(
            select(ConversationRating)
            .where(ConversationRating.conversation_id == conversation.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one()
    previous = row.score
    if previous != score:
        row.score = score
        row.agent_version_id = last_reply.agent_version_id
        row.rated_at = now
        session.add(
            ConversationRatingChange(
                organisation_id=conversation.organisation_id,
                conversation_id=conversation.id,
                score=score,
                previous_score=previous,
                agent_version_id=last_reply.agent_version_id,
                changed_at=now,
            )
        )
    await session.commit()
    return _state(row)


async def dismiss_prompt(
    session: AsyncSession, conversation: Conversation, *, now: datetime
) -> None:
    """Saves that the Visitor dismissed the rating prompt."""
    await session.execute(
        insert(ConversationRating)
        .values(
            id=uuid.uuid4(),
            organisation_id=conversation.organisation_id,
            conversation_id=conversation.id,
            prompt_dismissed_at=now,
        )
        .on_conflict_do_update(
            index_elements=[ConversationRating.conversation_id],
            set_={"prompt_dismissed_at": now},
        )
    )
    await session.commit()


async def rating_changes(
    session: AsyncSession, conversation_id: uuid.UUID
) -> list[ConversationRatingChange]:
    """The Conversation's rating change log, oldest first."""
    return list(
        await session.scalars(
            select(ConversationRatingChange)
            .where(ConversationRatingChange.conversation_id == conversation_id)
            .order_by(ConversationRatingChange.seq)
        )
    )
