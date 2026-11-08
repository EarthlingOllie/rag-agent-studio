"""Embed routes.

- ``GET /widget/a/{public_id}``: the widget shell, the HTML the Embed Snippet's iframe loads. Its
  ``Content-Security-Policy: frame-ancestors`` comes from the Agent's Allowed Origins, so
  browsers refuse to show it on other sites, and it carries a short-lived bootstrap token. An
  Agent that is archived, unknown or not live gets the "no longer available" shell instead.
- The widget API under ``/api/widget/agents/{public_id}``: exchange the bootstrap token for a
  Conversation token, then send messages with it (``Authorization: Bearer …``); each answer
  streams as Server-Sent Events from the Live Version. Visitors are anonymous: these routes take
  no Studio session. The iframe shares the API's origin (ADR-0011), so there is no CORS.
- The Studio's Operational Settings routes (Allowed Origins, the unavailable text, the rate
  limits and the Token Budget), for Editors and Owners. Changes apply on the next request and are
  audited. Beside them, today's usage against the Token Budget, for the Studio's meter.
"""

import html
import json
import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.agents.api import NOT_FOUND_RESPONSE, ClockDep, not_found
from app.agents.models import (
    CONVERSATION_RATE_MAX,
    IP_RATE_MAX,
    ORIGIN_MAX,
    TOKEN_BUDGET_MAX,
    UNAVAILABLE_TEXT_MAX,
)
from app.agents.service import AgentNotFoundError
from app.agents.serving import AgentNotLiveError, AgentNotServedError
from app.auth.api import Db, ErrorResponse
from app.core.client_ip import request_ip
from app.core.settings import Settings
from app.documents.ports import IngestionPorts
from app.embed import service
from app.embed.admission import Admission, Refusal
from app.embed.tokens import TokenSigner
from app.guardrails.pipeline import RefusalEvent
from app.mail.port import Mailer
from app.playground.api import QUESTION_MAX
from app.playground.service import Answered, NoDefaultModelError, answer
from app.projects.service import ProjectNotFoundError
from app.runtime.errors import ErrorEvent
from app.runtime.runtime import CitationEvent, ReplaceEvent, TokenEvent
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import Scope
from app.theme import images
from app.theme.resolve import font_stylesheet_url, theme_stylesheet, widget_theme

NO_LONGER_AVAILABLE = "This assistant is no longer available."
TEMPORARILY_UNAVAILABLE = service.DEFAULT_UNAVAILABLE_TEXT
# The `unavailable` event's reason when admission control refuses a message: a rate limit, or
# the day's Token Budget is spent.
RATE_LIMITED = "rate_limited"
BUDGET_EXHAUSTED = "budget_exhausted"
INVALID_TOKEN = "This chat has expired. Reload the page to start a new one."  # noqa: S105 (a message)
WIDGET_SCRIPT = "/widget/assets/widget.js"
IMAGES = ("avatar", "logo")


def get_signer(request: Request) -> TokenSigner:
    signer: TokenSigner = request.app.state.widget_tokens
    return signer


Signer = Annotated[TokenSigner, Depends(get_signer)]


def get_admission(request: Request) -> Admission:
    return Admission(request.app.state.redis, request.app.state.clock)


AdmissionDep = Annotated[Admission, Depends(get_admission)]


