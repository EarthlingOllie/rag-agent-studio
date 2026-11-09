"""Playground routes: start a Playground Conversation with an Agent's Draft, read it back, and
send a question, answered as a Server-Sent Events stream. Editors and Owners may use them.

A question is answered with the Project Instructions Draft, or with the Instructions Version
it names (``instructions_version_id``, any of the Project's Versions). Each answer records
which: ``instructions_source`` is ``draft`` or ``version``, with the Version's ID and number.

The stream sends ``token`` events (``{"text": …}``) as the answer arrives, then a ``citation``
event per Chunk the answer cites, then one ``done`` event with the saved Message's ID, the
Instructions it ran with, its token counts and latency, whether the answer is the Agent's
fallback text, the Chunks the model was given and the Chunks retrieval left out (with
the reason: below the minimum score, or outside top-k). If the answer starts to leak the Canary
token, the stream is cut: a ``replace`` event (``{"text": …}``) carries the fallback text that
replaces everything sent so far, then ``done``. If the model's provider fails, the stream ends
instead with one ``error`` event (``{"code": …, "message": …}``): the code is ``invalid_key``,
``rate_limited``, ``model_unavailable`` or ``provider_error``, and the message says what to do.
No answer is saved, and anything streamed before it is not part of one.
"""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, PlainSerializer, StringConstraints

from app.agents.api import (
    AGENT_ARCHIVED_RESPONSE,
    NOT_FOUND_RESPONSE,
    agent_archived,
    archived,
    not_found,
)
from app.agents.service import AgentArchivedError, AgentNotFoundError
from app.auth.api import Db, ErrorResponse
from app.conversations.models import Conversation, Message
from app.conversations.service import MessageNotFoundError, TracedChunk
from app.core.clock import Clock, get_clock
from app.documents.ports import IngestionPorts
from app.guardrails.outcomes import Action, Layer, Verdict
from app.guardrails.pipeline import RefusalEvent
from app.playground import service
from app.projects.instructions import InstructionsVersionNotFoundError, version_numbers
from app.projects.service import ProjectArchivedError, ProjectNotFoundError
from app.retrieval.service import ExcludedReason
from app.runtime.errors import ErrorEvent
from app.runtime.runtime import CitationEvent, ReplaceEvent, TokenEvent
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import Scope

router = APIRouter(
    prefix=ORGANISATION_PREFIX + "/projects/{project_id}/agents/{agent_id}/playground",
    tags=["playground"],
)

NOT_IN_PROJECT = "That Instructions Version isn't one of this Project's."
NO_DEFAULT_MODEL = (
    "This Organisation has no Default Model. An Owner can choose one in Settings, Models."
)
QUESTION_MAX = 4000

ClockDep = Annotated[Clock, Depends(get_clock)]
Question = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=QUESTION_MAX)
]


# US dollars as a plain decimal string: "0.000000000", never the exponent form "0E-9" that
# str() gives a zero read back from Numeric(18, 9).
Dollars = Annotated[Decimal, PlainSerializer(lambda d: format(d, "f"), return_type=str)]


InstructionsSourceOut = Literal["draft", "version"]


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    # The rest are set on the Agent's answers only. ``config_source`` is ``draft`` for a
    # Draft answer, or ``version`` with the answering ``agent_version_id``.
    config_source: str | None
    # The Project Instructions the answer ran with: the Draft, or a Version (its ID and number).
    instructions_source: InstructionsSourceOut | None
    instructions_version_id: uuid.UUID | None
    instructions_version_number: int | None
    agent_version_id: uuid.UUID | None
    model_provider: str | None
    model_name: str | None
    input_tokens: int | None
    output_tokens: int | None
    first_token_ms: int | None
    latency_ms: int | None
    cost_usd: Dollars | None


class ConversationOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    is_playground: bool
    created_at: datetime
    last_activity_at: datetime
    messages: list[MessageOut]


class TracedChunkOut(BaseModel):
    # Both null once the Chunk's Document is deleted (a tombstone).
    chunk_id: uuid.UUID | None
    document_id: uuid.UUID | None
    # The Document's name; for a deleted Document, its name when the answer was given (null
    # only for Documents deleted before names were kept).
    document_name: str | None
    # True when the Document has since been deleted: the Trace shows "Chunk from deleted
    # Document <name>".
    document_deleted: bool
    # Null once the Chunk's Document edition is replaced or deleted.
    text: str | None
    # The weighted reciprocal rank fusion score, and the relevance the minimum applies to.
    score: float
    relevance: float
    # The number in the Chunk's label ([C1] is rank 1); null when it wasn't given to the model.
    rank: int | None
    cited: bool
    excluded_reason: ExcludedReason | None


class GuardrailOutcomeOut(BaseModel):
    """What one Guardrail layer decided about the answer, and what it did."""

    # ``input``: the input Guardrail, before the model; ``canary``: the Canary token, after it.
    layer: Layer
    verdict: Verdict
    action: Action
    reason: str
    # How sure the layer was, from 0 to 1; null for a layer that doesn't score (the canary).
    score: float | None = None


