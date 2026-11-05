"""The local static-key wrapper: AES-256-GCM under one key from the environment.

Used in ``docker compose`` and tests in place of AWS KMS (spec 01 shared test seams).
"""

import base64
import binascii
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.crypto.envelope import NONCE_BYTES, EnvelopeError

_ASSOCIATED_DATA = b"rag-agent-studio/local-key-wrapper/v1"


class LocalKeyWrapper:
    def __init__(self, key_base64: str) -> None:
        try:
            key = base64.b64decode(key_base64, validate=True)
        except binascii.Error:
            key = b""
        if len(key) != 32:
            raise ValueError("The local key wrapper key must be 32 bytes, base64-encoded")
        self._aead = AESGCM(key)
        # A fingerprint, not the key: enough to tell which key sealed a record.
        self._key_id = "local:" + hashlib.sha256(b"key-id:" + key).hexdigest()[:16]

    @property
    def key_id(self) -> str:
        return self._key_id

    def wrap(self, data_key: bytes) -> bytes:
        nonce = os.urandom(NONCE_BYTES)
        return nonce + self._aead.encrypt(nonce, data_key, _ASSOCIATED_DATA)

    def unwrap(self, key_id: str, wrapped: bytes) -> bytes:
        if key_id != self._key_id:
            raise EnvelopeError(f"Sealed under key {key_id!r}, which this wrapper doesn't hold")
        try:
            return self._aead.decrypt(
                wrapped[:NONCE_BYTES], wrapped[NONCE_BYTES:], _ASSOCIATED_DATA
            )
        except (InvalidTag, ValueError) as exc:
            raise EnvelopeError("The wrapped data key failed authentication") from exc
