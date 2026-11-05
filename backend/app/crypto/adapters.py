"""Builds the envelope-encryption service with the key wrapper the settings select."""

import boto3

from app.core.settings import Settings
from app.crypto.envelope import EnvelopeEncryption, KeyWrapper
from app.crypto.kms_key_wrapper import KmsKeyWrapper
from app.crypto.local_key_wrapper import LocalKeyWrapper


def build_key_wrapper(settings: Settings) -> KeyWrapper:
    if settings.key_wrapper == "kms":
        # The settings validator guarantees a key ID when the KMS wrapper is selected.
        assert settings.kms_key_id is not None  # noqa: S101
        return KmsKeyWrapper(
            boto3.client("kms", region_name=settings.kms_region), settings.kms_key_id
        )
    return LocalKeyWrapper(settings.local_key_wrapper_key.get_secret_value())


def build_envelope(settings: Settings) -> EnvelopeEncryption:
    return EnvelopeEncryption(build_key_wrapper(settings))
