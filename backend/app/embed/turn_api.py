"""The turn endpoint (spec 20, ADR-0019): the OpenAI-compatible chat completions route the voice
layer calls as its custom LLM for every turn of a Call, under the Agent's public ID
(``…/llm/v1/chat/completions``).

The voice layer sends the Agent's per-Agent secret as the API key and the Call token in the
extra body the widget gave it (``elevenlabs_extra_body.call_token``). A turn with a wrong
secret, or a Call token that is tampered with, expired, for another Conversation or Agent, or
for a Call that has ended, is refused before anything is answered.

Only the last user message is taken, as the Visitor's words; the history the voice layer sends
is ignored, since the Conversation holds every earlier turn, typed or spoken. The words are
served exactly as a typed widget message is (``app.embed.visitor_turn.serve_turn``), so the
reply has its Trace, Cost and Message attribution, and both sides are saved as Spoken Messages
of the Call. The reply streams back as OpenAI chat completion chunks over Server-Sent Events.
"""

import json
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.agents.api import ClockDep
from app.agents.resolution import NoDefaultModelError, ProviderCredentialGoneError
from app.agents.serving import AgentNotLiveError, AgentNotServedError
from app.auth.api import Db
from app.embed import calls, service
from app.embed.api import NO_LONGER_AVAILABLE, Serving, Signer, _errors, _event_stream, _gone
from app.embed.visitor_turn import Unavailable, VisitorTurnEvent, serve_turn
from app.guardrails.pipeline import RefusalEvent
from app.playground.api import QUESTION_MAX
from app.runtime.errors import ErrorEvent
from app.runtime.runtime import ReplaceEvent, TokenEvent
from app.voice.api import Voice

router = APIRouter(prefix="/api/widget/agents/{public_id}/llm/v1", tags=["widget"])

INVALID_SECRET = "The API key isn't this Agent's."  # noqa: S105 (a message)
INVALID_CALL = "The Call token is invalid or expired, or the Call has ended."
NO_WORDS = "The last user message has no words."
TOO_LONG = f"The last user message is longer than {QUESTION_MAX} characters."
# The model name the chunks report: the Agent answers, not a model the voice layer chose.
MODEL = "rag-agent-studio"


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str
    # Text, or OpenAI content parts (only `text` parts count).
    content: str | list[dict[str, Any]] | None = None


class VoiceLayerExtraBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    call_token: Annotated[str, StringConstraints(max_length=1000)] = ""


class ChatCompletionRequest(BaseModel):
    """An OpenAI chat completions request. Only the last user message and the Call token count;
    the model, the history and any other options are ignored."""

    model_config = ConfigDict(extra="ignore")

    messages: list[ChatMessage]
    elevenlabs_extra_body: VoiceLayerExtraBody | None = None


def _text(content: str | list[dict[str, Any]] | None) -> str:
    if isinstance(content, list):
        return "".join(str(part.get("text", "")) for part in content if part.get("type") == "text")
    return content or ""


def _words(messages: list[ChatMessage]) -> str:
    """The Visitor's words: the last user message's text."""
    users = [m for m in messages if m.role == "user"]
    words = _text(users[-1].content).strip() if users else ""
    if not words:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NO_WORDS)
    if len(words) > QUESTION_MAX:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, TOO_LONG)
    return words


def _chunk(completion: str, created: int, content: str | None) -> str:
    delta: dict[str, str] = {} if content is None else {"role": "assistant", "content": content}
    choice: dict[str, Any] = {
        "index": 0,
        "delta": delta,
        "finish_reason": "stop" if content is None else None,
    }
    data = {
        "id": completion,
        "object": "chat.completion.chunk",
        "created": created,
        "model": MODEL,
        "choices": [choice],
    }
    return f"data: {json.dumps(data)}\n\n"


def _spoken(event: VisitorTurnEvent, unavailable: str) -> str | None:
    """What the voice layer speaks for one event of the turn, or None for nothing: sources and
    the Searching status are not read out."""
    if isinstance(event, TokenEvent | ReplaceEvent | RefusalEvent):
        return event.text
    if isinstance(event, Unavailable | ErrorEvent):
        return unavailable
    return None


_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
        "description": (
            "Server-Sent Events, as OpenAI streams chat completions: `chat.completion.chunk` "
            "objects whose `choices[0].delta.content` is the text to speak (the reply, the "
            "Agent's refusal or replacement text, or its unavailable text), then one with "
            "`finish_reason` `stop`, then `[DONE]`."
        ),
    },
    **_errors(
        (401, INVALID_SECRET),
        (403, INVALID_CALL),
        (404, NO_LONGER_AVAILABLE),
        (503, "The Agent's unavailable text: it has no model to answer with."),
    ),
}


@router.post(
    "/chat/completions",
    operation_id="answerCallTurn",
    response_class=StreamingResponse,
    responses=_RESPONSES,
)
async def chat_completions(
    public_id: str,
    body: ChatCompletionRequest,
    db: Db,
    signer: Signer,
    clock: ClockDep,
    serving: Serving,
    voice: Voice,
    authorization: Annotated[str, Header(description="`Bearer <the Agent's secret>`")] = "",
) -> StreamingResponse:
    """Answers one turn of a Call, for the voice layer. The Visitor's words (the last user
    message) are answered by the Agent's Live Version as a typed widget message is, with the
    earlier turns of the Conversation as history, and saved with the reply as Spoken Messages
    of the Call."""
    scheme, _, secret = authorization.partition(" ")
    call_token = "" if body.elevenlabs_extra_body is None else body.elevenlabs_extra_body.call_token
    try:
        found = await calls.turn_call(
            db,
            signer,
            voice,
            public_id,
            secret.strip() if scheme.lower() == "bearer" else "",
            call_token,
            now=clock.now(),
        )
    except calls.InvalidSecretError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_SECRET) from None
    except calls.InvalidCallError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, INVALID_CALL) from None
    words = _words(body.messages)
    unavailable = await service.unavailable_text(db, public_id)
    try:
        turn = await serve_turn(
            db,
            found.agent,
            found.conversation,
            words,
            found.call.ip,
            ports=serving,
            call_id=found.call.id,
        )
    except (AgentNotServedError, AgentNotLiveError):
        raise _gone() from None
    except (NoDefaultModelError, ProviderCredentialGoneError):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, unavailable) from None
    completion = f"chatcmpl-{found.call.id.hex}-{time.monotonic_ns()}"
    created = int(clock.now().timestamp())

    async def chunks() -> AsyncIterator[str]:
        async for event in turn:
            spoken = _spoken(event, unavailable)
            if spoken:
                yield _chunk(completion, created, spoken)
        yield _chunk(completion, created, None)
        yield "data: [DONE]\n\n"

    return _event_stream(chunks())
