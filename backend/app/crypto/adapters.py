"""Builds the envelope-encryption service with the key wrapper the settings select."""

from app.core.settings import Settings
from app.crypto.envelope import EnvelopeEncryption
from app.crypto.local_key_wrapper import LocalKeyWrapper


def build_envelope(settings: Settings) -> EnvelopeEncryption:
    # ``key_wrapper`` has one value so far, "local"; AWS KMS is added with spec 09.
    return EnvelopeEncryption(LocalKeyWrapper(settings.local_key_wrapper_key.get_secret_value()))