class TraceOut(BaseModel):
    """Why an answer came out as it did: the model, its usage, cost and latency, and every
    Chunk retrieval found, given to the model (cited or not) or left out with the reason."""

    message_id: uuid.UUID
    config_source: str | None
    # The number of the Agent Version that answered; null for a Draft answer.
    agent_version_number: int | None
    instructions_source: InstructionsSourceOut | None
    instructions_version_id: uuid.UUID | None
    instructions_version_number: int | None
    agent_version_id: uuid.UUID | None
    model_provider: str | None
    model_name: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: Dollars | None
    first_token_ms: int | None
    latency_ms: int | None
    # True when no Chunk reached the minimum score, so the answer is the fallback text.
    fallback: bool
    chunks: list[TracedChunkOut]
    guardrail_outcomes: list[GuardrailOutcomeOut]


class SendMessageRequest(BaseModel):
    content: Question
    # The Instructions Version to answer with; null or left out: the Instructions Draft.
    instructions_version_id: uuid.UUID | None = None


def _instructions(message: Message, numbers: dict[uuid.UUID, int]) -> dict[str, Any]:
    version_id = message.instructions_version_id
    return {
        "instructions_source": message.instructions_source,
        "instructions_version_id": version_id,
        "instructions_version_number": None if version_id is None else numbers[version_id],
    }


async def _numbers(db: Db, messages: list[Message]) -> dict[uuid.UUID, int]:
    return await version_numbers(
        db, {m.instructions_version_id for m in messages if m.instructions_version_id}
    )


def message_fields(message: Message, numbers: dict[uuid.UUID, int]) -> dict[str, Any]:
    """A ``MessageOut``'s fields; ``numbers`` holds the Instructions Versions' numbers."""
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at,
        "config_source": message.config_source,
        **_instructions(message, numbers),
        "agent_version_id": message.agent_version_id,
        "model_provider": message.model_provider,
        "model_name": message.model_name,
        "input_tokens": message.input_tokens,
        "output_tokens": message.output_tokens,
        "first_token_ms": message.first_token_ms,
        "latency_ms": message.latency_ms,
        "cost_usd": message.cost_usd,
    }


async def instructions_numbers(db: Db, messages: list[Message]) -> dict[uuid.UUID, int]:
    """The numbers of the Instructions Versions the Messages ran with."""
    return await _numbers(db, messages)


def _out(
    conversation: Conversation, messages: list[Message], numbers: dict[uuid.UUID, int]
) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        agent_id=conversation.agent_id,
        is_playground=conversation.is_playground,
        created_at=conversation.created_at,
        last_activity_at=conversation.last_activity_at,
        messages=[MessageOut(**message_fields(m, numbers)) for m in messages],
    )


async def trace_out(
    db: Db, message: Message, agent_version_number: int | None, chunks: list[TracedChunk]
) -> TraceOut:
    """The Trace of an answer, as the Studio reads it."""
    return TraceOut(
        message_id=message.id,
        config_source=message.config_source,
        agent_version_number=agent_version_number,
        **_instructions(message, await _numbers(db, [message])),
        agent_version_id=message.agent_version_id,
        model_provider=message.model_provider,
        model_name=message.model_name,
        input_tokens=message.input_tokens,
        output_tokens=message.output_tokens,
        cost_usd=message.cost_usd,
        first_token_ms=message.first_token_ms,
        latency_ms=message.latency_ms,
        fallback=message.fallback,
        guardrail_outcomes=[
            GuardrailOutcomeOut.model_validate(o) for o in message.guardrail_outcomes
        ],
        chunks=[
            TracedChunkOut(
                chunk_id=c.retrieval.chunk_id,
                document_id=c.retrieval.document_id,
                document_name=c.document_name,
                document_deleted=c.document_deleted,
                text=c.text,
                score=c.retrieval.score,
                relevance=c.retrieval.relevance,
                rank=c.retrieval.rank,
                cited=c.retrieval.cited,
                excluded_reason=cast(ExcludedReason | None, c.retrieval.excluded_reason),
            )
            for c in chunks
        ],
    )


@router.post(
    "/conversations",
    status_code=status.HTTP_201_CREATED,
    operation_id="startPlaygroundConversation",
    responses={**NOT_FOUND_RESPONSE, **AGENT_ARCHIVED_RESPONSE},
)
async def start_conversation(
    project_id: uuid.UUID, agent_id: uuid.UUID, scope: Scope, db: Db, clock: ClockDep
) -> ConversationOut:
    """Starts an empty Playground Conversation with the Agent's Draft. An archived Agent starts
    none."""
    try:
        conversation = await service.start_conversation(
            db, scope, project_id, agent_id, now=clock.now()
        )
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    except AgentArchivedError:
        raise agent_archived() from None
    return _out(conversation, [], {})


@router.get(
    "/conversations/{conversation_id}",
    operation_id="getPlaygroundConversation",
    responses=NOT_FOUND_RESPONSE,
)
async def get_conversation(
    project_id: uuid.UUID, agent_id: uuid.UUID, conversation_id: uuid.UUID, scope: Scope, db: Db
) -> ConversationOut:
    """The Playground Conversation and its Messages, oldest first."""
    try:
        conversation, messages = await service.get_conversation(
            db, scope, project_id, agent_id, conversation_id
        )
    except (ProjectNotFoundError, AgentNotFoundError, service.ConversationNotFoundError):
        raise not_found() from None
    return _out(conversation, messages, await _numbers(db, messages))