VisitorIp = Annotated[str, Depends(request_ip)]


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
                "Server-Sent Events. When admission control refuses the message, one "
                "`unavailable` event (`reason`: `budget_exhausted` when the Agent's daily "
                "Token Budget is spent, or `rate_limited` when the Conversation or the "
                "Visitor's IP address is over the Agent's rate limit; and as `message` the "
                "Agent's unavailable text); nothing is saved. Otherwise "
                "`token` events (`text`), then `citation` events "
                "(`label`, `document_name`, `passage`; only when the Live Version shows "
                "citations) and one `done` event (`message_id`); or, when the "
                "answer leaks the Canary token, a `replace` event (`text`) then `done`; or, "
                "when the input Guardrail blocks the message, a `refusal` event (`text`) then "
                "`done`, and no model is asked; or, when the model provider fails, one `error` "
                "event (`code`, and as `message` the Agent's unavailable text, which names no "
                "model or credential)."
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
    admission: AdmissionDep,
    ip: VisitorIp,
    authorization: Authorization = "",
) -> StreamingResponse:
    """Asks the Agent's Live Version a question in the token's Conversation. The answer is
    recorded against the Version that was Live when it was generated, and the tokens it used
    count against the Agent's daily Token Budget. Messages over the Agent's rate limits, per
    Conversation and per IP address, or once the day's budget is spent, get its unavailable
    text; the first refusal or reply that finds the budget spent raises the Agent's alert and
    emails its Owners, once per day."""
    token = _bearer(authorization)
    # The Agent's own words for "can't answer now", read on every request so a change applies
    # at once.
    unavailable = await service.unavailable_text(db, public_id)
    settings: Settings = request.app.state.settings
    mailer: Mailer = request.app.state.mailer
    studio_url = str(settings.studio_url)
    try:
        admitted = await service.prepare_turn(
            db, signer, public_id, token, body.content, admission=admission, ip=ip, now=clock.now()
        )
    except service.NotAdmittedError as refused:
        reason = RATE_LIMITED
        if refused.reason is Refusal.TOKEN_BUDGET:
            reason = BUDGET_EXHAUSTED
            await service.budget_exhausted(
                db, refused.agent_id, mailer=mailer, studio_url=studio_url, now=clock.now()
            )
        return _event_stream(_one(_sse("unavailable", {"reason": reason, "message": unavailable})))
    except service.InvalidTokenError:
        raise _invalid() from None
    except (AgentNotServedError, AgentNotLiveError):
        raise _gone() from None
    except NoDefaultModelError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, unavailable) from None
    ingestion: IngestionPorts = request.app.state.ingestion
    prepared = admitted.turn

    async def spent(event: Answered) -> None:
        # The reply's actual usage counts against today's Token Budget; the reply that spends
        # it raises the alert.
        used = event.event.input_tokens + event.event.output_tokens
        total = await admission.record_usage(admitted.limits.public_id, used)
        if total >= admitted.limits.daily_token_budget:
            async with request.app.state.sessionmaker() as session:
                await service.budget_exhausted(
                    session,
                    admitted.agent_id,
                    mailer=mailer,
                    studio_url=studio_url,
                    now=request.app.state.clock.now(),
                )

    async def events() -> AsyncIterator[str]:
        async for event in answer(
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
                # The event's message is written for Editors (it may name the model or say to
                # rotate the Provider Credential); Visitors get the Agent's unavailable text.
                yield _sse("error", {"code": event.kind, "message": unavailable})
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
                await spent(event)
                yield _sse("done", {"message_id": str(event.message_id)})

    return _event_stream(events())


async def _one(event: str) -> AsyncIterator[str]:
    yield event


def _event_stream(events: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class WidgetCitationOut(BaseModel):
    label: str
    # None when the Document has since been deleted.
    document_name: str | None


class WidgetFeedbackOut(BaseModel):
    rating: Literal["up", "down"]
    comment: str | None


class WidgetMessageOut(BaseModel):
    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    # The sources an answer cited; empty for the Visitor's own questions.
    citations: list[WidgetCitationOut]
    # The Visitor's thumbs on an answer (Message Feedback); null when none was given.
    feedback: WidgetFeedbackOut | None


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
                id=m.id,
                role=cast(Literal["user", "assistant"], m.role),
                content=m.content,
                citations=[
                    WidgetCitationOut(label=c.label, document_name=c.document_name)
                    for c in m.citations
                ],
                feedback=(
                    None
                    if m.feedback is None
                    else WidgetFeedbackOut(
                        rating=cast(Literal["up", "down"], m.feedback.rating),
                        comment=m.feedback.comment,
                    )
                ),
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


# Operational Settings, in the Studio


settings_router = APIRouter(
    prefix=ORGANISATION_PREFIX + "/projects/{project_id}/agents/{agent_id}", tags=["embed"]
)

Origin = Annotated[str, StringConstraints(max_length=ORIGIN_MAX * 2)]
UnavailableText = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=UNAVAILABLE_TEXT_MAX)
]
ConversationRate = Annotated[int, Field(ge=1, le=CONVERSATION_RATE_MAX)]
IpRate = Annotated[int, Field(ge=1, le=IP_RATE_MAX)]
TokenBudget = Annotated[int, Field(ge=1, le=TOKEN_BUDGET_MAX)]


