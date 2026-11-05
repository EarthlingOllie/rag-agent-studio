"""Sign-ins that passed the password check and wait for an MFA code ("MFA pending").

Like sessions, they live in Redis under a SHA-256 of an opaque token held in a cookie. They
expire after ``MFA_PENDING_TTL_SECONDS`` and after ``MAX_ATTEMPTS`` wrong codes.
"""

import hashlib
import secrets
import uuid
from typing import cast

from redis.asyncio import Redis

MFA_PENDING_COOKIE = "studio_mfa_pending"
MAX_ATTEMPTS = 5
_KEY_PREFIX = "mfa-pending:"


def _key(token: str) -> str:
    return _KEY_PREFIX + hashlib.sha256(token.encode()).hexdigest()


class PendingSignIns:
    def __init__(self, redis: "Redis", ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    async def create(self, member_id: uuid.UUID) -> str:
        token = secrets.token_urlsafe(32)
        key = _key(token)
        await self._redis.hset(key, mapping={"member_id": str(member_id), "attempts": 0})
        await self._redis.expire(key, self._ttl_seconds)
        return token

    async def member_id(self, token: str) -> uuid.UUID | None:
        value = cast(bytes | None, await self._redis.hget(_key(token), "member_id"))
        return None if value is None else uuid.UUID(value.decode())

    async def record_failure(self, token: str) -> None:
        """Counts a wrong code; the pending sign-in ends at ``MAX_ATTEMPTS``."""
        key = _key(token)
        attempts = await self._redis.hincrby(key, "attempts", 1)
        if attempts >= MAX_ATTEMPTS:
            await self._redis.delete(key)

    async def delete(self, token: str) -> None:
        await self._redis.delete(_key(token))