@router.get(
    "/conversations/{conversation_id}/messages/{message_id}/trace",
    operation_id="getPlaygroundTrace",
    responses=NOT_FOUND_RESPONSE,
)
async def get_trace(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    scope: Scope,
    db: Db,
) -> TraceOut:
    """The Trace of one of the Agent's answers in the Playground Conversation."""
    try:
        message, chunks = await service.get_trace(
            db, scope, project_id, agent_id, conversation_id, message_id
        )
    except (
        ProjectNotFoundError,
        AgentNotFoundError,
        service.ConversationNotFoundError,
        MessageNotFoundError,
    ):
        raise not_found() from None
    return await trace_out(db, message, None, chunks)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


_STREAM: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
        "description": (
            "Server-Sent Events: `token` events, then `citation` events and one `done` event; "
            "or, when the answer leaks the Canary token, a `replace` event then `done`; "
            "or, when the input Guardrail blocks the question, a `refusal` event (`text`, the "
            "Agent's refusal text) then `done`, and no model is asked; "
            "or, when the model provider fails, one `error` event (`code`: `invalid_key`, "
            "`rate_limited`, `model_unavailable` or `provider_error`; `message`)."
        ),
    },
    409: {
        "model": ErrorResponse,
        "description": "The Project or Agent is archived, or there is no Default Model.",
    },
    422: {
        "description": (
            "The question is empty or too long, or the Instructions Version isn't one of the "
            "Project's."
        ),
    },
}


@router.post(
    "/conversations/{conversation_id}/messages",
    operation_id="sendPlaygroundMessage",
    response_class=StreamingResponse,
    responses={**NOT_FOUND_RESPONSE, **_STREAM},
)
async def send_message(
    request: Request,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: SendMessageRequest,
    scope: Scope,
    db: Db,
    clock: ClockDep,
) -> StreamingResponse:
    """Asks the Agent's Draft a question, with the Instructions Draft or the chosen Instructions
    Version; the answer streams back as Server-Sent Events. An archived Agent answers no more
    questions; its Conversations can still be read."""
    try:
        prepared = await service.prepare_turn(
            db,
            scope,
            project_id,
            agent_id,
            conversation_id,
            body.content,
            instructions_version_id=body.instructions_version_id,
            now=clock.now(),
        )
    except (ProjectNotFoundError, AgentNotFoundError, service.ConversationNotFoundError):
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    except AgentArchivedError:
        raise agent_archived() from None
    except service.NoDefaultModelError:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_DEFAULT_MODEL) from None
    except InstructionsVersionNotFoundError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NOT_IN_PROJECT) from None
    ingestion: IngestionPorts = request.app.state.ingestion

    async def events() -> AsyncIterator[str]:
        async for event in service.answer(
            prepared,
            sessionmaker=request.app.state.sessionmaker,
            gateway=request.app.state.model_gateway,
            guardrails=request.app.state.guardrails,
            embedders=ingestion.embedders,
            clock=request.app.state.clock,
        ):
            if isinstance(event, TokenEvent):
                yield _sse("token", {"text": event.text})
            elif isinstance(event, ReplaceEvent):
                yield _sse("replace", {"text": event.text})
            elif isinstance(event, RefusalEvent):
                yield _sse("refusal", {"text": event.text})
            elif isinstance(event, ErrorEvent):
                yield _sse("error", {"code": event.kind, "message": event.message})
            elif isinstance(event, CitationEvent):
                yield _sse(
                    "citation",
                    {
                        "label": event.label,
                        "chunk_id": str(event.chunk.chunk_id),
                        "document_id": str(event.chunk.document_id),
                        "document_name": event.chunk.document_name,
                        "rank": event.chunk.rank,
                    },
                )
            else:
                yield _sse(
                    "done",
                    {
                        "message_id": str(event.message_id),
                        "instructions_source": prepared.instructions_source.value,
                        "instructions_version_id": (
                            None
                            if prepared.instructions_version_id is None
                            else str(prepared.instructions_version_id)
                        ),
                        "instructions_version_number": prepared.instructions_version_number,
                        "input_tokens": event.event.input_tokens,
                        "output_tokens": event.event.output_tokens,
                        "first_token_ms": event.first_token_ms,
                        "latency_ms": event.latency_ms,
                        "fallback": event.event.fallback,
                        "chunks": [
                            {
                                "chunk_id": str(c.chunk_id),
                                "score": c.score,
                                "relevance": c.relevance,
                                "rank": c.rank,
                            }
                            for c in event.event.retrieved
                        ],
                        "excluded": [
                            {
                                "chunk_id": str(e.chunk_id),
                                "score": e.score,
                                "relevance": e.relevance,
                                "reason": e.reason,
                            }
                            for e in event.event.excluded
                        ],
                    },
                )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
