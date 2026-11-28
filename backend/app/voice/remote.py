"""An Agent's remote agent in the voice layer: set up when calling is saved on, updated on later
saves, and removed when calling is turned off, its credential changes, or the Agent is archived
or deleted (spec 20).

When the voice layer can't start one of the Agent's Calls, its Calls failing alert is raised;
setting the remote agent up again (saving the Call settings), removing it (calling off), or the
next Call that starts clears it.

The remote agent presents a per-Agent secret to our turn endpoint as its custom LLM's API key.
The platform generates the secret and stores it only sealed (``app.crypto.envelope``), bound to
the Agent and its Organisation; ``call_secret`` opens it for the turn endpoint's check.
"""

import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.credentials.models import ProviderCredential
from app.credentials.service import open_secret
from app.crypto.envelope import EnvelopeEncryption
from app.voice.port import CallJoin, RemoteAgentSpec, VoiceLayer, VoiceLayerError

logger = logging.getLogger(__name__)

SECRET_BYTES = 32


@dataclass(frozen=True)
class VoicePorts:
    layer: VoiceLayer
    envelope: EnvelopeEncryption
    # The platform's public base URL, without a trailing slash.
    public_base_url: str


_installed: list[VoicePorts] = []


def install_voice_ports(ports: VoicePorts) -> None:
    """The API and the worker install the voice layer tasks reach remote agents through (the
    Project deletion cascade); in tests, tasks run eagerly and use the API's own."""
    _installed[:] = [ports]


def current_voice_ports() -> VoicePorts:
    return _installed[0]


def turn_endpoint(public_base_url: str, public_id: str) -> str:
    """The OpenAI-compatible base URL the remote agent calls as its custom LLM: it posts each
    turn to ``…/chat/completions`` under it."""
    return f"{public_base_url.rstrip('/')}/api/widget/agents/{public_id}/llm/v1"


def _context(agent: Agent) -> bytes:
    return f"agent-call-secret:{agent.organisation_id}:{agent.id}".encode()


def call_secret(envelope: EnvelopeEncryption, agent: Agent) -> str | None:
    """The secret the Agent's remote agent presents to the turn endpoint; None while it has
    none (calling is off)."""
    if agent.call_secret_sealed is None:
        return None
    return envelope.open(agent.call_secret_sealed, context=_context(agent)).decode()


async def set_up(
    session: AsyncSession, ports: VoicePorts, agent: Agent, credential: ProviderCredential
) -> None:
    """Creates the Agent's remote agent with ``credential``, or updates it, from its Call
    settings, in the caller's transaction. A secret is generated the first time. Raises
    ``VoiceLayerError``, leaving the Agent's columns as they were."""
    secret = call_secret(ports.envelope, agent)
    sealed = None
    if secret is None:
        secret = secrets.token_urlsafe(SECRET_BYTES)
        sealed = ports.envelope.seal(secret.encode(), context=_context(agent))
    spec = RemoteAgentSpec(
        name=f"{agent.name} ({agent.public_id})",
        voice_id=agent.call_voice_id or "",
        spoken_greeting=agent.spoken_greeting,
        llm_url=turn_endpoint(ports.public_base_url, agent.public_id),
        llm_secret=secret,
    )
    remote_agent_id = await ports.layer.set_up_agent(
        open_secret(ports.envelope, credential), spec, remote_agent_id=agent.remote_agent_id
    )
    agent.remote_agent_id = remote_agent_id
    if sealed is not None:
        agent.call_secret_sealed = sealed
    agent.calls_failing_at = None


async def discard(
    session: AsyncSession,
    ports: VoicePorts,
    credential_id: uuid.UUID | None,
    remote_agent_id: str | None,
) -> None:
    """Deletes a remote agent from the account of the credential it was set up with. Best
    effort: when the voice layer fails, the failure is logged and the remote agent, which
    nothing answers for any more, is left behind, so the Agent's own change still goes ahead."""
    credential = (
        None if credential_id is None else await session.get(ProviderCredential, credential_id)
    )
    if remote_agent_id is None or credential is None:
        return
    try:
        await ports.layer.remove_agent(open_secret(ports.envelope, credential), remote_agent_id)
    except VoiceLayerError:
        logger.warning(
            "The voice layer couldn't remove a remote agent",
            extra={"remote_agent_id": remote_agent_id},
        )


async def remove(
    session: AsyncSession, ports: VoicePorts, agent: Agent, credential_id: uuid.UUID | None
) -> None:
    """Removes the Agent's remote agent, if it has one, from the account of the credential it
    was set up with (see ``discard``), and forgets it and its secret."""
    remote_agent_id = agent.remote_agent_id
    agent.remote_agent_id = None
    agent.call_secret_sealed = None
    # An Agent with no remote agent takes no Calls, so none can fail.
    agent.calls_failing_at = None
    await discard(session, ports, credential_id, remote_agent_id)


async def start_call(
    session: AsyncSession,
    ports: VoicePorts,
    agent: Agent,
    credential: ProviderCredential,
    *,
    greet: bool,
    now: datetime,
) -> CallJoin:
    """Asks the voice layer for a Call with the Agent's remote agent. A Call that starts clears
    the Agent's Calls failing alert, in the caller's transaction. When the voice layer can't
    start it, the caller's transaction is rolled back, the alert is raised (and committed), and
    ``VoiceLayerError`` raised."""
    agent_id = agent.id
    try:
        join = await ports.layer.start_call(
            open_secret(ports.envelope, credential), str(agent.remote_agent_id), greet=greet
        )
    except VoiceLayerError:
        await session.rollback()
        await session.execute(
            update(Agent)
            .where(Agent.id == agent_id, Agent.calls_failing_at.is_(None))
            .values(calls_failing_at=now)
        )
        await session.commit()
        logger.warning("The voice layer couldn't start a Call", extra={"agent_id": str(agent_id)})
        raise
    agent.calls_failing_at = None
    return join
