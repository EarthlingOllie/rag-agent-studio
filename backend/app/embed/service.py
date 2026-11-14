"""Embedding rules: an Agent's Operational Settings (its Allowed Origins, unavailable text, rate
limits and Token Budget), the Token Budget's alert, the shell's framing policy, and Visitors'
Conversations, which are reached only through their Conversation token.

Operational Settings are not part of any Draft or Version (ADR-0009): they are edited here, apply
on the next request without publishing, and every change is an Audit Event with the before and
after values of the settings it changed.
"""

import re
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time, timedelta
from datetime import date as date_type
from typing import cast

from publicsuffixlist import PublicSuffixList
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.agents import serving
from app.agents.config import Experience
from app.agents.models import ORIGIN_MAX, Agent
from app.agents.service import active_agent, get_agent
from app.conversations.models import Conversation, Message, MessageRetrieval
from app.documents.models import Document
from app.embed.admission import Admission, Limits, Refusal, Reservation, utc_date
from app.embed.branding import override_of
from app.embed.tokens import TokenSigner, expired, token_hash
from app.feedback.models import MessageFeedback
from app.feedback.service import RatingState, feedback_on, rating_state
from app.mail import templates
from app.mail.port import Mailer
from app.playground.service import PreparedTurn
from app.projects.service import active_project
from app.runtime.prompt import chunk_label
from app.tenancy.models import Member, Membership, Role
from app.tenancy.repository import OrganisationScope
from app.theme.resolve import with_colours
from app.theme.schema import ThemeSettings
from app.theme.service import StoredImage, ThemeImageKind, organisation_theme

ORIGINS_MAX = 50
DEFAULT_UNAVAILABLE_TEXT = "This assistant is temporarily unavailable. Please try again later."
OPERATIONAL_SETTINGS_CHANGED = "agent.operational_settings_changed"

_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
# A host; or a subdomain wildcard over a named site of at least two labels (``*.example.com``,
# never ``*.com``); or IPv6 loopback. The port is a number or, for this machine only, ``*``.
_ORIGIN = re.compile(
    rf"https?://(?P<host>{_LABEL}(?:\.{_LABEL})*|\*\.{_LABEL}(?:\.{_LABEL})+|\[::1\])"
    r"(?::(?P<port>[0-9]{1,5}|\*))?"
)
# The developer's own machine, where any port may be allowed.
_LOOPBACK = frozenset({"localhost", "127.0.0.1", "[::1]"})
# The Public Suffix List snapshot bundled with the package: read from disk, never fetched.
_PUBLIC_SUFFIXES = PublicSuffixList()


def _over_public_suffix(host: str) -> bool:
    """Whether ``host`` is a wildcard over a public suffix (``*.co.uk``, ``*.github.io``),
    which would let every site registered under that suffix in."""
    return host.startswith("*.") and bool(_PUBLIC_SUFFIXES.is_public(host[2:]))


class InvalidOriginError(Exception):
    def __init__(self, index: int, origin: str) -> None:
        super().__init__(origin)
        self.index = index
        self.origin = origin


def _valid(origin: str) -> bool:
    found = _ORIGIN.fullmatch(origin)
    if found is None or len(origin) > ORIGIN_MAX or _over_public_suffix(found["host"]):
        return False
    port = found["port"]
    if port == "*":
        return found["host"] in _LOOPBACK
    return port is None or 0 < int(port) < 65536


def normalise_origins(origins: list[str]) -> list[str]:
    """The origins, lower-cased, without a trailing slash and without repeats, in order; an
    entry that isn't an origin raises ``InvalidOriginError``.

    An origin is ``http`` or ``https``, a host and an optional port, with no path. The host may
    start with a subdomain wildcard (``https://*.example.com``, any subdomain of example.com but
    not example.com itself) over a named site, never over a public suffix such as ``co.uk`` or
    ``github.io`` (the Public Suffix List). Localhost (``localhost``, ``127.0.0.1``, ``[::1]``)
    may take any port with ``:*``, for development.
    """
    found: list[str] = []
    for index, raw in enumerate(origins):
        origin = raw.strip().lower().removesuffix("/")
        if not _valid(origin):
            raise InvalidOriginError(index, raw)
        if origin not in found:
            found.append(origin)
    return found


# An origin as a browser sends it in ``Origin``: scheme, host and optional port.
_REQUEST_ORIGIN = re.compile(
    r"(?P<scheme>https?)://(?P<host>\[[0-9a-f:.]+\]|[^:/\[\]]+)(?::(?P<port>[0-9]{1,5}))?"
)


