"""Live suite: the ElevenLabs voice layer against a real account (spec 20, ticket 20-05).

With ``SEED_ELEVENLABS_API_KEY`` set (a key whose permissions include ElevenLabs Agents), it
sets up a remote agent with the account's first voice, updates it, mints a WebRTC token for a
Call with it, and removes it again, leaving nothing behind in the account. No Call is held, so no
audio is spoken and no turn endpoint needs to be reachable.

``ELEVENLABS_RECORD=<directory>`` also writes each operation's HTTP exchanges there (without the
key), in the form ``tests/fixtures/elevenlabs`` replays, to refresh those recordings.

Run with ``make test-live``; without a key it is skipped with the reason, unless
``LIVE_REQUIRE_MODELS=1``.
"""

import os
import secrets
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from app.voice.elevenlabs import ElevenLabsVoiceLayer
from app.voice.port import RemoteAgentSpec, VoiceLayerError
from tests.fakes.http_exchanges import Recorder
from tests.live.models import skip_or_fail

pytestmark = pytest.mark.live


@pytest.fixture
def api_key() -> str:
    key = os.environ.get("SEED_ELEVENLABS_API_KEY", "")
    if not key:
        skip_or_fail(
            "No ElevenLabs key: set SEED_ELEVENLABS_API_KEY to set up a real remote agent."
        )
    return key


class Layers:
    """A fresh adapter per operation, recording each when ``ELEVENLABS_RECORD`` is set."""

    def __init__(self) -> None:
        record = os.environ.get("ELEVENLABS_RECORD")
        self._directory = Path(record) if record else None
        self._recorders: list[tuple[str, Recorder]] = []

    def __call__(self, recording: str) -> ElevenLabsVoiceLayer:
        transport: httpx.AsyncBaseTransport = httpx.AsyncHTTPTransport()
        if self._directory is not None:
            recorder = Recorder(transport)
            self._recorders.append((recording, recorder))
            transport = recorder
        return ElevenLabsVoiceLayer(timeout_seconds=30, transport=transport)

    def save(self) -> None:
        if self._directory is None:
            return
        self._directory.mkdir(parents=True, exist_ok=True)
        for recording, recorder in self._recorders:
            recorder.save(self._directory / recording)


async def test_a_remote_agent_is_set_up_called_and_removed_on_a_real_account(
    api_key: str,
) -> None:
    layers = Layers()
    voices = await layers("list_voices.json").list_voices(api_key)
    assert voices, "the account has no voices"
    spec = RemoteAgentSpec(
        name="RAG Agent Studio live test (agt_livetest)",
        voice_id=voices[0].id,
        spoken_greeting="Hello from the live suite.",
        # Never called: no Call is held, so no turn reaches it.
        llm_url="https://calls.example.invalid/api/widget/agents/agt_livetest/llm/v1",
        llm_secret=secrets.token_urlsafe(32),
    )
    remote_agent_id = await layers("create_agent.json").set_up_agent(
        api_key, spec, remote_agent_id=None
    )
    try:
        updated = await layers("update_agent.json").set_up_agent(
            api_key,
            replace(spec, spoken_greeting="Hello again."),
            remote_agent_id=remote_agent_id,
        )
        assert updated == remote_agent_id

        joined = await layers("start_call.json").start_call(api_key, remote_agent_id, greet=True)
        assert joined.conversation_token
    finally:
        await layers("remove_agent.json").remove_agent(api_key, remote_agent_id)

    # Gone: a Call can't be started with it, and removing it again counts as removed.
    with pytest.raises(VoiceLayerError):
        await layers("start_call_gone.json").start_call(api_key, remote_agent_id, greet=True)
    await layers("remove_agent_gone.json").remove_agent(api_key, remote_agent_id)
    layers.save()
