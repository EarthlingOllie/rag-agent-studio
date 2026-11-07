"""Embed routes.

- ``GET /widget/a/{public_id}``: the widget shell, the HTML the Embed Snippet's iframe loads. Its
  ``Content-Security-Policy: frame-ancestors`` comes from the Agent's Allowed Origins, so
  browsers refuse to show it on other sites, and it carries a short-lived bootstrap token. An
  Agent that is archived, unknown or not live gets the "no longer available" shell instead.
- The widget API under ``/api/widget/agents/{public_id}``: exchange the bootstrap token for a
  Conversation token, then send messages with it (``Authorization: Bearer …``); each answer
  streams as Server-Sent Events from the Live Version. Visitors are anonymous: these routes take
  no Studio session. The iframe shares the API's origin (ADR-0011), so there is no CORS.
- The Studio's Operational Settings routes (Allowed Origins and the unavailable text), for
  Editors and Owners. Changes apply on the next request and are audited.
"""

import html
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field, StringConstraints

from app.agents.api import NOT_FOUND_RESPONSE, ClockDep, not_found
from app.agents.models import ORIGIN_MAX, UNAVAILABLE_TEXT_MAX
from app.agents.service import AgentNotFoundError
from app.agents.serving import AgentNotLiveError, AgentNotServedError
from app.auth.api import Db, ErrorResponse
from app.documents.ports import IngestionPorts
from app.embed import service
from app.embed.tokens import TokenSigner
from app.playground.api import QUESTION_MAX
from app.playground.service import NoDefaultModelError, answer
from app.projects.service import ProjectNotFoundError
from app.runtime.errors import ErrorEvent
from app.runtime.runtime import CitationEvent, ReplaceEvent, TokenEvent
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import Scope

NO_LONGER_AVAILABLE = "This assistant is no longer available."
TEMPORARILY_UNAVAILABLE = service.DEFAULT_UNAVAILABLE_TEXT
INVALID_TOKEN = "This chat has expired. Reload the page to start a new one."  # noqa: S105 (a message)
WIDGET_SCRIPT = "/widget/assets/widget.js"


def get_signer(request: Request) -> TokenSigner:
    signer: TokenSigner = request.app.state.widget_tokens
    return signer


Signer = Annotated[TokenSigner, Depends(get_signer)]


# The shell


shell_router = APIRouter()


def _json_for_script(data: dict[str, str]) -> str:
    # Inside <script>, "</script>" or "<!--" in a value would end or confuse the element.
    return json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _page(title: str, body: str) -> str:
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


@shell_router.get("/widget/a/{public_id}", include_in_schema=False)
async def widget_shell(public_id: str, db: Db, signer: Signer, clock: ClockDep) -> HTMLResponse:
    try:
        found = await service.shell(db, signer, public_id, now=clock.now())
    except (AgentNotServedError, AgentNotLiveError):
        # Nothing about the Agent is in this page, so any site may show it.
        return HTMLResponse(
            _page("Unavailable", f'<p role="status">{NO_LONGER_AVAILABLE}</p>'),
            status_code=status.HTTP_404_NOT_FOUND,
            headers={**_HEADERS, "Content-Security-Policy": "frame-ancestors *"},
        )
    boot = _json_for_script(
        {"agent": found.public_id, "name": found.name, "bootstrap_token": found.bootstrap_token}
    )
    return HTMLResponse(
        _page(
            found.name,
            '<div id="root"></div>\n'
            f'<script id="widget-boot" type="application/json">{boot}</script>\n'
            f'<script type="module" src="{WIDGET_SCRIPT}"></script>',
        ),
        headers={
            **_HEADERS,
            "Content-Security-Policy": service.frame_ancestors(found.allowed_origins),
        },
    )


# The widget API


widget_router = APIRouter(prefix="/api/widget/agents/{public_id}", tags=["widget"])


def _errors(*codes: tuple[int, str]) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ErrorResponse, "description": text} for code, text in codes}


class StartConversationRequest(BaseModel):
    bootstrap_token: Annotated[str, StringConstraints(max_length=1000)]


class ConversationTokenOut(BaseModel):
    # Sent as `Authorization: Bearer <token>` with each message.
    conversation_token: str


def _gone() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, NO_LONGER_AVAILABLE)


def _invalid() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_TOKEN)


@widget_router.post(
    "/conversations",
    operation_id="startWidgetConversation",
    status_code=status.HTTP_201_CREATED,
    responses=_errors((401, INVALID_TOKEN), (404, NO_LONGER_AVAILABLE)),
)
async def start_conversation(
    public_id: str, body: StartConversationRequest, db: Db, signer: Signer, clock: ClockDep
) -> ConversationTokenOut:
    """Exchanges the shell's bootstrap token for a new Conversation and its Conversation
    token."""
    try:
        token = await service.start_conversation(
            db, signer, public_id, body.bootstrap_token, now=clock.now()
        )
    except service.InvalidTokenError:
        raise _invalid() from None
    except (AgentNotServedError, AgentNotLiveError):
        raise _gone() from None
    return ConversationTokenOut(conversation_token=token)


