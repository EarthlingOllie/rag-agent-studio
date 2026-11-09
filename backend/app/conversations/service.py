"""Reading a Project's Conversations for the Studio's Conversations viewer: Visitor
Conversations (from the widget) and Playground ones (flagged), filtered by Agent, start date,
Agent Version, Playground, Message Feedback, Conversation Rating and Guardrail outcome, and
one Conversation's Messages and each reply's Trace.

Everything is found through the Project, which is found through the Organisation scope, so a
Conversation of another Project or Organisation is simply not found.
"""

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent, AgentVersion
from app.conversations.models import Conversation, Message, MessageRetrieval, MessageRole
from app.documents.models import Chunk, Document
from app.feedback.models import (
    ConversationRating,
    ConversationRatingChange,
    MessageFeedback,
    Thumb,
)
from app.feedback.service import feedback_on, rating_changes, rating_of
from app.projects.service import get_project
from app.tenancy.repository import OrganisationScope

PREVIEW_MAX = 120


class FeedbackFilter(enum.StrEnum):
    """Which Conversations to keep by their Message Feedback: with a thumbs up, with a thumbs
    down, with any feedback, or with none."""

    UP = "up"
    DOWN = "down"
    ANY = "any"
    NONE = "none"


def _with_feedback(rating: Thumb | None = None) -> ColumnElement[bool]:
    given = select(Message.conversation_id).join(
        MessageFeedback, MessageFeedback.message_id == Message.id
    )
    if rating is not None:
        given = given.where(MessageFeedback.rating == rating)
    return Conversation.id.in_(given)


class RatingFilter(enum.StrEnum):
    """Which Conversations to keep by their Conversation Rating: one score (1 to 5), rated
    (any score), or not rated."""

    ONE = "1"
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    ANY = "any"
    NONE = "none"


def _rated(score: int | None = None) -> ColumnElement[bool]:
    rated = select(ConversationRating.conversation_id).where(ConversationRating.score.is_not(None))
    if score is not None:
        rated = rated.where(ConversationRating.score == score)
    return Conversation.id.in_(rated)


class GuardrailFilter(enum.StrEnum):
    """Which Conversations to keep by their replies' Guardrail outcomes: with a reply whose
    Guardrail took this action (blocked, flagged, logged, replaced or allowed), with any
    Guardrail outcome, or with none."""

    BLOCKED = "blocked"
    FLAGGED = "flagged"
    LOGGED = "logged"
    REPLACED = "replaced"
    ALLOWED = "allowed"
    ANY = "any"
    NONE = "none"


def _has_guardrail_outcome() -> ColumnElement[bool]:
    return func.jsonb_array_length(Message.guardrail_outcomes) > 0


def _with_guardrail_outcome(action: str | None = None) -> ColumnElement[bool]:
    condition = (
        _has_guardrail_outcome()
        if action is None
        else Message.guardrail_outcomes.contains([{"action": action}])
    )
    return Conversation.id.in_(select(Message.conversation_id).where(condition))


class ConversationNotFoundError(Exception):
    """No Conversation with that ID in the Project."""


class MessageNotFoundError(Exception):
    """No Agent reply with that ID in the Conversation."""


@dataclass(frozen=True)
class ConversationFilter:
    """Which Conversations to list. ``start`` and ``end`` bound when the Conversation started
    (``end`` exclusive); ``version_id`` keeps those with a reply from that Agent Version;
    ``playground`` keeps only Playground (True) or only Visitor (False) Conversations;
    ``feedback`` keeps them by their Message Feedback; ``rating`` by their current
    Conversation Rating; ``guardrail`` by their replies' Guardrail outcomes."""

    agent_id: uuid.UUID | None = None
    version_id: uuid.UUID | None = None
    start: datetime | None = None
    end: datetime | None = None
    playground: bool | None = None
    feedback: FeedbackFilter | None = None
    rating: RatingFilter | None = None
    guardrail: GuardrailFilter | None = None

    def conditions(self) -> list[ColumnElement[bool]]:
        found: list[ColumnElement[bool]] = []
        if self.agent_id is not None:
            found.append(Conversation.agent_id == self.agent_id)
        if self.version_id is not None:
            found.append(
                Conversation.id.in_(
                    select(Message.conversation_id).where(
                        Message.agent_version_id == self.version_id
                    )
                )
            )
        if self.start is not None:
            found.append(Conversation.created_at >= self.start)
        if self.end is not None:
            found.append(Conversation.created_at < self.end)
        if self.playground is not None:
            found.append(Conversation.is_playground.is_(self.playground))
        if self.feedback in (FeedbackFilter.UP, FeedbackFilter.DOWN):
            found.append(_with_feedback(Thumb(self.feedback.value)))
        elif self.feedback is FeedbackFilter.ANY:
            found.append(_with_feedback())
        elif self.feedback is FeedbackFilter.NONE:
            found.append(~_with_feedback())
        if self.rating is RatingFilter.ANY:
            found.append(_rated())
        elif self.rating is RatingFilter.NONE:
            found.append(~_rated())
        elif self.rating is not None:
            found.append(_rated(int(self.rating.value)))
        if self.guardrail is GuardrailFilter.ANY:
            found.append(_with_guardrail_outcome())
        elif self.guardrail is GuardrailFilter.NONE:
            found.append(~_with_guardrail_outcome())
        elif self.guardrail is not None:
            found.append(_with_guardrail_outcome(self.guardrail.value))
        return found


