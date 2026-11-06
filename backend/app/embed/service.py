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
from app.agents.models import ORIGIN_MAX, Agent
from app.agents.service import get_agent
from app.conversations.models import Conversation
from app.embed.tokens import TokenSigner, expired, token_hash
from app.playground.service import PreparedTurn
from app.tenancy.repository import OrganisationScope

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
    name: str
    allowed_origins: list[str]
    bootstrap_token: str


async def shell(
    session: AsyncSession, signer: TokenSigner, public_id: str, *, now: datetime
) -> Shell:
    """What the widget shell needs; raises ``serving.AgentNotServedError`` or
    ``serving.AgentNotLiveError`` when the Agent can't be served."""
    found = await serving.live_agent(session, public_id)
    return Shell(
        public_id=found.agent.public_id,
        name=found.agent.name,
        allowed_origins=found.agent.allowed_origins,
        bootstrap_token=signer.bootstrap(found.agent.public_id, now=now),
    )


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