def _parts(origin: str) -> tuple[str, str, str | None] | None:
    found = _REQUEST_ORIGIN.fullmatch(origin.strip().lower().removesuffix("/"))
    return None if found is None else (found["scheme"], found["host"], found["port"])


def origin_allowed(origin: str, allowed: list[str]) -> bool:
    """Whether a browser's origin is one of the Allowed Origins (``normalise_origins``' forms:
    an exact origin, a subdomain wildcard, or a loopback host with any port). A wildcard over a
    public suffix, stored before those were refused, lets nobody in."""
    request = _parts(origin)
    if request is None:
        return False
    scheme, host, port = request
    for rule in allowed:
        # Allowed Origins are stored normalised, so each one matches ``_ORIGIN``.
        if not rule.startswith(f"{scheme}://") or (found := _ORIGIN.fullmatch(rule)) is None:
            continue
        rule_host, rule_port = found["host"], found["port"]
        if _over_public_suffix(rule_host):
            continue
        if rule_host.startswith("*."):
            host_matches = host.endswith(rule_host[1:])
        else:
            host_matches = host == rule_host
        if host_matches and rule_port in ("*", port):
            return True
    return False


async def allowed_origins(session: AsyncSession, public_id: str) -> list[str]:
    """The Agent's Allowed Origins; none for an Agent that doesn't exist."""
    found = await session.scalar(select(Agent.allowed_origins).where(Agent.public_id == public_id))
    return [] if found is None else list(found)


# Where the widget shell may load images from: its own origin (the hosted avatar and logo) and
# inline images, never an external host.
WIDGET_IMG_SRC = "img-src 'self' data: blob:"


def frame_ancestors(origins: list[str]) -> str:
    """The ``Content-Security-Policy`` that lets only those origins frame the widget; a stored
    wildcard over a public suffix is left out, as ``origin_allowed`` ignores it."""
    framing = [
        origin
        for origin in origins
        if (found := _ORIGIN.fullmatch(origin)) is None or not _over_public_suffix(found["host"])
    ]
    return "frame-ancestors " + (" ".join(framing) if framing else "'none'")


@dataclass(frozen=True)
class OperationalSettings:
    allowed_origins: list[str]
    # What Visitors are told when the Agent can't answer.
    unavailable_text: str
    # Rate limits: Visitor messages admitted in any minute per Conversation and per IP address.
    conversation_messages_per_minute: int
    ip_messages_per_minute: int
    # Tokens the Agent's Visitor replies may use per UTC date.
    daily_token_budget: int


def _settings_of(agent: Agent) -> OperationalSettings:
    return OperationalSettings(
        allowed_origins=list(agent.allowed_origins),
        unavailable_text=agent.unavailable_text or DEFAULT_UNAVAILABLE_TEXT,
        conversation_messages_per_minute=agent.conversation_messages_per_minute,
        ip_messages_per_minute=agent.ip_messages_per_minute,
        daily_token_budget=agent.daily_token_budget,
    )


async def operational_settings(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, agent_id: uuid.UUID
) -> OperationalSettings:
    return _settings_of((await get_agent(session, scope, project_id, agent_id)).agent)


async def change_operational_settings(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    allowed_origins: list[str] | None = None,
    unavailable_text: str | None = None,
    conversation_messages_per_minute: int | None = None,
    ip_messages_per_minute: int | None = None,
    daily_token_budget: int | None = None,
    now: datetime,
) -> OperationalSettings:
    """Changes the settings given (``None`` leaves one as it is; a blank ``unavailable_text``
    restores the default). The next request uses them. A change is recorded as an
    ``agent.operational_settings_changed`` Audit Event holding the before and after values of
    the settings that changed; a save that changes nothing records nothing. Raises
    ``ProjectArchivedError`` or ``AgentArchivedError`` while the Project or Agent is archived."""
    origins = None if allowed_origins is None else normalise_origins(allowed_origins)
    # An archived Agent, or one in an archived Project, is read-only until it is restored.
    await active_project(session, scope, project_id)
    agent = (await active_agent(session, scope, project_id, agent_id, lock=True)).agent
    before = asdict(_settings_of(agent))
    if origins is not None:
        agent.allowed_origins = origins
    if unavailable_text is not None:
        agent.unavailable_text = unavailable_text.strip() or None
    if conversation_messages_per_minute is not None:
        agent.conversation_messages_per_minute = conversation_messages_per_minute
    if ip_messages_per_minute is not None:
        agent.ip_messages_per_minute = ip_messages_per_minute
    if daily_token_budget is not None:
        agent.daily_token_budget = daily_token_budget
    after = asdict(_settings_of(agent))
    changed = [key for key in before if before[key] != after[key]]
    if changed:
        await audit.record(
            session,
            organisation_id=scope.organisation_id,
            actor_id=scope.member_id,
            action=OPERATIONAL_SETTINGS_CHANGED,
            target=audit.AuditTarget("agent", agent.id),
            before={key: before[key] for key in changed},
            after={key: after[key] for key in changed},
            occurred_at=now,
        )
    await session.commit()
    return _settings_of(agent)