class OperationalSettingsOut(BaseModel):
    # The sites whose pages may show the widget: `https://www.example.com`,
    # `https://*.example.com` (its subdomains), `http://localhost:8080`, `http://localhost:*`.
    allowed_origins: list[str]
    # What Visitors are told when the Agent can't answer.
    unavailable_text: str
    # Rate limits: how many messages a Visitor's Conversation, and an IP address, may send in
    # any one minute. Messages over the limit get the unavailable text instead of an answer.
    conversation_messages_per_minute: int
    ip_messages_per_minute: int
    # The Token Budget: how many tokens the Agent's Visitor replies may use per UTC date. Once
    # the day's usage reaches it, Visitors get the unavailable text until midnight UTC. The
    # Playground doesn't count.
    daily_token_budget: int


class OperationalSettingsChange(BaseModel):
    """The settings to change; one left out stays as it is."""

    allowed_origins: Annotated[list[Origin], Field(max_length=service.ORIGINS_MAX)] | None = None
    # Null or blank restores the default.
    unavailable_text: UnavailableText | None = None
    conversation_messages_per_minute: ConversationRate | None = None
    ip_messages_per_minute: IpRate | None = None
    daily_token_budget: TokenBudget | None = None

    @field_validator("conversation_messages_per_minute", "ip_messages_per_minute", mode="before")
    @classmethod
    def _a_limit_is_a_number(cls, value: object) -> object:
        # Leaving a limit out keeps it; there is no "no limit".
        if value is None:
            raise ValueError("A rate limit must be a whole number of messages.")
        return value

    @field_validator("daily_token_budget", mode="before")
    @classmethod
    def _a_budget_is_a_number(cls, value: object) -> object:
        # Leaving the budget out keeps it; there is no "no budget".
        if value is None:
            raise ValueError("The Token Budget must be a whole number of tokens.")
        return value


def _out(found: service.OperationalSettings) -> OperationalSettingsOut:
    return OperationalSettingsOut(
        allowed_origins=found.allowed_origins,
        unavailable_text=found.unavailable_text,
        conversation_messages_per_minute=found.conversation_messages_per_minute,
        ip_messages_per_minute=found.ip_messages_per_minute,
        daily_token_budget=found.daily_token_budget,
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
            conversation_messages_per_minute=body.conversation_messages_per_minute,
            ip_messages_per_minute=body.ip_messages_per_minute,
            daily_token_budget=body.daily_token_budget,
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


class TokenUsageOut(BaseModel):
    # The UTC date counted: today's.
    date: date
    # Tokens the Agent's Visitor replies have used today. The Playground doesn't count.
    tokens_used: int
    daily_token_budget: int
    # Whether today's budget is spent, so Visitors get the unavailable text.
    exhausted: bool
    # Midnight UTC, when a new day's budget starts.
    resets_at: datetime


@settings_router.get("/token-usage", operation_id="getTokenUsage", responses=NOT_FOUND_RESPONSE)
async def get_token_usage(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    scope: Scope,
    db: Db,
    clock: ClockDep,
    admission: AdmissionDep,
) -> TokenUsageOut:
    """Today's (UTC) Visitor usage against the Agent's Token Budget, for the Studio's meter."""
    try:
        found = await service.token_usage(
            db, scope, project_id, agent_id, admission=admission, now=clock.now()
        )
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
    return TokenUsageOut(
        date=found.date,
        tokens_used=found.tokens_used,
        daily_token_budget=found.daily_token_budget,
        exhausted=found.exhausted,
        resets_at=found.resets_at,
    )
