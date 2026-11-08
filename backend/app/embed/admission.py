"""Admission control: whether a Visitor's message may be answered now.

``admit`` checks the Agent's rate limits (Operational Settings) with sliding one-minute windows
in Redis: one per Conversation token and one per IP address for that Agent. Each window is a
sorted set of the admitted messages' times; a message is admitted only if both windows hold
fewer than their limit, and only then is it counted in both, so refused messages never count
and waiting always works. The check and the count are one Lua script, so concurrent messages
can't both take the last place.

Times come from the Clock port, not from Redis, so tests can move time forward. Redis expiry
only clears windows nobody has used for longer than a window.

The Playground never comes through here: it is exempt.
"""

import enum
import hashlib
import secrets
from dataclasses import dataclass

from redis.asyncio import Redis

from app.core.clock import Clock

WINDOW_SECONDS = 60
_KEY_PREFIX = "widget-rate:"
# Seconds kept in Redis beyond the window, so a window never expires while it still counts.
_EXPIRY_MARGIN_SECONDS = 60

# KEYS: the windows. ARGV: now, the window length, a unique member, the expiry, then each
# window's limit. Returns 0 when admitted (and counted in every window), else the 1-based
# index of the first window that is full.
_ADMIT = """
local now = tonumber(ARGV[1])
for i, key in ipairs(KEYS) do
  redis.call('ZREMRANGEBYSCORE', key, '-inf', now - tonumber(ARGV[2]))
  if redis.call('ZCARD', key) >= tonumber(ARGV[4 + i]) then
    return i
  end
end
for _, key in ipairs(KEYS) do
  redis.call('ZADD', key, now, ARGV[3])
  redis.call('EXPIRE', key, ARGV[4])
end
return 0
"""


class Refusal(enum.StrEnum):
    """Why a message wasn't admitted."""

    CONVERSATION_RATE = "conversation_rate"
    IP_RATE = "ip_rate"


@dataclass(frozen=True)
class Limits:
    """An Agent's rate limits, from its Operational Settings."""

    public_id: str
    conversation_messages_per_minute: int
    ip_messages_per_minute: int


class Admission:
    def __init__(self, redis: "Redis", clock: Clock) -> None:
        self._redis = redis
        self._clock = clock

    async def admit(self, agent: Limits, token: str, ip: str) -> Refusal | None:
        """None when the message is admitted (and counted), else why it was refused."""
        # The token is hashed so Redis never holds a usable one.
        conversation = hashlib.sha256(token.encode()).hexdigest()
        windows = [
            (
                Refusal.CONVERSATION_RATE,
                f"{_KEY_PREFIX}conversation:{conversation}",
                agent.conversation_messages_per_minute,
            ),
            (
                Refusal.IP_RATE,
                f"{_KEY_PREFIX}ip:{agent.public_id}:{ip}",
                agent.ip_messages_per_minute,
            ),
        ]
        now = self._clock.now().timestamp()
        full = int(
            await self._redis.eval(
                _ADMIT,
                len(windows),
                *(key for _, key, _ in windows),
                str(now),
                WINDOW_SECONDS,
                f"{now}:{secrets.token_hex(8)}",
                WINDOW_SECONDS + _EXPIRY_MARGIN_SECONDS,
                *(limit for _, _, limit in windows),
            )
        )
        return None if full == 0 else windows[full - 1][0]
