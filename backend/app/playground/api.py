"""Playground routes: start a Playground Conversation with an Agent's Draft, read it back, and
send a question, answered as a Server-Sent Events stream. Editors and Owners may use them.

The stream sends ``token`` events (``{"text": …}``) as the answer arrives, then one ``done``
event with the saved Message's ID, its token counts and latency.
"""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, StringConstraints

from app.agents.api import ARCHIVED_RESPONSE, NOT_FOUND_RESPONSE, archived, not_found
from app.agents.service import AgentNotFoundError
from app.auth.api import Db, ErrorResponse
from app.conversations.models import Conversation, Message
from app.core.clock import Clock, get_clock
from app.documents.ports import IngestionPorts
from app.playground import service
from app.projects.service import ProjectArchivedError, ProjectNotFoundError
from app.runtime.runtime import TokenEvent
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import Scope

router = APIRouter(
    prefix=ORGANISATION_PREFIX + "/projects/{project_id}/agents/{agent_id}/playground",
    tags=["playground"],
)

NO_DEFAULT_MODEL = (
    "This Organisation has no Default Model. An Owner can choose one in Settings, Models."
)
QUESTION_MAX = 4000

ClockDep = Annotated[Clock, Depends(get_clock)]
Question = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=QUESTION_MAX)
]


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    # The rest are set on the Agent's answers only.
    config_source: str | None
    model_provider: str | None
    model_name: str | None
    input_tokens: int | None
    output_tokens: int | None
    first_token_ms: int | None
    latency_ms: int | None
    cost_usd: Decimal | None


class ConversationOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    is_playground: bool
    created_at: datetime
    last_activity_at: datetime
    messages: list[MessageOut]


class SendMessageRequest(BaseModel):
    content: Question


def _out(conversation: Conversation, messages: list[Message]) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        agent_id=conversation.agent_id,
        is_playground=conversation.is_playground,
        created_at=conversation.created_at,
        last_activity_at=conversation.last_activity_at,
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                config_source=m.config_source,
                model_provider=m.model_provider,
                model_name=m.model_name,
                input_tokens=m.input_tokens,
                output_tokens=m.output_tokens,
                first_token_ms=m.first_token_ms,
                latency_ms=m.latency_ms,
                cost_usd=m.cost_usd,
            )
            for m in messages
        ],
    )


@router.post(
    "/conversations",
    status_code=status.HTTP_201_CREATED,
    operation_id="startPlaygroundConversation",
    responses={**NOT_FOUND_RESPONSE, **ARCHIVED_RESPONSE},
)
async def start_conversation(
    project_id: uuid.UUID, agent_id: uuid.UUID, scope: Scope, db: Db, clock: ClockDep
) -> ConversationOut:
    """Starts an empty Playground Conversation with the Agent's Draft."""
    try:
        conversation = await service.start_conversation(
            db, scope, project_id, agent_id, now=clock.now()
        )
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    return _out(conversation, [])


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
    return _out(conversation, messages)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


_STREAM: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
        "description": "Server-Sent Events: `token` events, then one `done` event.",
    },
    409: {"model": ErrorResponse, "description": "The Project is archived, or no Default Model."},
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
    """Asks the Agent's Draft a question; the answer streams back as Server-Sent Events."""
    try:
        prepared = await service.prepare_turn(
            db, scope, project_id, agent_id, conversation_id, body.content, now=clock.now()
        )
    except (ProjectNotFoundError, AgentNotFoundError, service.ConversationNotFoundError):
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    except service.NoDefaultModelError:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_DEFAULT_MODEL) from None
    ingestion: IngestionPorts = request.app.state.ingestion

    async def events() -> AsyncIterator[str]:
        async for event in service.answer(
            prepared,
            sessionmaker=request.app.state.sessionmaker,
            gateway=request.app.state.model_gateway,
            embedders=ingestion.embedders,
            clock=request.app.state.clock,
        ):
            if isinstance(event, TokenEvent):
                yield _sse("token", {"text": event.text})
            else:
                yield _sse(
                    "done",
                    {
                        "message_id": str(event.message_id),
                        "input_tokens": event.event.input_tokens,
                        "output_tokens": event.event.output_tokens,
                        "first_token_ms": event.first_token_ms,
                        "latency_ms": event.latency_ms,
                        "chunks": [
                            {"chunk_id": str(c.chunk_id), "score": c.score, "rank": c.rank}
                            for c in event.event.retrieved
                        ],
                    },
                )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
