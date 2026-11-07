"""Embedding rules: an Agent's Allowed Origins, the shell's framing policy, and Visitors'
Conversations, which are reached only through their Conversation token.

Allowed Origins are a simple list here: each is a scheme (``http`` or ``https``), a host and an
optional port, with no path. Spec 06's Operational Settings (ticket 06-02) add subdomain
wildcards and auditing.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import serving
from app.agents.config import Experience
from app.agents.models import ORIGIN_MAX, Agent
from app.agents.service import get_agent
from app.conversations.models import Conversation
from app.embed.branding import override_of
from app.embed.tokens import TokenSigner, expired, token_hash
from app.playground.service import PreparedTurn
from app.tenancy.repository import OrganisationScope
from app.theme.resolve import with_colours
from app.theme.schema import ThemeSettings
from app.theme.service import StoredImage, ThemeImageKind, organisation_theme

ORIGINS_MAX = 50
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_ORIGIN = re.compile(rf"https?://{_LABEL}(?:\.{_LABEL})*(?::[0-9]{{1,5}})?")


class InvalidOriginError(Exception):
    def __init__(self, index: int, origin: str) -> None:
        super().__init__(origin)
        self.index = index
        self.origin = origin


def normalise_origins(origins: list[str]) -> list[str]:
    """The origins, lower-cased, without a trailing slash and without repeats, in order; an
    entry that isn't an origin raises ``InvalidOriginError``."""
    found: list[str] = []
    for index, raw in enumerate(origins):
        origin = raw.strip().lower().removesuffix("/")
        port = origin.rpartition(":")[2]
        if (
            len(origin) > ORIGIN_MAX
            or not _ORIGIN.fullmatch(origin)
            or (port.isdigit() and not 0 < int(port) < 65536)
        ):
            raise InvalidOriginError(index, raw)
        if origin not in found:
            found.append(origin)
    return found


def frame_ancestors(origins: list[str]) -> str:
    """The ``Content-Security-Policy`` that lets only those origins frame the widget."""
    return "frame-ancestors " + (" ".join(origins) if origins else "'none'")


async def allowed_origins(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, agent_id: uuid.UUID
) -> list[str]:
    return (await get_agent(session, scope, project_id, agent_id)).agent.allowed_origins


async def set_allowed_origins(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    origins: list[str],
) -> list[str]:
    """Replaces the Agent's Allowed Origins; the next shell served uses them."""
    normalised = normalise_origins(origins)
    agent = (await get_agent(session, scope, project_id, agent_id, lock=True)).agent
    agent.allowed_origins = normalised
    await session.commit()
    return normalised


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
    # The Agent's own avatar, else the Live Version's, else the Theme's default avatar.
    avatar_url: str | None = None
    if override.avatar is not None:
        avatar_url = _image_url(public_id, "avatar", override.avatar)
    elif experience.avatar_url is not None:
        avatar_url = str(experience.avatar_url)
    elif (theme_avatar := theme.images[ThemeImageKind.AVATAR]) is not None:
        avatar_url = _image_url(public_id, "avatar", theme_avatar)
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


async def prepare_turn(
    session: AsyncSession,
    signer: TokenSigner,
    public_id: str,
    token: str,
    question: str,
    *,
    now: datetime,
) -> PreparedTurn:
    """Saves the Visitor's question in the token's Conversation, to be answered by the Agent's
    Live Version at this moment."""
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
    return await serving.prepare_turn(session, public_id, conversation_id, question, now=now)
