"""The AWS KMS key wrapper: data keys are encrypted and decrypted by a KMS key.

The application never holds the KMS key itself. Each record names the key ARN that wrapped
it (``kms:<arn>``), so a record sealed before a move to a new key still opens.
"""

from typing import TYPE_CHECKING

from botocore.exceptions import BotoCoreError, ClientError

from app.crypto.envelope import EnvelopeError

if TYPE_CHECKING:
    from mypy_boto3_kms import KMSClient

_PREFIX = "kms:"
# Bound into every wrap, so a data key can only be unwrapped for this purpose.
ENCRYPTION_CONTEXT = {"purpose": "rag-agent-studio/envelope-data-key"}


class KmsKeyWrapper:
    def __init__(self, client: "KMSClient", key_arn: str) -> None:
        self._client = client
        self._key_arn = key_arn

    @property
    def key_id(self) -> str:
        return _PREFIX + self._key_arn

    def wrap(self, data_key: bytes) -> bytes:
        response = self._client.encrypt(
            KeyId=self._key_arn, Plaintext=data_key, EncryptionContext=ENCRYPTION_CONTEXT
        )
        return response["CiphertextBlob"]

    def unwrap(self, key_id: str, wrapped: bytes) -> bytes:
        if not key_id.startswith(_PREFIX):
            raise EnvelopeError(f"Sealed under key {key_id!r}, which is not a KMS key")
        try:
            response = self._client.decrypt(
                CiphertextBlob=wrapped,
                KeyId=key_id.removeprefix(_PREFIX),
                EncryptionContext=ENCRYPTION_CONTEXT,
            )
        except (ClientError, BotoCoreError) as exc:
            raise EnvelopeError("KMS could not unwrap the data key") from exc
        return response["Plaintext"]
