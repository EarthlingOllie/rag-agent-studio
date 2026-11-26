"""The scripted fake voice layer (``VOICE_LAYER=fake``: tests and ``docker compose``).

It keeps remote agents in memory, offers a fixed set of voices, and joins Calls with no audio.
``failing`` makes every operation fail until it is turned off, as an outage or a revoked key
would. Tests read ``remote_agents`` to see what the platform set up.

A joined Call's turns are driven from outside, as speech would drive ElevenLabs: ``hold_turn``
takes the words "heard" in the Call and does what ElevenLabs does with them, posting them to the
remote agent's custom LLM (our turn endpoint) with its secret, the Call token the widget handed
over as extra body, and the transcript so far as history, then returns the reply it would
speak. The widget's scripted call client drives it through ``app.voice.fake_api``.
"""

import itertools
import json
from dataclasses import dataclass, field

import httpx

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


@dataclass
class FakeCall:
    remote_agent_id: str
    # The turns so far, as ElevenLabs sends them to the custom LLM: {role, content}.
    transcript: list[dict[str, str]] = field(default_factory=list)


class FakeVoiceLayer:
    def __init__(self) -> None:
        self.remote_agents: dict[str, FakeRemoteAgent] = {}
        # Every Call joined: (remote agent ID, conversation token).
        self.calls: list[tuple[str, str]] = []
        # Every greeting spoken as a Call opened.
        self.greetings: list[str] = []
        self.failing = False
        self._ids = itertools.count(1)
        self._joined: dict[str, FakeCall] = {}

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

    async def start_call(self, api_key: str, remote_agent_id: str, *, greet: bool) -> CallJoin:
        self._check()
        remote_agent = self.remote_agents.get(remote_agent_id)
        if remote_agent is None:
            raise VoiceLayerError("The fake voice layer has no such remote agent.")
        token = f"fake-call-{next(self._ids)}"
        self.calls.append((remote_agent_id, token))
        call = FakeCall(remote_agent_id)
        greeting = remote_agent.spec.spoken_greeting
        if greet and greeting:
            # Spoken as the Call opens, and part of the transcript ElevenLabs sends as history.
            self.greetings.append(greeting)
            call.transcript.append({"role": "assistant", "content": greeting})
        self._joined[token] = call
        return CallJoin(token, greet)

    async def hold_turn(
        self, join_token: str, words: str, call_token: str, *, transport: httpx.AsyncBaseTransport
    ) -> str:
        """One turn of the Call joined with ``join_token``: posts ``words`` to the remote agent's
        custom LLM over ``transport`` and returns the reply's text. Raises ``VoiceLayerError``
        for an unknown Call or a refused turn."""
        call = self._joined.get(join_token)
        remote_agent = None if call is None else self.remote_agents.get(call.remote_agent_id)
        if call is None or remote_agent is None:
            raise VoiceLayerError("The fake voice layer has no such Call.")
        spec = remote_agent.spec
        call.transcript.append({"role": "user", "content": words})
        async with httpx.AsyncClient(transport=transport) as client:
            response = await client.post(
                f"{spec.llm_url}/chat/completions",
                headers={"Authorization": f"Bearer {spec.llm_secret}"},
                json={
                    "model": "custom-llm",
                    "stream": True,
                    "messages": [
                        {"role": "system", "content": "The remote agent has no prompt."},
                        *call.transcript,
                    ],
                    "elevenlabs_extra_body": {"call_token": call_token},
                },
            )
        if response.status_code != httpx.codes.OK:
            raise VoiceLayerError(f"The custom LLM refused the turn: {response.text}")
        reply = "".join(
            choice["delta"].get("content", "")
            for line in response.text.splitlines()
            if line.startswith("data: {")
            for choice in json.loads(line.removeprefix("data: "))["choices"]
        )
        call.transcript.append({"role": "assistant", "content": reply})
        return reply
