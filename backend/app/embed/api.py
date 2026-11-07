"""Embed routes.

- ``GET /widget/a/{public_id}``: the widget shell, the HTML the Embed Snippet's iframe loads. Its
  ``Content-Security-Policy: frame-ancestors`` comes from the Agent's Allowed Origins, so
  browsers refuse to show it on other sites, and it carries a short-lived bootstrap token. An
  Agent that is archived, unknown or not live gets the "no longer available" shell instead.
- The widget API under ``/api/widget/agents/{public_id}``: exchange the bootstrap token for a
  Conversation token, then send messages with it (``Authorization: Bearer …``); each answer
  streams as Server-Sent Events from the Live Version. Visitors are anonymous: these routes take
  no Studio session. The iframe shares the API's origin (ADR-0011), so there is no CORS.
- The Studio's Allowed Origins routes, for Editors and Owners.
"""

import html
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, StringConstraints

from app.agents.api import NOT_FOUND_RESPONSE, ClockDep, not_found
from app.agents.models import ORIGIN_MAX
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
from app.theme import images
from app.theme.resolve import font_stylesheet_url, theme_stylesheet, widget_theme

NO_LONGER_AVAILABLE = "This assistant is no longer available."
TEMPORARILY_UNAVAILABLE = "This assistant is temporarily unavailable. Please try again later."
INVALID_TOKEN = "This chat has expired. Reload the page to start a new one."  # noqa: S105 (a message)
WIDGET_SCRIPT = "/widget/assets/widget.js"
IMAGES = ("avatar", "logo")


def get_signer(request: Request) -> TokenSigner:
    signer: TokenSigner = request.app.state.widget_tokens
    return signer


Signer = Annotated[TokenSigner, Depends(get_signer)]


# The shell


shell_router = APIRouter()


def _json_for_script(data: dict[str, Any]) -> str:
    # Inside <script>, "</script>" or "<!--" in a value would end or confuse the element.
    return json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _page(title: str, body: str, head: str = "") -> str:
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n{head}</head>\n<body>\n{body}\n</body>\n</html>\n"
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
    experience = found.experience
    boot = _json_for_script(
        {
            "agent": found.public_id,
            "name": found.name,
            "bootstrap_token": found.bootstrap_token,
            "theme": widget_theme(found.theme),
            "logo_url": found.logo_url,
            "avatar_url": found.avatar_url,
            "greeting": experience.greeting,
            "starter_questions": experience.starter_questions,
            "ui_text": experience.ui_text.model_dump(mode="json"),
            "citations": found.citations,
        }
    )
    # The Theme's values are validated (hex colours, a whole radius, an allowlisted font), so
    # they can't close the <style> element.
    head = (
        f'<link rel="stylesheet" href="{html.escape(font_stylesheet_url(found.theme))}">\n'
        f'<style id="widget-theme">{theme_stylesheet(found.theme, "#root")}</style>\n'
    )
    return HTMLResponse(
        _page(
            found.name,
            '<div id="root"></div>\n'
            f'<script id="widget-boot" type="application/json">{boot}</script>\n'
            f'<script type="module" src="{WIDGET_SCRIPT}"></script>',
            head,
        ),
        headers={
            **_HEADERS,
            "Content-Security-Policy": service.frame_ancestors(found.allowed_origins),
        },
    )