async def unavailable_text(session: AsyncSession, public_id: str) -> str:
    """What Visitors of the Agent are told when it can't answer."""
    text = await session.scalar(select(Agent.unavailable_text).where(Agent.public_id == public_id))
    return text or DEFAULT_UNAVAILABLE_TEXT


@dataclass(frozen=True)
class Shell:
    public_id: str
    # The name Visitors see: the Live Version's display name, or else the Agent's name.
    name: str
    allowed_origins: list[str]
    bootstrap_token: str
    # The Organisation's Theme with the Agent's colour override applied.
    theme: ThemeSettings
    # The public Experience of the Live Version.
    experience: Experience
    citations: bool
    # Where the widget fetches the Agent's avatar and the Theme's logo, or None.
    avatar_url: str | None
    logo_url: str | None


def _image_url(public_id: str, kind: str, image: StoredImage) -> str:
    # The content hash names the bytes, so the image can be cached for good.
    return f"/widget/a/{public_id}/{kind}?v={image.content_hash[:16]}"


async def shell(
    session: AsyncSession, signer: TokenSigner, public_id: str, *, now: datetime
) -> Shell:
    """What the widget shell needs; raises ``serving.AgentNotServedError`` or
    ``serving.AgentNotLiveError`` when the Agent can't be served."""
    found = await serving.live_agent(session, public_id)
    theme = await organisation_theme(session, found.agent.organisation_id)
    experience = found.live.config.experience
    override = override_of(found.agent)
    public_id = found.agent.public_id
    # The Agent's own avatar, else the Theme's default avatar: hosted images only. A Version's
    # external ``experience.avatar_url`` is never served, so no Visitor's browser fetches a URL
    # an Editor chose (the shell's ``img-src`` refuses other origins too).
    avatar = override.avatar or theme.images[ThemeImageKind.AVATAR]
    avatar_url = None if avatar is None else _image_url(public_id, "avatar", avatar)
    logo = theme.images[ThemeImageKind.LOGO]
    return Shell(
        public_id=found.agent.public_id,
        name=experience.display_name or found.agent.name,
        allowed_origins=found.agent.allowed_origins,
        bootstrap_token=signer.bootstrap(found.agent.public_id, now=now),
        theme=with_colours(theme.settings, override.colours),
        experience=experience,
        citations=found.live.config.retrieval.citations,
        avatar_url=avatar_url,
        logo_url=None if logo is None else _image_url(public_id, "logo", logo),
    )


async def widget_image(session: AsyncSession, public_id: str, kind: str) -> StoredImage | None:
    """The image a live Agent's widget shows as ``kind``: ``avatar`` (the Agent's own, else the
    Theme's) or ``logo`` (the Theme's); None when there is none. Raises
    ``serving.AgentNotServedError`` or ``serving.AgentNotLiveError`` like the shell."""
    found = await serving.live_agent(session, public_id)
    theme = await organisation_theme(session, found.agent.organisation_id)
    if kind == "logo":
        return theme.images[ThemeImageKind.LOGO]
    return override_of(found.agent).avatar or theme.images[ThemeImageKind.AVATAR]


class InvalidTokenError(Exception):
    """The token is tampered with, expired, or isn't for this Agent."""


async def start_conversation(
    session: AsyncSession, signer: TokenSigner, public_id: str, bootstrap: str, *, now: datetime
) -> str:
    """Exchanges the Agent's bootstrap token for a new Visitor Conversation's token."""
    if signer.bootstrap_agent(bootstrap, now=now) != public_id:
        raise InvalidTokenError
    conversation_id = await serving.start_conversation(session, public_id, now=now)
    token = signer.conversation(conversation_id)
    conversation = await session.get_one(Conversation, conversation_id)
    conversation.token_hash = token_hash(token)
    await session.commit()
    return token


