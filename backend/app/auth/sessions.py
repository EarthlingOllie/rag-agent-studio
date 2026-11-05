"""Server-side sessions in Redis, referenced by an opaque token in a cookie.

Redis holds only a SHA-256 of the token, so reading Redis doesn't yield usable cookies.
"""

import hashlib
import secrets
import uuid
from typing import cast

from redis.asyncio import Redis

SESSION_COOKIE = "studio_session"
_KEY_PREFIX = "session:"


def _key(token: str) -> str:
    return _KEY_PREFIX + hashlib.sha256(token.encode()).hexdigest()


class SessionStore:
    def __init__(self, redis: "Redis", ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    async def create(self, member_id: uuid.UUID) -> str:
        """Starts a session and returns its token, which goes only in the cookie."""
        token = secrets.token_urlsafe(32)
        await self._redis.set(_key(token), str(member_id), ex=self._ttl_seconds)
        return token

    async def member_id(self, token: str) -> uuid.UUID | None:
        # The app's client doesn't decode responses, so values come back as bytes.
        value = cast(bytes | None, await self._redis.get(_key(token)))
        return None if value is None else uuid.UUID(value.decode())

    async def delete(self, token: str) -> None:
        await self._redis.delete(_key(token))
