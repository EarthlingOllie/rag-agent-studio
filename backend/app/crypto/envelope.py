"""Envelope encryption: each record is sealed with its own AES-256-GCM data key.

The data key is wrapped by a ``KeyWrapper`` (the local static-key wrapper in ``docker compose``
and tests, AWS KMS in AWS) and stored next to the ciphertext. Format, version 1::

    version (1 byte = 0x01)
    key ID length (1 byte) | key ID (UTF-8)
    wrapped data key length (2 bytes, big endian) | wrapped data key
    nonce (12 bytes)
    ciphertext + GCM tag (16 bytes)

Everything before the nonce, plus the caller's ``context``, is authenticated as associated
data, so changing any byte, or opening a record under another context (another Member's
secret, say), fails.
"""

import os
import struct
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FORMAT_VERSION = 1
NONCE_BYTES = 12
DATA_KEY_BYTES = 32


class EnvelopeError(Exception):
    """A sealed record could not be opened: tampered, truncated, unknown version or key."""


class KeyWrapper(Protocol):
    """Wraps and unwraps data keys under a key the application never stores with the data."""

    @property
    def key_id(self) -> str:
        """Names the wrapping key, so records say which key opens them."""
        ...

    def wrap(self, data_key: bytes) -> bytes: ...

    def unwrap(self, key_id: str, wrapped: bytes) -> bytes:
        """The data key; raises ``EnvelopeError`` if it can't be unwrapped."""
        ...


class EnvelopeEncryption:
    def __init__(self, wrapper: KeyWrapper) -> None:
        self._wrapper = wrapper

    def seal(self, plaintext: bytes, *, context: bytes) -> bytes:
        data_key = AESGCM.generate_key(bit_length=DATA_KEY_BYTES * 8)
        key_id = self._wrapper.key_id.encode()
        wrapped = self._wrapper.wrap(data_key)
        header = (
            struct.pack(">BB", FORMAT_VERSION, len(key_id))
            + key_id
            + struct.pack(">H", len(wrapped))
            + wrapped
        )
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = AESGCM(data_key).encrypt(nonce, plaintext, header + context)
        return header + nonce + ciphertext

    def open(self, sealed: bytes, *, context: bytes) -> bytes:
        try:
            version, key_id_length = struct.unpack_from(">BB", sealed)
            if version != FORMAT_VERSION:
                raise EnvelopeError(f"Unknown envelope format version {version}")
            offset = 2 + key_id_length
            key_id = sealed[2:offset].decode()
            (wrapped_length,) = struct.unpack_from(">H", sealed, offset)
            offset += 2
            wrapped = sealed[offset : offset + wrapped_length]
            offset += wrapped_length
        except (struct.error, UnicodeDecodeError) as exc:
            raise EnvelopeError("Truncated or malformed envelope") from exc
        header, nonce, ciphertext = (
            sealed[:offset],
            sealed[offset : offset + NONCE_BYTES],
            sealed[offset + NONCE_BYTES :],
        )
        data_key = self._wrapper.unwrap(key_id, wrapped)
        try:
            return AESGCM(data_key).decrypt(nonce, ciphertext, header + context)
        except (InvalidTag, ValueError) as exc:
            raise EnvelopeError("The envelope failed authentication") from exc
