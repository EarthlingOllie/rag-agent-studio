"""An Agent's Call settings (spec 20): whether it takes Calls, the voice-capable Provider
Credential and the voice it speaks with, and its spoken greeting. They are Operational Settings
(``app.embed.service``), so they apply at once and are audited with the others; this module
checks a change and keeps the Agent's remote agent in the voice layer (``app.voice.remote``)
in step with it.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.credentials.models import ProviderCredential
from app.credentials.references import CredentialReference
from app.credentials.registry import Capability
from app.credentials.service import open_secret
from app.tenancy.repository import OrganisationScope
from app.voice import remote
from app.voice.remote import VoicePorts

NO_VOICE_CREDENTIAL = (
    "The Organisation has no voice-capable Provider Credential, so the Agent can't take Calls. "
    "An Owner adds an ElevenLabs credential in Organisation settings, Credentials."
)
UNKNOWN_CREDENTIAL = "No Provider Credential with this ID in the Organisation."
NOT_VOICE_CAPABLE = "This credential doesn't have the voice Capability, so it can't carry Calls."
CREDENTIAL_REQUIRED = "Choose the voice-capable credential the Agent's Calls use."
VOICE_REQUIRED = "Choose the voice the Agent speaks with."
VOICE_UNAVAILABLE = "The credential's ElevenLabs account doesn't offer this voice."


class CallSettingsError(Exception):
    """A Call settings change refused, naming the field and the reason."""

    def __init__(self, field: str, message: str, kind: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message
        self.kind = kind


@dataclass(frozen=True)
class CallSettingsChange:
    """The Call settings to change; ``None`` leaves one as it is."""

    calls_enabled: bool | None = None
    call_credential_id: uuid.UUID | None = None
    call_voice_id: str | None = None
    spoken_greeting: str | None = None


@dataclass(frozen=True)
class _CallState:
    enabled: bool
    credential_id: uuid.UUID | None
    voice_id: str | None
    spoken_greeting: str


def _state(agent: Agent) -> _CallState:
    return _CallState(
        agent.calls_enabled, agent.call_credential_id, agent.call_voice_id, agent.spoken_greeting
    )


async def _credential(
    session: AsyncSession, scope: OrganisationScope, credential_id: uuid.UUID
) -> ProviderCredential:
    credential = await session.scalar(
        select(ProviderCredential).where(
            ProviderCredential.id == credential_id,
            ProviderCredential.organisation_id == scope.organisation_id,
        )
    )
    if credential is None:
        raise CallSettingsError("call_credential_id", UNKNOWN_CREDENTIAL, "unknown_credential")
    if Capability.VOICE not in credential.capabilities:
        raise CallSettingsError("call_credential_id", NOT_VOICE_CAPABLE, "not_voice_capable")
    return credential


async def _has_voice_credential(session: AsyncSession, scope: OrganisationScope) -> bool:
    found = await session.scalar(
        select(ProviderCredential.id)
        .where(
            ProviderCredential.organisation_id == scope.organisation_id,
            ProviderCredential.capabilities.contains([Capability.VOICE.value]),
        )
        .limit(1)
    )
    return found is not None


async def _checked_credential(
    session: AsyncSession, scope: OrganisationScope, agent: Agent, ports: VoicePorts
) -> ProviderCredential:
    """The credential calling is on with, once it and the voice are good."""
    if agent.call_credential_id is None:
        if not await _has_voice_credential(session, scope):
            raise CallSettingsError("calls_enabled", NO_VOICE_CREDENTIAL, "no_voice_credential")
        raise CallSettingsError("call_credential_id", CREDENTIAL_REQUIRED, "missing")
    credential = await _credential(session, scope, agent.call_credential_id)
    if agent.call_voice_id is None:
        raise CallSettingsError("call_voice_id", VOICE_REQUIRED, "missing")
    voices = await ports.layer.list_voices(open_secret(ports.envelope, credential))
    if agent.call_voice_id not in {voice.id for voice in voices}:
        raise CallSettingsError("call_voice_id", VOICE_UNAVAILABLE, "voice_unavailable")
    return credential


async def apply(
    session: AsyncSession,
    scope: OrganisationScope,
    agent: Agent,
    change: CallSettingsChange,
    ports: VoicePorts,
) -> None:
    """Applies the change to the locked ``agent`` in the caller's transaction, refusing it with
    ``CallSettingsError`` when it isn't good, and brings the remote agent in step: set up when
    calling is saved on (or has none yet), updated when the Call settings change, set up anew
    with the new credential (and the old one removed) when the credential changes, and removed
    when calling is turned off. A voice layer failure raises ``VoiceLayerError``; the caller
    saves nothing then. An archived Agent gets no remote agent."""
    before = _state(agent)
    if change.calls_enabled is not None:
        agent.calls_enabled = change.calls_enabled
    if change.call_credential_id is not None:
        await _credential(session, scope, change.call_credential_id)
        agent.call_credential_id = change.call_credential_id
    if change.call_voice_id is not None:
        agent.call_voice_id = change.call_voice_id
    if change.spoken_greeting is not None:
        agent.spoken_greeting = change.spoken_greeting.strip()
    after = _state(agent)
    if not after.enabled:
        if before.enabled:
            await remote.remove(session, ports, agent, before.credential_id)
        return
    if agent.archived_at is not None:
        return
    if after == before and agent.remote_agent_id is not None:
        return
    credential = await _checked_credential(session, scope, agent, ports)
    if before.enabled and before.credential_id != after.credential_id:
        # Set up in the new credential's account first, so a failure there leaves the old one.
        old = agent.remote_agent_id
        agent.remote_agent_id = None
        await remote.set_up(session, ports, agent, credential)
        await remote.discard(session, ports, before.credential_id, old)
        return
    await remote.set_up(session, ports, agent, credential)


async def call_settings_references(
    session: AsyncSession, scope: OrganisationScope, credential_id: uuid.UUID
) -> list[CredentialReference]:
    """The "who references me" source: each Agent that calls with the credential."""
    agents = await session.scalars(
        select(Agent)
        .where(
            Agent.organisation_id == scope.organisation_id,
            Agent.calls_enabled.is_(True),
            Agent.call_credential_id == credential_id,
        )
        .order_by(Agent.name)
    )
    return [
        CredentialReference("agent", str(agent.id), f"{agent.name} (Call settings)")
        for agent in agents
    ]
