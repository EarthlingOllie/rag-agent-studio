"""The voice layer the settings select: the scripted fake, or (until the ElevenLabs adapter
lands) one that refuses every operation. Starting a Call is used from ticket 20-04."""

import pytest

from app.core.settings import Settings
from app.voice.adapters import UnconnectedVoiceLayer, build_voice_layer
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


async def test_the_elevenlabs_layer_refuses_everything_until_it_is_connected(
    settings_env: pytest.MonkeyPatch,
) -> None:
    layer = build_voice_layer(settings(settings_env, "elevenlabs"))

    assert isinstance(layer, UnconnectedVoiceLayer)
    with pytest.raises(VoiceLayerError):
        await layer.set_up_agent("key", SPEC, remote_agent_id=None)
    with pytest.raises(VoiceLayerError):
        await layer.remove_agent("key", "agent")
    with pytest.raises(VoiceLayerError):
        await layer.list_voices("key")
    with pytest.raises(VoiceLayerError):
        await layer.start_call("key", "agent")


async def test_the_fake_joins_a_call_with_a_remote_agent_it_holds() -> None:
    layer = FakeVoiceLayer()
    remote_agent_id = await layer.set_up_agent("key", SPEC, remote_agent_id=None)

    joined = await layer.start_call("key", remote_agent_id)

    assert joined == CallJoin(joined.conversation_token)
    assert layer.calls == [(remote_agent_id, joined.conversation_token)]
    with pytest.raises(VoiceLayerError):
        await layer.start_call("key", "gone")
    layer.failing = True
    with pytest.raises(VoiceLayerError):
        await layer.start_call("key", remote_agent_id)
