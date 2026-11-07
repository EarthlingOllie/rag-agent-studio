"""Reading a Project's Conversations for the Studio's Conversations viewer: Visitor
Conversations (from the widget) and Playground ones (flagged), filtered by Agent, start date,
Agent Version and Playground, and one Conversation's Messages and each reply's Trace.

Everything is found through the Project, which is found through the Organisation scope, so a
Conversation of another Project or Organisation is simply not found.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent, AgentVersion
from app.conversations.models import Conversation, Message, MessageRetrieval, MessageRole
from app.documents.models import Chunk, Document
from app.projects.service import get_project
from app.tenancy.repository import OrganisationScope

PREVIEW_MAX = 120


class ConversationNotFoundError(Exception):
    """No Conversation with that ID in the Project."""


class MessageNotFoundError(Exception):
    """No Agent reply with that ID in the Conversation."""


@dataclass(frozen=True)
class ConversationFilter:
    """Which Conversations to list. ``start`` and ``end`` bound when the Conversation started
    (``end`` exclusive); ``version_id`` keeps those with a reply from that Agent Version;
    ``playground`` keeps only Playground (True) or only Visitor (False) Conversations."""

    agent_id: uuid.UUID | None = None
    version_id: uuid.UUID | None = None
    start: datetime | None = None
    end: datetime | None = None
    playground: bool | None = None

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
        return found


@dataclass(frozen=True)
class ConversationSummary:
    conversation: Conversation
    agent_name: str
    message_count: int
    # The Visitor's (or Editor's) first question, cut to ``PREVIEW_MAX`` characters.
    preview: str | None
    # The Agent Versions that answered, in order; empty for a Playground Conversation.
    version_numbers: list[int]


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
    previews: dict[uuid.UUID, str] = dict(
        (
            await session.execute(
                select(Message.conversation_id, func.left(Message.content, PREVIEW_MAX))
                .where(Message.conversation_id.in_(ids), Message.role == MessageRole.USER)
                .ext(distinct_on(Message.conversation_id))
                .order_by(Message.conversation_id, Message.seq)
            )
        ).all()
    )
    numbers: dict[uuid.UUID, list[int]] = {}
    for conversation_id, number in await session.execute(
        select(Message.conversation_id, AgentVersion.number)
        .join(AgentVersion, AgentVersion.id == Message.agent_version_id)
        .where(Message.conversation_id.in_(ids))
        .distinct()
        .order_by(Message.conversation_id, AgentVersion.number)
    ):
        numbers.setdefault(conversation_id, []).append(number)
    return ConversationPage(
        rows=[
            ConversationSummary(
                conversation=conversation,
                agent_name=agent_name,
                message_count=counts.get(conversation.id, 0),
                preview=previews.get(conversation.id),
                version_numbers=numbers.get(conversation.id, []),
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
    # The number of each Agent Version that answered in it.
    version_numbers: dict[uuid.UUID, int]


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
    numbers: dict[uuid.UUID, int] = dict(
        (
            await session.execute(
                select(AgentVersion.id, AgentVersion.number).where(
                    AgentVersion.id.in_({m.agent_version_id for m in messages})
                )
            )
        ).all()
    )
    return ConversationRead(conversation, agent_name, messages, numbers)


@dataclass(frozen=True)
class TracedChunk:
    """A Chunk retrieval of an answer, with its Chunk's text and Document's name when the
    Chunk still exists."""

    retrieval: MessageRetrieval
    document_name: str | None
    text: str | None


async def traced_chunks(session: AsyncSession, message: Message) -> list[TracedChunk]:
    """The answer's Chunk retrievals, in Trace order."""
    rows = await session.execute(
        select(MessageRetrieval, Document.name, Chunk.text)
        .outerjoin(Chunk, Chunk.id == MessageRetrieval.chunk_id)
        .outerjoin(Document, Document.id == MessageRetrieval.document_id)
        .where(MessageRetrieval.message_id == message.id)
        .order_by(MessageRetrieval.position)
    )
    return [TracedChunk(row, name, text) for row, name, text in rows]


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