class NotAdmittedError(Exception):
    """Admission control refused the message: the Visitor gets the unavailable text."""

    def __init__(self, reason: Refusal, agent_id: uuid.UUID) -> None:
        super().__init__(reason)
        self.reason = reason
        self.agent_id = agent_id


@dataclass(frozen=True)
class AdmittedTurn:
    """A Visitor's question admitted and saved, ready for the Live Version to answer."""

    turn: PreparedTurn
    agent_id: uuid.UUID
    # The limits it was admitted under; the reply's usage counts against the Token Budget.
    limits: Limits
    # The cost the reply holds against the budget until its usage is recorded (which settles
    # it) or it is released.
    reservation: Reservation


async def prepare_turn(
    session: AsyncSession,
    signer: TokenSigner,
    public_id: str,
    token: str,
    question: str,
    *,
    admission: Admission,
    ip: str,
    now: datetime,
) -> AdmittedTurn:
    """Saves the Visitor's question in the token's Conversation, to be answered by the Agent's
    Live Version at this moment. A valid token's message first goes through admission control
    with the Agent's current Token Budget and rate limits; a refused one raises
    ``NotAdmittedError`` and nothing is saved. An admitted one reserves an estimate of its
    reply's cost, given back here if the turn can't be prepared."""
    conversation = await _conversation(session, signer, public_id, token, now=now)
    agent = await session.get_one(Agent, conversation.agent_id)
    limits = Limits(
        public_id=agent.public_id,
        conversation_messages_per_minute=agent.conversation_messages_per_minute,
        ip_messages_per_minute=agent.ip_messages_per_minute,
        daily_token_budget=agent.daily_token_budget,
    )
    admitted = await admission.admit(limits, token, ip)
    if isinstance(admitted, Refusal):
        raise NotAdmittedError(admitted, agent.id)
    try:
        turn = await serving.prepare_turn(session, public_id, conversation.id, question, now=now)
    except BaseException:
        await admission.release(admitted)
        raise
    return AdmittedTurn(turn, agent.id, limits, admitted)


# The Token Budget


@dataclass(frozen=True)
class TokenUsage:
    # The UTC date counted, today's.
    date: date_type
    tokens_used: int
    daily_token_budget: int
    exhausted: bool
    # Midnight UTC, when the next day's budget starts.
    resets_at: datetime


def _midnight_after(now: datetime) -> datetime:
    return datetime.combine(utc_date(now) + timedelta(days=1), time(), tzinfo=UTC)


def _start_of_day(now: datetime) -> datetime:
    return datetime.combine(utc_date(now), time(), tzinfo=UTC)


async def token_usage(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    admission: Admission,
    now: datetime,
) -> TokenUsage:
    """Today's (UTC) Visitor usage against the Agent's Token Budget."""
    agent = (await get_agent(session, scope, project_id, agent_id)).agent
    today = utc_date(now)
    used = await admission.tokens_used(agent.public_id, today)
    return TokenUsage(
        date=today,
        tokens_used=used,
        daily_token_budget=agent.daily_token_budget,
        exhausted=used >= agent.daily_token_budget,
        resets_at=_midnight_after(now),
    )


async def budget_exhausted(
    session: AsyncSession,
    agent_id: uuid.UUID,
    *,
    mailer: Mailer,
    studio_url: str,
    now: datetime,
) -> None:
    """Raises the Agent's budget alert flag for today and emails every Owner of its
    Organisation, once per Agent per UTC date: only the call that raises today's flag sends,
    so concurrent replies and refusals can't send twice. A flag left from an earlier day counts
    as no flag."""
    raised = await session.scalar(
        update(Agent)
        .where(
            Agent.id == agent_id,
            or_(
                Agent.budget_exhausted_at.is_(None), Agent.budget_exhausted_at < _start_of_day(now)
            ),
        )
        .values(budget_exhausted_at=now)
        .returning(Agent.id)
    )
    await session.commit()
    if raised is None:
        return
    agent = await session.get_one(Agent, agent_id)
    owners = await session.execute(
        select(Member.name, Member.email)
        .join(Membership, Membership.member_id == Member.id)
        .where(Membership.organisation_id == agent.organisation_id, Membership.role == Role.OWNER)
        .order_by(Member.email)
    )
    link = templates.agent_link(
        studio_url, str(agent.organisation_id), str(agent.project_id), str(agent.id)
    )
    for name, email in owners:
        await mailer.send(
            templates.token_budget_exhausted(
                to=email,
                name=name,
                agent_name=agent.name,
                budget=agent.daily_token_budget,
                link=link,
            )
        )


