"""The voice layer port: the one way the platform talks to ElevenLabs Agents (ADR-0019).

ElevenLabs only listens, takes turns and speaks; our runtime writes every reply. Each Agent with
calling on has one remote agent there, which holds the voice, the language, the spoken greeting
and our turn endpoint as its custom LLM, and nothing of the Agent's prompt or knowledge.

The operations: set up or update an Agent's remote agent, remove it, list a credential's voices,
and start a Call (what the browser needs to join it). Every operation takes the ElevenLabs API
key of the Agent's voice-capable Provider Credential. The production adapter talks to
ElevenLabs; the scripted fake (``app.voice.fake``) is selected by ``VOICE_LAYER=fake``. Nothing
else imports the ElevenLabs API.
"""

from dataclasses import dataclass
from typing import Protocol

# Calls are held in English.
LANGUAGE = "en"


class VoiceLayerError(Exception):
    """The voice layer refused or couldn't be reached: a revoked key, a gone remote agent, an
    outage."""


@dataclass(frozen=True)
class Voice:
    """A voice of the ElevenLabs account: its ID, its name and a sample to listen to."""

    id: str
    name: str
    # Where a short recording of the voice can be played; None when the account has none.
    sample_url: str | None


@dataclass(frozen=True)
class RemoteAgentSpec:
    """What the remote agent holds. It has no prompt, tools or knowledge of its own."""

    # A name to recognise it by in the ElevenLabs account.
    name: str
    voice_id: str
    # What it says first when a Call opens a Conversation with no Messages; empty says nothing.
    # It is spoken by the voice layer only, never saved as a Message.
    spoken_greeting: str
    # Our OpenAI-compatible turn endpoint, its custom LLM.
    llm_url: str
    # The per-Agent secret it presents to the turn endpoint as that LLM's API key.
    llm_secret: str
    language: str = LANGUAGE
    # The custom LLM is sent the extra body the widget passes when a Call starts (the Call
    # token), so the turn endpoint can tell which Call a turn belongs to.
    extra_body: bool = True


@dataclass(frozen=True)
class CallJoin:
    """What the browser needs to join a Call with the remote agent."""

    conversation_token: str
    # Whether the remote agent speaks its greeting when the Call opens; otherwise it opens
    # listening.
    greet: bool


class VoiceLayer(Protocol):
    async def set_up_agent(
        self, api_key: str, spec: RemoteAgentSpec, *, remote_agent_id: str | None
    ) -> str:
        """Creates the remote agent, or updates the one with ``remote_agent_id`` (creating a new
        one if it is gone); returns its ID. Raises ``VoiceLayerError``."""
        ...

    async def remove_agent(self, api_key: str, remote_agent_id: str) -> None:
        """Deletes the remote agent; one already gone counts as removed. Raises
        ``VoiceLayerError``."""
        ...

    async def list_voices(self, api_key: str) -> list[Voice]:
        """The voices the key's account offers. Raises ``VoiceLayerError``."""
        ...

    async def start_call(self, api_key: str, remote_agent_id: str, *, greet: bool) -> CallJoin:
        """Asks for a Call with the remote agent, which speaks its greeting when it opens only
        if ``greet`` (a Call that opens a Conversation with no Messages). Raises
        ``VoiceLayerError``."""
        ...
