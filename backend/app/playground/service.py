"""Playground Conversations: starting one, reading it back, and answering a question with
the Agent runtime, saving the question and the answer as Messages.

A question is answered by the Organisation's Default Model through the model gateway, from
Chunks the retrieval module finds in the Agent's Project. The question is saved before the
answer streams; the answer, with its tokens, latency and cost, once the stream ends.
"""

import itertools
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.config import AgentConfig, Retrieval
from app.agents.service import get_agent
from app.conversations.models import DRAFT, Conversation, Message, MessageRetrieval, MessageRole
from app.core.clock import Clock
from app.default_model.service import CurrentDefault, read_default
from app.documents.models import Chunk, Document
from app.embeddings.port import Embedder
from app.gateway.gateway import ModelGateway
from app.pricing.service import credential_pricing, price_table
from app.pricing.table import TokenUsage, cost
from app.projects.models import Project
from app.projects.service import active_project
from app.retrieval.service import RetrievalResult, retrieve
from app.runtime.prompt import Turn
from app.runtime.runtime import CitationEvent, DoneEvent, TokenEvent, run_turn
from app.tenancy.repository import OrganisationScope


class MessageNotFoundError(Exception):
    """No answer with that ID in the Conversation."""


class ConversationNotFoundError(Exception):
    """No Playground Conversation with that ID for the Agent."""


class NoDefaultModelError(Exception):
    """The Organisation has no Default Model to answer with."""


async def start_conversation(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    now: datetime,
) -> Conversation:
    await active_project(session, scope, project_id)
    found = await get_agent(session, scope, project_id, agent_id)
    conversation = Conversation(
        organisation_id=scope.organisation_id,
        agent_id=found.agent.id,
        is_playground=True,
        last_activity_at=now,
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def get_conversation(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> tuple[Conversation, list[Message]]:
    found = await get_agent(session, scope, project_id, agent_id)
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.agent_id == found.agent.id,
            Conversation.is_playground.is_(True),
        )
    )
    if conversation is None:
        raise ConversationNotFoundError
    messages = await session.scalars(
        select(Message).where(Message.conversation_id == conversation.id).order_by(Message.seq)
    )
    return conversation, list(messages)


def _turns(messages: list[Message]) -> list[Turn]:
    """Each question with the answer that followed it; a question left unanswered is skipped."""
    return [
        Turn(question.content, answer.content)
        for question, answer in itertools.pairwise(messages)
        if (question.role, answer.role) == (MessageRole.USER, MessageRole.ASSISTANT)
    ]


@dataclass(frozen=True)
class PreparedTurn:
    """A question saved and ready to answer."""

    organisation_id: uuid.UUID
    conversation_id: uuid.UUID
    project: Project
    config: AgentConfig
    turns: list[Turn]
    question: str
    default: CurrentDefault


async def prepare_turn(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID,
    question: str,
    *,
    now: datetime,
) -> PreparedTurn:
    """Checks the question can be answered, then saves it."""
    project = await active_project(session, scope, project_id)
    found = await get_agent(session, scope, project_id, agent_id)
    conversation, messages = await get_conversation(
        session, scope, project_id, agent_id, conversation_id
    )
    default = await read_default(session, scope.organisation_id)
    if default is None:
        raise NoDefaultModelError
    session.add(
        Message(
            organisation_id=scope.organisation_id,
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=question,
        )
    )
    conversation.last_activity_at = now
    await session.commit()
    return PreparedTurn(
        organisation_id=scope.organisation_id,
        conversation_id=conversation.id,
        project=project,
        config=found.draft,
        turns=_turns(messages),
        question=question,
        default=default,
    )


