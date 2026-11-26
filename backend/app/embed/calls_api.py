"""Call routes of the widget API (spec 20): the Visitor's widget starts a Call in its
Conversation (``POST …/conversation/calls``) and ends it (``DELETE …/conversation/calls/current``),
with the Conversation token as for messages, and says when the Visitor talked over a reply
(``POST …/conversation/calls/current/interruptions``). The turns of the Call reach the platform
from the voice layer, through the turn endpoint (``app.embed.turn_api``).
"""

import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.agents.api import ClockDep
from app.agents.serving import AgentNotLiveError, AgentNotServedError
from app.auth.api import Db
from app.core.settings import Settings
from app.embed import call_limits, calls, service
from app.embed.admission import Refusal
from app.embed.api import (
    BUDGET_EXHAUSTED,
    INVALID_TOKEN,
    NO_LONGER_AVAILABLE,
    RATE_LIMITED,
    Authorization,
    Serving,
    Signer,
    VisitorIp,
    _bearer,
    _errors,
    _gone,
    _invalid,
)
from app.embed.call_limits import CallRefusal
from app.voice.api import Voice
from app.voice.port import VoiceLayerError

router = APIRouter(prefix="/api/widget/agents/{public_id}/conversation/calls", tags=["widget"])

CALLS_OFF = "This assistant doesn't take Calls."
# The refusal's reason when the voice layer couldn't start the Call.
VOICE_UNAVAILABLE = "voice_unavailable"


class CallJoinOut(BaseModel):
    # Which voice layer holds the Call: ElevenLabs, or the scripted fake (`docker compose` and
    # tests), which the widget plays without audio.
    voice_layer: Literal["elevenlabs", "fake"]
    # What the browser joins the Call in the voice layer with.
    conversation_token: str
    # Whether the voice layer speaks the Agent's spoken greeting as the Call opens: only for a
    # Conversation with no Messages yet. Otherwise the Call opens with the Agent listening.
    greet: bool


class StartedCallOut(BaseModel):
    call_id: uuid.UUID
    # Signed and bound to the Call and its Conversation; the widget hands it to the voice layer,
    # which sends it back with every turn. It lasts the Maximum Call length.
    call_token: str
    join: CallJoinOut
    # The Maximum Call length, in minutes: the platform ends the Call that long after it
    # started, and the widget returns to the chat saying why.
    max_call_minutes: int


class CallRefusedOut(BaseModel):
    # The Agent's unavailable text.
    detail: str
    # `rate_limited`, `budget_exhausted` (the day's Token Budget is spent),
    # `call_open` (the Conversation already has a Call), `too_many_calls` (the Visitor's IP
    # address holds the platform's cap of open Calls with the Agent), `call_minutes_exhausted`
    # (the day's Call minutes budget is spent) or `voice_unavailable` (the voice layer couldn't
    # start the Call). Messaging still works.
    reason: Literal[
        "rate_limited",
        "budget_exhausted",
        "call_open",
        "too_many_calls",
        "call_minutes_exhausted",
        "voice_unavailable",
    ]


def _refused(unavailable: str, reason: str) -> JSONResponse:
    return JSONResponse(
        {"detail": unavailable, "reason": reason}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE
    )


_START_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_errors((401, INVALID_TOKEN), (404, NO_LONGER_AVAILABLE), (409, CALLS_OFF)),
    503: {
        "model": CallRefusedOut,
        "description": "Admission control refused the Call, or the voice layer couldn't start it",
    },
}


@router.post(
    "",
    operation_id="startWidgetCall",
    status_code=status.HTTP_201_CREATED,
    response_model=StartedCallOut,
    responses=_START_RESPONSES,
)
async def start_call(
    public_id: str,
    request: Request,
    db: Db,
    signer: Signer,
    clock: ClockDep,
    serving: Serving,
    voice: Voice,
    ip: VisitorIp,
    authorization: Authorization = "",
) -> StartedCallOut | JSONResponse:
    """Starts a Call in the token's Conversation with the Agent's Live Version, which the Call
    records. Admission control runs first, as for a message (the rate limits and the Token
    Budget; the start counts against the rate limits), then the Call limits (one Call at a time
    in a Conversation, two at once for an IP address with the Agent, the day's Call minutes
    budget): a refusal is a 503 with the Agent's unavailable text and the reason, and so is a
    voice layer that can't start the Call; nothing is recorded then. The first refusal of a day
    for the Call minutes budget raises the Agent's alert and emails its Owners. An Agent with
    calling off refuses with a 409."""
    token = _bearer(authorization)
    unavailable = await service.unavailable_text(db, public_id)
    now = clock.now()
    try:
        started = await calls.start_call(
            db,
            signer,
            public_id,
            token,
            admission=serving.admission,
            voice=voice,
            ip=ip,
            now=now,
        )
    except service.InvalidTokenError:
        raise _invalid() from None
    except (AgentNotServedError, AgentNotLiveError):
        raise _gone() from None
    except calls.CallsOffError:
        raise HTTPException(status.HTTP_409_CONFLICT, CALLS_OFF) from None
    except service.NotAdmittedError as refused:
        if refused.reason is Refusal.TOKEN_BUDGET:
            await service.budget_exhausted(
                db, refused.agent_id, mailer=serving.mailer, studio_url=serving.studio_url, now=now
            )
            return _refused(unavailable, BUDGET_EXHAUSTED)
        return _refused(unavailable, RATE_LIMITED)
    except calls.CallNotAdmittedError as limited:
        if limited.reason is CallRefusal.MINUTES_SPENT:
            await call_limits.budget_spent(
                db, limited.agent_id, mailer=serving.mailer, studio_url=serving.studio_url, now=now
            )
        return _refused(unavailable, limited.reason)
    except VoiceLayerError:
        return _refused(unavailable, VOICE_UNAVAILABLE)
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
    operation_id="endWidgetCall",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_errors((401, INVALID_TOKEN)),
)
async def end_call(
    public_id: str, db: Db, signer: Signer, clock: ClockDep, authorization: Authorization = ""
) -> None:
    """Ends the token's Conversation's open Call, recording when it ended and adding its minutes
    (rounded up) to the Agent's Call minutes for the day; with no Call open, nothing changes.
    What was said stays in the Conversation as Spoken Messages."""
    try:
        await calls.end_call(db, signer, public_id, _bearer(authorization), now=clock.now())
    except service.InvalidTokenError:
        raise _invalid() from None


@router.post(
    "/current/interruptions",
    operation_id="interruptWidgetCall",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_errors((401, INVALID_TOKEN)),
)
async def interrupt_call(
    public_id: str, db: Db, signer: Signer, clock: ClockDep, authorization: Authorization = ""
) -> None:
    """The Visitor talked over the reply being spoken in the token's Conversation's open Call:
    that Agent Message is marked interrupted, and keeps its whole text. With no reply being
    spoken, nothing changes."""
    try:
        await calls.interrupt(db, signer, public_id, _bearer(authorization), now=clock.now())
    except service.InvalidTokenError:
        raise _invalid() from None
