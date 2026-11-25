"""Builds the voice layer the settings select."""

from app.core.settings import Settings
from app.voice.fake import FakeVoiceLayer
from app.voice.port import CallJoin, RemoteAgentSpec, Voice, VoiceLayer, VoiceLayerError

NOT_CONNECTED = "The ElevenLabs voice layer isn't connected in this release."


class UnconnectedVoiceLayer:
    """The ElevenLabs adapter's place until it is built (ticket 20-05): every operation fails,
    so calling can't be turned on against a voice layer that can't hold a Call."""

    async def set_up_agent(
        self, api_key: str, spec: RemoteAgentSpec, *, remote_agent_id: str | None
    ) -> str:
        raise VoiceLayerError(NOT_CONNECTED)

    async def remove_agent(self, api_key: str, remote_agent_id: str) -> None:
        raise VoiceLayerError(NOT_CONNECTED)

    async def list_voices(self, api_key: str) -> list[Voice]:
        raise VoiceLayerError(NOT_CONNECTED)

    async def start_call(self, api_key: str, remote_agent_id: str) -> CallJoin:
        raise VoiceLayerError(NOT_CONNECTED)


def build_voice_layer(settings: Settings) -> VoiceLayer:
    if settings.voice_layer == "fake":
        return FakeVoiceLayer()
    return UnconnectedVoiceLayer()