@dataclass(frozen=True)
class ConversationSummary:
    conversation: Conversation
    agent_name: str
    message_count: int
    # The Visitor's (or Editor's) first question, cut to ``PREVIEW_MAX`` characters; None once
    # its text is purged.
    preview: str | None
    # The Agent Versions that answered, in order; empty for a Playground Conversation.
    version_numbers: list[int]
    # How many of its replies have a thumbs up, and a thumbs down.
    thumbs_up: int
    thumbs_down: int
    # Its current Conversation Rating; None when the Visitor hasn't rated it.
    rating: int | None
    # How many of its replies have a Guardrail outcome.
    guardrail_events: int


@dataclass(frozen=True)
class ConversationPage:
    rows: list[ConversationSummary]
    total: int


def _in_project(project_id: uuid.UUID, scope: OrganisationScope) -> Select[Conversation, str]:
    return (
        select(Conversation, Agent.name)
        .join(Agent, Agent.id == Conversation.agent_id)
        .where(
            Agent.project_id == project_id,
            Conversation.organisation_id == scope.organisation_id,
        )
    )


async def list_conversations(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    where: ConversationFilter,
    *,
    page: int,
    size: int,
) -> ConversationPage:
    """The Project's Conversations matching ``where``, newest first, one page of them."""
    project = await get_project(session, scope, project_id)
    query = _in_project(project.id, scope).where(*where.conditions())
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    found = (
        await session.execute(
            query.order_by(Conversation.created_at.desc(), Conversation.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
    ).all()
    ids = [conversation.id for conversation, _ in found]
    counts: dict[uuid.UUID, int] = dict(
        (
            await session.execute(
                select(Message.conversation_id, func.count())
                .where(Message.conversation_id.in_(ids))
                .group_by(Message.conversation_id)
            )
        ).all()
    )
    # The first question, unless its text has been purged.
    previews: dict[uuid.UUID, str] = {
        conversation_id: preview
        for conversation_id, preview, purged_at in await session.execute(
            select(
                Message.conversation_id,
                func.left(Message.content, PREVIEW_MAX),
                Message.purged_at,
            )
            .where(Message.conversation_id.in_(ids), Message.role == MessageRole.USER)
            .ext(distinct_on(Message.conversation_id))
            .order_by(Message.conversation_id, Message.seq)
        )
        if purged_at is None
    }
    numbers: dict[uuid.UUID, list[int]] = {}
    for conversation_id, number in await session.execute(
        select(Message.conversation_id, AgentVersion.number)
        .join(AgentVersion, AgentVersion.id == Message.agent_version_id)
        .where(Message.conversation_id.in_(ids))
        .distinct()
        .order_by(Message.conversation_id, AgentVersion.number)
    ):
        numbers.setdefault(conversation_id, []).append(number)
    thumbs: dict[tuple[uuid.UUID, str], int] = {
        (conversation_id, rating): count
        for conversation_id, rating, count in await session.execute(
            select(Message.conversation_id, MessageFeedback.rating, func.count())
            .join(MessageFeedback, MessageFeedback.message_id == Message.id)
            .where(Message.conversation_id.in_(ids))
            .group_by(Message.conversation_id, MessageFeedback.rating)
        )
    }
    ratings: dict[uuid.UUID, int | None] = dict(
        (
            await session.execute(
                select(ConversationRating.conversation_id, ConversationRating.score).where(
                    ConversationRating.conversation_id.in_(ids)
                )
            )
        ).all()
    )
    guardrail_events: dict[uuid.UUID, int] = dict(
        (
            await session.execute(
                select(Message.conversation_id, func.count())
                .where(Message.conversation_id.in_(ids), _has_guardrail_outcome())
                .group_by(Message.conversation_id)
            )
        ).all()
    )
    return ConversationPage(
        rows=[
            ConversationSummary(
                conversation=conversation,
                agent_name=agent_name,
                message_count=counts.get(conversation.id, 0),
                preview=previews.get(conversation.id),
                version_numbers=numbers.get(conversation.id, []),
                thumbs_up=thumbs.get((conversation.id, Thumb.UP), 0),
                thumbs_down=thumbs.get((conversation.id, Thumb.DOWN), 0),
                rating=ratings.get(conversation.id),
                guardrail_events=guardrail_events.get(conversation.id, 0),
            )
            for conversation, agent_name in found
        ],
        total=total or 0,
    )


@dataclass(frozen=True)
class ConversationRead:
    conversation: Conversation
    agent_name: str
    messages: list[Message]
    # The number of each Agent Version that answered in it, or that feedback is attributed to.
    version_numbers: dict[uuid.UUID, int]
    # The Message Feedback on its replies, by Message ID.
    feedback: dict[uuid.UUID, MessageFeedback]
    # Its Conversation Rating (with the prompt's dismissal), if either was given, and the
    # rating's change log, oldest first.
    rating: ConversationRating | None
    rating_changes: list[ConversationRatingChange]


async def get_conversation(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> ConversationRead:
    """The Project's Conversation and its Messages, oldest first."""
    project = await get_project(session, scope, project_id)
    found = (
        await session.execute(
            _in_project(project.id, scope).where(Conversation.id == conversation_id)
        )
    ).first()
    if found is None:
        raise ConversationNotFoundError
    conversation, agent_name = found
    messages = list(
        await session.scalars(
            select(Message).where(Message.conversation_id == conversation.id).order_by(Message.seq)
        )
    )
    feedback = await feedback_on(session, [m.id for m in messages])
    rating = await rating_of(session, conversation.id)
    changes = await rating_changes(session, conversation.id)
    versions = (
        {m.agent_version_id for m in messages}
        | {f.agent_version_id for f in feedback.values()}
        | {c.agent_version_id for c in changes}
    )
    numbers: dict[uuid.UUID, int] = dict(
        (
            await session.execute(
                select(AgentVersion.id, AgentVersion.number).where(AgentVersion.id.in_(versions))
            )
        ).all()
    )
    return ConversationRead(conversation, agent_name, messages, numbers, feedback, rating, changes)


@dataclass(frozen=True)
class TracedChunk:
    """A Chunk retrieval of an answer, with its Chunk's text while the Chunk still exists, and
    its Document's name: the current name while the Document exists, else the name kept when
    the answer was given (a tombstone, with ``document_deleted`` set)."""

    retrieval: MessageRetrieval
    document_name: str | None
    text: str | None

    @property
    def document_deleted(self) -> bool:
        return self.retrieval.document_id is None


async def traced_chunks(session: AsyncSession, message: Message) -> list[TracedChunk]:
    """The answer's Chunk retrievals, in Trace order."""
    rows = await session.execute(
        select(MessageRetrieval, Document.name, Chunk.text)
        .outerjoin(Chunk, Chunk.id == MessageRetrieval.chunk_id)
        .outerjoin(Document, Document.id == MessageRetrieval.document_id)
        .where(MessageRetrieval.message_id == message.id)
        .order_by(MessageRetrieval.position)
    )
    return [TracedChunk(row, name or row.document_name, text) for row, name, text in rows]


def answer_in(messages: list[Message], message_id: uuid.UUID) -> Message:
    """The Agent's answer with that ID among ``messages``; ``MessageNotFoundError`` if there is
    none (a question has no Trace)."""
    found = next(
        (m for m in messages if m.id == message_id and m.role == MessageRole.ASSISTANT), None
    )
    if found is None:
        raise MessageNotFoundError
    return found


@dataclass(frozen=True)
class TraceRead:
    message: Message
    agent_version_number: int | None
    chunks: list[TracedChunk]


async def get_trace(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
) -> TraceRead:
    """The Trace of one of the Agent's answers in the Project's Conversation."""
    read = await get_conversation(session, scope, project_id, conversation_id)
    message = answer_in(read.messages, message_id)
    number = (
        None if message.agent_version_id is None else read.version_numbers[message.agent_version_id]
    )
    return TraceRead(message, number, await traced_chunks(session, message))