async def clear_budget_alerts(session: AsyncSession, *, now: datetime) -> int:
    """Clears the budget alert flags raised before today (UTC), for Beat at midnight; returns
    how many it cleared. A flag raised today stays: today's budget is still spent."""
    cleared = await session.execute(
        update(Agent)
        .where(Agent.budget_exhausted_at < _start_of_day(now))
        .values(budget_exhausted_at=None)
        .returning(Agent.id)
    )
    count = len(cleared.all())
    await session.commit()
    return count


async def _conversation(
    session: AsyncSession, signer: TokenSigner, public_id: str, token: str, *, now: datetime
) -> Conversation:
    """The Visitor Conversation the token stands for; raises ``InvalidTokenError`` when the
    token is tampered with, ended, expired or for another Agent."""
    conversation_id = signer.conversation_id(token)
    if conversation_id is None:
        raise InvalidTokenError
    conversation = await session.scalar(
        select(Conversation)
        .join(Agent, Agent.id == Conversation.agent_id)
        .where(
            Conversation.id == conversation_id,
            Conversation.token_hash == token_hash(token),
            Agent.public_id == public_id,
        )
    )
    if conversation is None or expired(conversation.last_activity_at, now=now):
        raise InvalidTokenError
    return conversation


@dataclass(frozen=True)
class ResumedCitation:
    label: str
    document_name: str | None


@dataclass(frozen=True)
class ResumedMessage:
    id: uuid.UUID
    role: str
    content: str
    citations: list[ResumedCitation]
    # The Visitor's Message Feedback on an answer, if they gave some.
    feedback: MessageFeedback | None


@dataclass(frozen=True)
class ResumedConversation:
    messages: list[ResumedMessage]
    # The Visitor's Conversation Rating and whether they dismissed the rating prompt.
    rating: RatingState


async def resume(
    session: AsyncSession, signer: TokenSigner, public_id: str, token: str, *, now: datetime
) -> ResumedConversation:
    """The Messages of the token's Conversation, in order, each answer with the sources it
    cited, and its Conversation Rating. A reload counts as activity, so it slides the 24-hour
    window on. Raises
    ``serving.AgentNotServedError`` or ``serving.AgentNotLiveError`` once the Agent is
    retired."""
    conversation = await _conversation(session, signer, public_id, token, now=now)
    await serving.live_agent(session, public_id)
    conversation.last_activity_at = now
    messages = list(
        await session.scalars(
            select(Message).where(Message.conversation_id == conversation.id).order_by(Message.seq)
        )
    )
    await session.commit()
    cited: dict[uuid.UUID, list[ResumedCitation]] = {}
    rows = await session.execute(
        select(MessageRetrieval.message_id, MessageRetrieval.rank, Document.name)
        .outerjoin(Document, Document.id == MessageRetrieval.document_id)
        .where(
            MessageRetrieval.message_id.in_([m.id for m in messages]),
            MessageRetrieval.cited.is_(True),
        )
        .order_by(MessageRetrieval.message_id, MessageRetrieval.rank)
    )
    for message_id, rank, name in rows:
        cited.setdefault(message_id, []).append(ResumedCitation(chunk_label(cast(int, rank)), name))
    given = await feedback_on(session, [m.id for m in messages])
    return ResumedConversation(
        [
            ResumedMessage(m.id, m.role, m.content, cited.get(m.id, []), given.get(m.id))
            for m in messages
        ],
        await rating_state(session, conversation),
    )


async def end(
    session: AsyncSession, signer: TokenSigner, public_id: str, token: str, *, now: datetime
) -> None:
    """Ends the token's Conversation: its token is forgotten, so it is refused from now on.
    The Conversation and its Messages are kept. A retired Agent's Conversations can still be
    ended."""
    conversation = await _conversation(session, signer, public_id, token, now=now)
    conversation.token_hash = None
    await session.commit()


async def visitor_conversation(
    session: AsyncSession, signer: TokenSigner, public_id: str, token: str, *, now: datetime
) -> Conversation:
    """The Visitor Conversation the Conversation token stands for, for other modules' widget
    routes (Message Feedback); raises ``InvalidTokenError`` like the routes here."""
    return await _conversation(session, signer, public_id, token, now=now)
