"""The scripted fake voice layer, as the settings select it (the ElevenLabs adapter is tested in
``test_elevenlabs_voice_layer``)."""

import pytest

from app.core.settings import Settings
from app.voice.adapters import build_voice_layer
from app.voice.fake import FakeVoiceLayer
from app.voice.port import CallJoin, RemoteAgentSpec, VoiceLayerError

SPEC = RemoteAgentSpec(
    name="Front desk",
    voice_id="fake-voice-ada",
    spoken_greeting="Hello.",
    llm_url="https://calls.example.test/api/widget/agents/agt_x/llm/v1",
    llm_secret="s" * 43,
)


def settings(settings_env: pytest.MonkeyPatch, voice_layer: str) -> Settings:
    settings_env.setenv("VOICE_LAYER", voice_layer)
    return Settings()


def test_the_fake_is_selected_by_settings(settings_env: pytest.MonkeyPatch) -> None:
    assert isinstance(build_voice_layer(settings(settings_env, "fake")), FakeVoiceLayer)


async def test_the_fake_joins_a_call_with_a_remote_agent_it_holds() -> None:
    layer = FakeVoiceLayer()
    remote_agent_id = await layer.set_up_agent("key", SPEC, remote_agent_id=None)

    joined = await layer.start_call("key", remote_agent_id, greet=True)
    listening = await layer.start_call("key", remote_agent_id, greet=False)

    assert joined == CallJoin(joined.conversation_token, greet=True)
    assert listening == CallJoin(listening.conversation_token, greet=False)
    assert layer.calls == [
        (remote_agent_id, joined.conversation_token),
        (remote_agent_id, listening.conversation_token),
    ]
    # Only the Call that greets speaks the remote agent's greeting.
    assert layer.greetings == [SPEC.spoken_greeting]
    with pytest.raises(VoiceLayerError):
        await layer.start_call("key", "gone", greet=True)
    layer.failing = True
    with pytest.raises(VoiceLayerError):
        await layer.start_call("key", remote_agent_id, greet=True)