@shell_router.get("/widget/a/{public_id}/{kind}", include_in_schema=False)
async def widget_image(public_id: str, kind: str, db: Db, request: Request) -> Response:
    """The widget's avatar or logo, for Visitors: no Studio session."""
    try:
        image = await service.widget_image(db, public_id, kind) if kind in IMAGES else None
        if image is None:
            raise images.ImageNotFoundError
        found = await images.read_stored(request.app.state.ingestion.object_store, image)
    except (AgentNotServedError, AgentNotLiveError, images.ImageNotFoundError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.") from None
    return Response(
        found.data,
        media_type=found.content_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            # The URL carries the image's content hash, so it always names the same bytes.
            "Cache-Control": "public, max-age=31536000, immutable",
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


def _bearer(authorization: str) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _invalid()
    return token.strip()


Authorization = Annotated[str, Header(description="`Bearer <conversation token>`")]


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
                "(`label`, `document_name`, `passage`; only when the Live Version shows "
                "citations) and one `done` event (`message_id`); or, when the "
                "answer leaks the Canary token, a `replace` event (`text`) then `done`; or, "
                "when the model provider fails, one `error` event (`code`, and a `message` for "
                "Visitors that names no model or credential)."
            ),
        },
        **_errors((401, INVALID_TOKEN), (404, NO_LONGER_AVAILABLE), (503, TEMPORARILY_UNAVAILABLE)),
    },
)
async def send_message(
    request: Request,
    public_id: str,
    body: WidgetMessageRequest,
    db: Db,
    signer: Signer,
    clock: ClockDep,
    authorization: Authorization = "",
) -> StreamingResponse:
    """Asks the Agent's Live Version a question in the token's Conversation. The answer is
    recorded against the Version that was Live when it was generated."""
    token = _bearer(authorization)
    try:
        prepared = await service.prepare_turn(
            db, signer, public_id, token, body.content, now=clock.now()
        )
    except service.InvalidTokenError:
        raise _invalid() from None
    except (AgentNotServedError, AgentNotLiveError):
        raise _gone() from None
    except NoDefaultModelError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, TEMPORARILY_UNAVAILABLE) from None
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
                # rotate the Provider Credential); Visitors get the generic one.
                yield _sse("error", {"code": event.kind, "message": TEMPORARILY_UNAVAILABLE})
            elif isinstance(event, CitationEvent):
                # Only when the Live Version shows citations to Visitors.
                if prepared.config.retrieval.citations:
                    yield _sse(
                        "citation",
                        {
                            "label": event.label,
                            "document_name": event.chunk.document_name,
                            "passage": event.chunk.text,
                        },
                    )
            else:
                yield _sse("done", {"message_id": str(event.message_id)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class WidgetCitationOut(BaseModel):
    label: str
    # None when the Document has since been deleted.
    document_name: str | None


class WidgetMessageOut(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    # The sources an answer cited; empty for the Visitor's own questions.
    citations: list[WidgetCitationOut]


class WidgetConversationOut(BaseModel):
    messages: list[WidgetMessageOut]


@widget_router.get(
    "/conversation",
    operation_id="getWidgetConversation",
    responses=_errors((401, INVALID_TOKEN), (404, NO_LONGER_AVAILABLE)),
)
async def get_conversation(
    public_id: str, db: Db, signer: Signer, clock: ClockDep, authorization: Authorization = ""
) -> WidgetConversationOut:
    """The token's Conversation, for a Visitor who comes back to the page: its Messages in
    order, each answer with its sources. Coming back counts as activity, so the token's
    24-hour window slides on; after 24 hours without activity the token is refused."""
    try:
        messages = await service.resume(
            db, signer, public_id, _bearer(authorization), now=clock.now()
        )
    except service.InvalidTokenError:
        raise _invalid() from None
    except (AgentNotServedError, AgentNotLiveError):
        raise _gone() from None
    return WidgetConversationOut(
        messages=[
            WidgetMessageOut(
                role=cast(Literal["user", "assistant"], m.role),
                content=m.content,
                citations=[
                    WidgetCitationOut(label=c.label, document_name=c.document_name)
                    for c in m.citations
                ],
            )
            for m in messages
        ]
    )


@widget_router.delete(
    "/conversation",
    operation_id="endWidgetConversation",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_errors((401, INVALID_TOKEN)),
)
async def end_conversation(
    public_id: str, db: Db, signer: Signer, clock: ClockDep, authorization: Authorization = ""
) -> None:
    """Ends the token's Conversation: the token is refused from then on. The Visitor's next
    question starts a new Conversation."""
    try:
        await service.end(db, signer, public_id, _bearer(authorization), now=clock.now())
    except service.InvalidTokenError:
        raise _invalid() from None


# Allowed Origins, in the Studio


origins_router = APIRouter(
    prefix=ORGANISATION_PREFIX + "/projects/{project_id}/agents/{agent_id}", tags=["embed"]
)

Origin = Annotated[str, StringConstraints(max_length=ORIGIN_MAX * 2)]


class AllowedOriginsIn(BaseModel):
    # Each a scheme, host and optional port: `https://www.example.com`, `http://localhost:8080`.
    origins: Annotated[list[Origin], Field(max_length=service.ORIGINS_MAX)]


class AllowedOriginsOut(BaseModel):
    origins: list[str]


@origins_router.get(
    "/allowed-origins", operation_id="getAllowedOrigins", responses=NOT_FOUND_RESPONSE
)
async def get_allowed_origins(
    project_id: uuid.UUID, agent_id: uuid.UUID, scope: Scope, db: Db
) -> AllowedOriginsOut:
    """The sites whose pages may show the Agent's widget."""
    try:
        origins = await service.allowed_origins(db, scope, project_id, agent_id)
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
    return AllowedOriginsOut(origins=origins)


@origins_router.put(
    "/allowed-origins", operation_id="setAllowedOrigins", responses=NOT_FOUND_RESPONSE
)
async def set_allowed_origins(
    project_id: uuid.UUID, agent_id: uuid.UUID, body: AllowedOriginsIn, scope: Scope, db: Db
) -> AllowedOriginsOut:
    """Replaces the Agent's Allowed Origins; the widget's next page load uses them, without
    publishing."""
    try:
        origins = await service.set_allowed_origins(db, scope, project_id, agent_id, body.origins)
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
    except service.InvalidOriginError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [
                {
                    "loc": ["body", "origins", error.index],
                    "msg": (
                        f"{error.origin!r} isn't a site address. Use a scheme, host and optional "
                        "port, such as https://www.example.com or http://localhost:8080."
                    ),
                    "type": "value_error",
                }
            ],
        ) from None
    return AllowedOriginsOut(origins=origins)
