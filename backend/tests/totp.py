"""An RFC 6238 TOTP generator written for the tests, independent of the app's implementation."""

import base64
import hashlib
import hmac
import struct
from datetime import datetime


def totp(secret_base32: str, at: datetime, *, step_offset: int = 0) -> str:
    """The six-digit SHA-1 code for ``at`` (plus ``step_offset`` 30-second steps)."""
    key = base64.b32decode(secret_base32 + "=" * (-len(secret_base32) % 8))
    return hotp(key, int(at.timestamp()) // 30 + step_offset)


def hotp(key: bytes, counter: int) -> str:
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"