class WidgetMessageRequest(BaseModel):
    content: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=QUESTION_MAX)
    ]


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@widget_router.post(
    "/messages",
    operation_id="sendWidgetMessage",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
            "description": (
                "Server-Sent Events: `token` events (`text`), then `citation` events "
                "(`label`, `document_name`) and one `done` event (`message_id`); or, when the "
                "answer leaks the Canary token, a `replace` event (`text`) then `done`; or, "
                "when the model provider fails, one `error` event (`code`, and as `message` the "
                "Agent's unavailable text, which names no model or credential)."
            ),
        },
        **_errors(
            (401, INVALID_TOKEN),
            (404, NO_LONGER_AVAILABLE),
            (503, "The Agent's unavailable text: it has no model to answer with."),
        ),
    },
)
async def send_message(
    request: Request,
    public_id: str,
    body: WidgetMessageRequest,
    db: Db,
    signer: Signer,
    clock: ClockDep,
    authorization: Annotated[str, Header(description="`Bearer <conversation token>`")] = "",
) -> StreamingResponse:
    """Asks the Agent's Live Version a question in the token's Conversation. The answer is
    recorded against the Version that was Live when it was generated."""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _invalid()
    # The Agent's own words for "can't answer now", read on every request so a change applies
    # at once.
    unavailable = await service.unavailable_text(db, public_id)
    try:
        prepared = await service.prepare_turn(
            db, signer, public_id, token.strip(), body.content, now=clock.now()
        )
    except service.InvalidTokenError:
        raise _invalid() from None
    except (AgentNotServedError, AgentNotLiveError):
        raise _gone() from None
    except NoDefaultModelError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, unavailable) from None
    ingestion: IngestionPorts = request.app.state.ingestion

    async def events() -> AsyncIterator[str]:
        async for event in answer(
            prepared,
            sessionmaker=request.app.state.sessionmaker,
            gateway=request.app.state.model_gateway,
            embedders=ingestion.embedders,
            clock=request.app.state.clock,
        ):
            if isinstance(event, TokenEvent):
                yield _sse("token", {"text": event.text})
            elif isinstance(event, ReplaceEvent):
                yield _sse("replace", {"text": event.text})
            elif isinstance(event, ErrorEvent):
                # The event's message is written for Editors (it may name the model or say to
                # rotate the Provider Credential); Visitors get the Agent's unavailable text.
                yield _sse("error", {"code": event.kind, "message": unavailable})
            elif isinstance(event, CitationEvent):
                yield _sse(
                    "citation",
                    {"label": event.label, "document_name": event.chunk.document_name},
                )
            else:
                yield _sse("done", {"message_id": str(event.message_id)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Operational Settings, in the Studio


settings_router = APIRouter(
    prefix=ORGANISATION_PREFIX + "/projects/{project_id}/agents/{agent_id}", tags=["embed"]
)

Origin = Annotated[str, StringConstraints(max_length=ORIGIN_MAX * 2)]
UnavailableText = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=UNAVAILABLE_TEXT_MAX)
]


class OperationalSettingsOut(BaseModel):
    # The sites whose pages may show the widget: `https://www.example.com`,
    # `https://*.example.com` (its subdomains), `http://localhost:8080`, `http://localhost:*`.
    allowed_origins: list[str]
    # What Visitors are told when the Agent can't answer.
    unavailable_text: str


class OperationalSettingsChange(BaseModel):
    """The settings to change; one left out stays as it is."""

    allowed_origins: Annotated[list[Origin], Field(max_length=service.ORIGINS_MAX)] | None = None
    # Null or blank restores the default.
    unavailable_text: UnavailableText | None = None


def _out(found: service.OperationalSettings) -> OperationalSettingsOut:
    return OperationalSettingsOut(
        allowed_origins=found.allowed_origins, unavailable_text=found.unavailable_text
    )


@settings_router.get(
    "/operational-settings", operation_id="getOperationalSettings", responses=NOT_FOUND_RESPONSE
)
async def get_operational_settings(
    project_id: uuid.UUID, agent_id: uuid.UUID, scope: Scope, db: Db
) -> OperationalSettingsOut:
    """The Agent's Operational Settings: not part of its Draft or Versions."""
    try:
        found = await service.operational_settings(db, scope, project_id, agent_id)
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
    return _out(found)


@settings_router.patch(
    "/operational-settings",
    operation_id="changeOperationalSettings",
    responses=NOT_FOUND_RESPONSE,
)
async def change_operational_settings(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: OperationalSettingsChange,
    scope: Scope,
    db: Db,
    clock: ClockDep,
) -> OperationalSettingsOut:
    """Changes the settings given. The next request uses them, without publishing, and the
    change is recorded as an Audit Event with the before and after values."""
    blank_text = "unavailable_text" in body.model_fields_set and body.unavailable_text is None
    try:
        found = await service.change_operational_settings(
            db,
            scope,
            project_id,
            agent_id,
            allowed_origins=body.allowed_origins,
            unavailable_text="" if blank_text else body.unavailable_text,
            now=clock.now(),
        )
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
    except service.InvalidOriginError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [
                {
                    "loc": ["body", "allowed_origins", error.index],
                    "msg": (
                        f"{error.origin!r} isn't a site address. Use a scheme, host and optional "
                        "port, such as https://www.example.com, https://*.example.com for its "
                        "subdomains, or http://localhost:8080 (http://localhost:* for any port)."
                    ),
                    "type": "value_error",
                }
            ],
        ) from None
    return _out(found)
