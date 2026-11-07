"""Playground Conversations: starting one, reading it back, and answering a question with
the Agent runtime, saving the question and the answer as Messages.

In the Playground a question is answered by the Draft, following the Project Instructions Draft
or the Instructions Version the Editor chose (the Instructions picker), and the answer records the
Draft marker and which Instructions it ran with. ``save_question`` and ``answer`` are shared with
serving the Live Version (``app.agents.serving``), whose answers record the Agent Version instead
(its pinned Instructions are derivable from it).

A question is answered by the configuration's Model override, or else the Organisation's
Default Model, through the model gateway, from Chunks the retrieval module finds in the Agent's
Project (reranked by the configuration's Reranker, when it has one, also built through the
gateway). The question is saved before the answer streams; the answer, with its tokens, latency
and cost, once the stream ends.
"""

import itertools
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.config import AgentConfig, ModelChoice, Retrieval
from app.agents.service import active_agent, get_agent
from app.conversations.models import (
    DRAFT,
    VERSION,
    Conversation,
    InstructionsSource,
    Message,
    MessageRetrieval,
    MessageRole,
)
from app.core.clock import Clock
from app.credentials.models import ProviderCredential
from app.default_model.service import read_default
from app.documents.models import Chunk, Document
from app.embeddings.port import Embedder
from app.gateway.gateway import ModelGateway
from app.gateway.ports import Reranker
from app.guardrails.pipeline import GuardrailPipeline, RefusalEvent, blocked
from app.pricing.service import credential_pricing, price_table
from app.pricing.table import TokenUsage, cost
from app.projects.instructions import project_version
from app.projects.models import InstructionsVersion, Project
from app.projects.service import active_project
from app.retrieval.service import RetrievalResult, retrieve
from app.runtime.errors import PROVIDER_ERRORS, ErrorEvent, provider_error
from app.runtime.prompt import Turn
from app.runtime.runtime import CitationEvent, DoneEvent, ReplaceEvent, TokenEvent
from app.tenancy.repository import OrganisationScope


class MessageNotFoundError(Exception):
    """No answer with that ID in the Conversation."""


class ConversationNotFoundError(Exception):
    """No Playground Conversation with that ID for the Agent."""


class NoDefaultModelError(Exception):
    """The Draft has no Model override and the Organisation has no Default Model."""


@dataclass(frozen=True)
class ChosenModel:
    """A credential and one of its models: the chat model that answers, or the Reranker."""

    credential: ProviderCredential
    model: str


async def _chosen(
    session: AsyncSession, organisation_id: uuid.UUID, choice: ModelChoice
) -> ChosenModel:
    """The credential a Draft setting names, with its model. Saving the Draft checked the
    credential offers the model and made it a Credential reference, so it can't have been
    deleted since."""
    found = await session.scalars(
        select(ProviderCredential).where(
            ProviderCredential.id == choice.credential_id,
            ProviderCredential.organisation_id == organisation_id,
        )
    )
    return ChosenModel(found.one(), choice.model)


async def _chat_model(
    session: AsyncSession, organisation_id: uuid.UUID, config: AgentConfig
) -> ChosenModel:
    override = config.behaviour.model
    if override is not None:
        return await _chosen(session, organisation_id, override)
    default = await read_default(session, organisation_id)
    if default is None:
        raise NoDefaultModelError
    return ChosenModel(default.credential, default.model)


async def start_conversation(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    now: datetime,
) -> Conversation:
    await active_project(session, scope, project_id)
    found = await active_agent(session, scope, project_id, agent_id)
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
    """Each question with the answer that followed it. A question left unanswered is skipped,
    and so is one the input Guardrail blocked: an attack isn't replayed to the model later."""
    return [
        Turn(question.content, answer.content)
        for question, answer in itertools.pairwise(messages)
        if (question.role, answer.role) == (MessageRole.USER, MessageRole.ASSISTANT)
        and not blocked(answer.guardrail_outcomes)
    ]


@dataclass(frozen=True)
class PreparedTurn:
    """A question saved and ready to answer, with the configuration and Project Instructions
    that answer it: the Draft's in the Playground, or an Agent Version's when it is served."""

    organisation_id: uuid.UUID
    conversation_id: uuid.UUID
    project: Project
    config: AgentConfig
    instructions: str
    turns: list[Turn]
    question: str
    chat: ChosenModel
    # In the Playground, the Instructions Version the answer follows (None: the Draft).
    instructions_version_id: uuid.UUID | None = None
    instructions_version_number: int | None = None
    reranker: ChosenModel | None = None
    # The Agent Version answering; None for the Draft.
    agent_version_id: uuid.UUID | None = None

    @property
    def instructions_source(self) -> InstructionsSource:
        if self.instructions_version_id is None:
            return InstructionsSource.DRAFT
        return InstructionsSource.VERSION


