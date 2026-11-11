"""The AWS KMS key wrapper, tested with a stubbed KMS client (botocore Stubber).

It is a thin adapter, so it is checked against the KMS API model: each request must match
what KMS accepts, and KMS refusals become ``EnvelopeError``.
"""

import base64

import boto3
import pytest
from botocore.stub import Stubber
from mypy_boto3_kms import KMSClient

from app.core.settings import Settings
from app.crypto.adapters import build_key_wrapper
from app.crypto.envelope import EnvelopeEncryption, EnvelopeError
from app.crypto.kms_key_wrapper import ENCRYPTION_CONTEXT, KmsKeyWrapper
from app.crypto.local_key_wrapper import LocalKeyWrapper

KEY_ARN = "arn:aws:kms:eu-west-2:111122223333:key/1234abcd-12ab-34cd-56ef-1234567890ab"
OTHER_ARN = "arn:aws:kms:eu-west-2:111122223333:key/9999abcd-12ab-34cd-56ef-1234567890ab"
WRAPPED = b"kms-wrapped-data-key"


def _client() -> KMSClient:
    return boto3.client(
        "kms",
        region_name="eu-west-2",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",  # noqa: S106
    )


def test_the_key_id_names_the_kms_key() -> None:
    assert KmsKeyWrapper(_client(), KEY_ARN).key_id == f"kms:{KEY_ARN}"


def test_a_record_sealed_through_kms_opens_again() -> None:
    client = _client()
    envelope = EnvelopeEncryption(KmsKeyWrapper(client, KEY_ARN))
    data_keys: list[bytes] = []
    with Stubber(client) as stubber:
        # The data key is random, so the stub accepts any plaintext and remembers nothing:
        # the decrypt stub hands back the key captured from the request below.
        stubber.add_response(
            "encrypt",
            {"CiphertextBlob": WRAPPED, "KeyId": KEY_ARN},
            {
                "KeyId": KEY_ARN,
                "Plaintext": _capture(data_keys),
                "EncryptionContext": ENCRYPTION_CONTEXT,
            },
        )
        sealed = envelope.seal(b"sk-ant-api03-secret", context=b"credential:1")
        stubber.add_response(
            "decrypt",
            {"Plaintext": data_keys[0], "KeyId": KEY_ARN},
            {
                "CiphertextBlob": WRAPPED,
                "KeyId": KEY_ARN,
                "EncryptionContext": ENCRYPTION_CONTEXT,
            },
        )

        assert envelope.open(sealed, context=b"credential:1") == b"sk-ant-api03-secret"
        stubber.assert_no_pending_responses()
    assert len(data_keys[0]) == 32
    assert b"sk-ant-api03-secret" not in sealed


class _Capture:
    """Matches any value in a stubbed request and keeps it."""

    def __init__(self, into: list[bytes]) -> None:
        self._into = into

    def __eq__(self, other: object) -> bool:
        assert isinstance(other, bytes)
        self._into.append(other)
        return True

    __hash__ = None  # type: ignore[assignment]


def _capture(into: list[bytes]) -> _Capture:
    return _Capture(into)


def test_a_kms_refusal_is_an_envelope_error() -> None:
    client = _client()
    wrapper = KmsKeyWrapper(client, KEY_ARN)
    with Stubber(client) as stubber:
        stubber.add_client_error(
            "decrypt", service_error_code="AccessDeniedException", http_status_code=400
        )

        with pytest.raises(EnvelopeError, match="KMS could not unwrap"):
            wrapper.unwrap(f"kms:{KEY_ARN}", WRAPPED)


def test_a_record_sealed_by_another_kms_key_is_unwrapped_with_that_key() -> None:
    """Records name their key, so moving to a new KMS key leaves old records readable."""
    client = _client()
    wrapper = KmsKeyWrapper(client, KEY_ARN)
    with Stubber(client) as stubber:
        stubber.add_response(
            "decrypt",
            {"Plaintext": b"k" * 32, "KeyId": OTHER_ARN},
            {
                "CiphertextBlob": WRAPPED,
                "KeyId": OTHER_ARN,
                "EncryptionContext": ENCRYPTION_CONTEXT,
            },
        )

        assert wrapper.unwrap(f"kms:{OTHER_ARN}", WRAPPED) == b"k" * 32


def test_a_record_sealed_by_the_local_wrapper_is_refused_without_calling_kms() -> None:
    client = _client()
    local = LocalKeyWrapper(base64.b64encode(b"L" * 32).decode())
    sealed = EnvelopeEncryption(local).seal(b"secret", context=b"c")
    with Stubber(client) as stubber:
        with pytest.raises(EnvelopeError, match="not a KMS key"):
            EnvelopeEncryption(KmsKeyWrapper(client, KEY_ARN)).open(sealed, context=b"c")
        stubber.assert_no_pending_responses()


def _settings(**values: str) -> Settings:
    base = {
        "database_url": "postgresql+asyncpg://u:p@localhost/db",
        "redis_url": "redis://localhost:6379/0",
        "local_key_wrapper_key": base64.b64encode(b"L" * 32).decode(),
    }
    return Settings.model_validate(base | values)


def test_settings_select_the_kms_wrapper() -> None:
    wrapper = build_key_wrapper(
        _settings(key_wrapper="kms", kms_key_id=KEY_ARN, kms_region="eu-west-2")
    )

    assert isinstance(wrapper, KmsKeyWrapper)
    assert wrapper.key_id == f"kms:{KEY_ARN}"


def test_settings_select_the_local_wrapper_by_default() -> None:
    wrapper = build_key_wrapper(_settings())

    assert isinstance(wrapper, LocalKeyWrapper)


def test_the_kms_wrapper_needs_a_key_id() -> None:
    with pytest.raises(ValueError, match="KMS_KEY_ID is required"):
        _settings(key_wrapper="kms")
