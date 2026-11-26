"""Builds the voice layer the settings select: ElevenLabs, or the scripted fake."""

from app.core.settings import Settings
from app.voice.elevenlabs import ElevenLabsVoiceLayer
from app.voice.fake import FakeVoiceLayer
from app.voice.port import VoiceLayer


def build_voice_layer(settings: Settings) -> VoiceLayer:
    if settings.voice_layer == "fake":
        return FakeVoiceLayer()
    # A voice layer call is as quick as a credential check: one or a few small requests.
    return ElevenLabsVoiceLayer(timeout_seconds=settings.credential_check_timeout_seconds)