def _retrievals(
    organisation_id: uuid.UUID, message_id: uuid.UUID, done: DoneEvent
) -> list[MessageRetrieval]:
    """The answer's Trace rows: the Chunks given to the model, then those left out."""
    cited = {chunk.chunk_id for chunk in done.cited}
    rows = [
        MessageRetrieval(
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            score=c.score,
            relevance=c.relevance,
            rank=c.rank,
            cited=c.chunk_id in cited,
            excluded_reason=None,
        )
        for c in done.retrieved
    ] + [
        MessageRetrieval(
            chunk_id=e.chunk_id,
            document_id=e.document_id,
            score=e.score,
            relevance=e.relevance,
            rank=None,
            cited=False,
            excluded_reason=e.reason,
        )
        for e in done.excluded
    ]
    for position, row in enumerate(rows):
        row.organisation_id = organisation_id
        row.message_id = message_id
        row.position = position
    return rows


@dataclass(frozen=True)
class TracedChunk:
    """A Chunk retrieval of an answer, with its Chunk's text and Document's name when the
    Chunk still exists."""

    retrieval: MessageRetrieval
    document_name: str | None
    text: str | None


async def get_trace(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
) -> tuple[Message, list[TracedChunk]]:
    """An answer of the Playground Conversation and its Chunk retrievals, in Trace order."""
    _, messages = await get_conversation(session, scope, project_id, agent_id, conversation_id)
    message = next(
        (m for m in messages if m.id == message_id and m.role == MessageRole.ASSISTANT), None
    )
    if message is None:
        raise MessageNotFoundError
    rows = await session.execute(
        select(MessageRetrieval, Document.name, Chunk.text)
        .outerjoin(Chunk, Chunk.id == MessageRetrieval.chunk_id)
        .outerjoin(Document, Document.id == MessageRetrieval.document_id)
        .where(MessageRetrieval.message_id == message.id)
        .order_by(MessageRetrieval.position)
    )
    return message, [TracedChunk(row, name, text) for row, name, text in rows]


@dataclass(frozen=True)
class Answered:
    message_id: uuid.UUID
    event: DoneEvent
    first_token_ms: int
    latency_ms: int


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


async def answer(
    prepared: PreparedTurn,
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    gateway: ModelGateway,
    embedders: dict[str, Embedder],
    clock: Clock,
) -> AsyncIterator[TokenEvent | CitationEvent | Answered]:
    """Streams the answer's tokens and citations, then saves the answer, with what retrieval
    found for it, and ends with ``Answered``."""
    started = time.perf_counter()
    first_token_ms: int | None = None
    default = prepared.default
    model = gateway.chat_model(default.credential, default.model)
    async with sessionmaker() as session:

        async def retrieve_in_project(query: str, settings: Retrieval) -> RetrievalResult:
            return await retrieve(session, prepared.project, query, settings, embedders)

        async for event in run_turn(
            prepared.turns,
            prepared.config,
            "",  # Project Instructions arrive with ticket 05-01.
            prepared.question,
            model=model,
            retrieve=retrieve_in_project,
        ):
            if isinstance(event, TokenEvent):
                if first_token_ms is None:
                    first_token_ms = _elapsed_ms(started)
                yield event
                continue
            if isinstance(event, CitationEvent):
                yield event
                continue
            latency_ms = _elapsed_ms(started)
            now = clock.now()
            usage = TokenUsage(event.input_tokens, event.output_tokens)
            pricing = await credential_pricing(session, default.credential)
            message = Message(
                organisation_id=prepared.organisation_id,
                conversation_id=prepared.conversation_id,
                role=MessageRole.ASSISTANT,
                content=event.answer,
                config_source=DRAFT,
                # A fallback reply asked no model, so it names none.
                model_provider=None if event.fallback else default.credential.provider,
                model_name=None if event.fallback else default.model,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                first_token_ms=first_token_ms if first_token_ms is not None else latency_ms,
                latency_ms=latency_ms,
                cost_usd=cost(pricing, default.model, usage, now, await price_table(session)),
                fallback=event.fallback,
            )
            session.add(message)
            await session.flush()
            session.add_all(_retrievals(prepared.organisation_id, message.id, event))
            conversation = await session.get_one(Conversation, prepared.conversation_id)
            conversation.last_activity_at = now
            await session.commit()
            yield Answered(message.id, event, message.first_token_ms or 0, latency_ms)