async def prepare_turn(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID,
    question: str,
    *,
    instructions_version_id: uuid.UUID | None = None,
    now: datetime,
) -> PreparedTurn:
    """Checks the question can be answered by the Draft, then saves it. With no
    ``instructions_version_id`` the answer follows the Project Instructions Draft; otherwise that
    Version of the Project's Instructions (``InstructionsVersionNotFoundError`` if the Project
    has no such Version)."""
    project = await active_project(session, scope, project_id)
    version = (
        None
        if instructions_version_id is None
        else await project_version(session, project, instructions_version_id)
    )
    found = await active_agent(session, scope, project_id, agent_id)
    conversation, messages = await get_conversation(
        session, scope, project_id, agent_id, conversation_id
    )
    return await save_question(
        session,
        project,
        conversation,
        messages,
        found.draft,
        project.instructions if version is None else version.markdown,
        question,
        agent_version_id=None,
        instructions_version=version,
        now=now,
    )


async def save_question(
    session: AsyncSession,
    project: Project,
    conversation: Conversation,
    messages: list[Message],
    config: AgentConfig,
    instructions: str,
    question: str,
    *,
    agent_version_id: uuid.UUID | None,
    instructions_version: InstructionsVersion | None = None,
    now: datetime,
) -> PreparedTurn:
    """Checks ``config`` has a chat model, then saves the question in the Conversation."""
    organisation_id = conversation.organisation_id
    chat = await _chat_model(session, organisation_id, config)
    reranker_choice = config.retrieval.reranker
    reranker = (
        None
        if reranker_choice is None
        else await _chosen(session, organisation_id, reranker_choice)
    )
    session.add(
        Message(
            organisation_id=organisation_id,
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=question,
        )
    )
    conversation.last_activity_at = now
    await session.commit()
    return PreparedTurn(
        organisation_id=organisation_id,
        conversation_id=conversation.id,
        project=project,
        config=config,
        instructions=instructions,
        turns=_turns(messages),
        question=question,
        chat=chat,
        instructions_version_id=None if instructions_version is None else instructions_version.id,
        instructions_version_number=(
            None if instructions_version is None else instructions_version.number
        ),
        reranker=reranker,
        agent_version_id=agent_version_id,
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
    guardrails: GuardrailPipeline,
    embedders: dict[str, Embedder],
    clock: Clock,
) -> AsyncIterator[
    TokenEvent | ReplaceEvent | RefusalEvent | CitationEvent | ErrorEvent | Answered
]:
    """Streams the answer's tokens and citations (or the replacement of an answer that leaked
    the Canary token, or the refusal of a question the input Guardrail blocked), then saves
    the answer, with what retrieval found for it and the Guardrail outcomes, and ends with
    ``Answered``. If the provider fails, it ends with an
    ``ErrorEvent`` instead and saves no answer, so the question is not remembered."""
    started = time.perf_counter()
    first_token_ms: int | None = None
    chosen = prepared.chat
    try:
        model = gateway.chat_model(chosen.credential, chosen.model)
    except PROVIDER_ERRORS as error:
        yield provider_error(error, chosen.model)
        return
    reranking = prepared.reranker
    reranker: Reranker | None = None
    if reranking is not None:
        try:
            reranker = gateway.reranker(reranking.credential, reranking.model)
        except PROVIDER_ERRORS as error:
            yield provider_error(error, reranking.model)
            return
    async with sessionmaker() as session:

        async def retrieve_in_project(query: str, settings: Retrieval) -> RetrievalResult:
            return await retrieve(
                session, prepared.project, query, settings, embedders, reranker=reranker
            )

        async for event in guardrails.run_turn(
            prepared.turns,
            prepared.config,
            prepared.instructions,
            prepared.question,
            model=model,
            retrieve=retrieve_in_project,
        ):
            if isinstance(event, TokenEvent):
                if first_token_ms is None:
                    first_token_ms = _elapsed_ms(started)
                yield event
                continue
            if isinstance(event, CitationEvent | ReplaceEvent | RefusalEvent | ErrorEvent):
                yield event
                continue
            latency_ms = _elapsed_ms(started)
            now = clock.now()
            usage = TokenUsage(event.input_tokens, event.output_tokens)
            asked_none = event.fallback or event.refused
            pricing = await credential_pricing(session, chosen.credential)
            message = Message(
                organisation_id=prepared.organisation_id,
                conversation_id=prepared.conversation_id,
                role=MessageRole.ASSISTANT,
                content=event.answer,
                config_source=DRAFT if prepared.agent_version_id is None else VERSION,
                agent_version_id=prepared.agent_version_id,
                # An Agent Version's answer records no Instructions: its pinned Instructions
                # are named by the Version.
                instructions_source=(
                    prepared.instructions_source if prepared.agent_version_id is None else None
                ),
                instructions_version_id=prepared.instructions_version_id,
                # A fallback reply or a refusal asked no model, so it names none.
                model_provider=None if asked_none else chosen.credential.provider,
                model_name=None if asked_none else chosen.model,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                first_token_ms=first_token_ms if first_token_ms is not None else latency_ms,
                latency_ms=latency_ms,
                cost_usd=cost(pricing, chosen.model, usage, now, await price_table(session)),
                fallback=event.fallback,
                guardrail_outcomes=[o.as_dict() for o in event.guardrail_outcomes],
            )
            session.add(message)
            await session.flush()
            session.add_all(_retrievals(prepared.organisation_id, message.id, event))
            conversation = await session.get_one(Conversation, prepared.conversation_id)
            conversation.last_activity_at = now
            await session.commit()
            yield Answered(message.id, event, message.first_token_ms or 0, latency_ms)
