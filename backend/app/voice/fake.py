"""The scripted fake voice layer (``VOICE_LAYER=fake``: tests and ``docker compose``).

It keeps remote agents in memory, offers a fixed set of voices, and joins Calls with no audio.
``failing`` makes every operation fail until it is turned off, as an outage or a revoked key
would. Tests read ``remote_agents`` to see what the platform set up.
"""

import itertools
from dataclasses import dataclass

from app.voice.port import CallJoin, RemoteAgentSpec, Voice, VoiceLayerError

FAKE_VOICES = (
    Voice("fake-voice-ada", "Ada", "https://voices.example.invalid/fake-voice-ada.mp3"),
    Voice("fake-voice-bryn", "Bryn", "https://voices.example.invalid/fake-voice-bryn.mp3"),
    Voice("fake-voice-cato", "Cato", None),
)


@dataclass(frozen=True)
class FakeRemoteAgent:
    # The key it was set up with: the ElevenLabs account it lives in.
    api_key: str
    spec: RemoteAgentSpec


class FakeVoiceLayer:
    def __init__(self) -> None:
        self.remote_agents: dict[str, FakeRemoteAgent] = {}
        # Every Call joined: (remote agent ID, conversation token).
        self.calls: list[tuple[str, str]] = []
        self.failing = False
        self._ids = itertools.count(1)

    def _check(self) -> None:
        if self.failing:
            raise VoiceLayerError("The fake voice layer is failing.")

    async def set_up_agent(
        self, api_key: str, spec: RemoteAgentSpec, *, remote_agent_id: str | None
    ) -> str:
        self._check()
        if remote_agent_id is None or remote_agent_id not in self.remote_agents:
            remote_agent_id = f"fake-agent-{next(self._ids)}"
        self.remote_agents[remote_agent_id] = FakeRemoteAgent(api_key, spec)
        return remote_agent_id

    async def remove_agent(self, api_key: str, remote_agent_id: str) -> None:
        self._check()
        self.remote_agents.pop(remote_agent_id, None)

    async def list_voices(self, api_key: str) -> list[Voice]:
        self._check()
        return list(FAKE_VOICES)

    async def start_call(self, api_key: str, remote_agent_id: str) -> CallJoin:
        self._check()
        if remote_agent_id not in self.remote_agents:
            raise VoiceLayerError("The fake voice layer has no such remote agent.")
        token = f"fake-call-{next(self._ids)}"
        self.calls.append((remote_agent_id, token))
        return CallJoin(token)
