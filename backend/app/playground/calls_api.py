"""Playground Call routes (spec 20): an Editor starts a Call with the Agent's Draft in a
Playground Conversation (``POST …/playground/conversations/{conversation_id}/calls``) and ends it
(``DELETE …/calls/current``). The Call's turns reach the platform from the voice layer, through
the turn endpoint (``app.embed.turn_api``), with the Playground Call token the start returns.
"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.agents.api import (
    AGENT_ARCHIVED_RESPONSE,
    NOT_FOUND_RESPONSE,
    ClockDep,
    agent_archived,
    archived,
    not_found,
)
from app.agents.service import AgentArchivedError, AgentNotFoundError
from app.auth.api import Db, ErrorResponse
from app.core.settings import Settings
from app.embed.api import Signer
from app.embed.calls import CallsOffError
from app.embed.calls_api import CallJoinOut, StartedCallOut
from app.playground import calls, service
from app.playground.api import NOT_IN_PROJECT
from app.projects.instructions import InstructionsVersionNotFoundError
from app.projects.service import ProjectArchivedError, ProjectNotFoundError
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import Scope
from app.voice.api import VOICE_LAYER_FAILED, Voice, voice_layer_failed
from app.voice.port import VoiceLayerError

router = APIRouter(
    prefix=ORGANISATION_PREFIX
    + "/projects/{project_id}/agents/{agent_id}/playground/conversations/{conversation_id}/calls",
    tags=["playground"],
)

CALLS_OFF = (
    "Calling is off for this Agent. Turn it on in Embed & limits, Call settings, to call the Draft."
)
CALL_OPEN = "This Playground Conversation already has a Call open. End it first."


class StartPlaygroundCallRequest(BaseModel):
    # The Instructions Version the Call answers with; null or left out: the Instructions Draft.
    instructions_version_id: uuid.UUID | None = None


_START_RESPONSES: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND_RESPONSE,
    **AGENT_ARCHIVED_RESPONSE,
    409: {
        "model": ErrorResponse,
        "description": (
            "The Project or Agent is archived, the Agent's calling is off, or the Conversation "
            "already has a Call open."
        ),
    },
    422: {"description": "The Instructions Version isn't one of the Project's."},
    502: {"model": ErrorResponse, "description": VOICE_LAYER_FAILED},
}


@router.post(
    "",
    operation_id="startPlaygroundCall",
    status_code=status.HTTP_201_CREATED,
    responses=_START_RESPONSES,
)
async def start_call(
    request: Request,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID,
    scope: Scope,
    db: Db,
    clock: ClockDep,
    signer: Signer,
    voice: Voice,
    body: StartPlaygroundCallRequest | None = None,
) -> StartedCallOut:
    """Starts a Call with the Agent's Draft in the Playground Conversation, with the Agent's Call
    settings, answering with the Instructions Draft or the chosen Instructions Version. The
    spoken greeting opens a Conversation with no Messages. The Call token returned is a
    Playground Call token: its turns are answered by the Draft and are kept out of metrics, the
    Token Budget and the Call minutes budget. An Agent with calling off refuses with a 409."""
    version_id = None if body is None else body.instructions_version_id
    try:
        started = await calls.start_call(
            db,
            scope,
            project_id,
            agent_id,
            conversation_id,
            instructions_version_id=version_id,
            signer=signer,
            voice=voice,
            now=clock.now(),
        )
    except (ProjectNotFoundError, AgentNotFoundError, service.ConversationNotFoundError):
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    except AgentArchivedError:
        raise agent_archived() from None
    except InstructionsVersionNotFoundError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NOT_IN_PROJECT) from None
    except CallsOffError:
        raise HTTPException(status.HTTP_409_CONFLICT, CALLS_OFF) from None
    except calls.CallOpenError:
        raise HTTPException(status.HTTP_409_CONFLICT, CALL_OPEN) from None
    except VoiceLayerError:
        raise voice_layer_failed() from None
    settings: Settings = request.app.state.settings
    return StartedCallOut(
        call_id=started.call_id,
        call_token=started.call_token,
        join=CallJoinOut(
            voice_layer=settings.voice_layer,
            conversation_token=started.join.conversation_token,
            greet=started.join.greet,
        ),
        max_call_minutes=started.max_call_minutes,
    )


@router.delete(
    "/current",
    operation_id="endPlaygroundCall",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND_RESPONSE,
)
async def end_call(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    conversation_id: uuid.UUID,
    scope: Scope,
    db: Db,
    clock: ClockDep,
) -> None:
    """Ends the Playground Conversation's open Call, freezing its minutes and Voice Cost; with no
    Call open, nothing changes. What was said stays as Spoken Messages."""
    try:
        await calls.end_call(db, scope, project_id, agent_id, conversation_id, now=clock.now())
    except (ProjectNotFoundError, AgentNotFoundError, service.ConversationNotFoundError):
        raise not_found() from None
