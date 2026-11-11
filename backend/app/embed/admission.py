"""Admission control: whether a Visitor's message may be answered now.

``admit`` first checks the Agent's Token Budget: the tokens its Visitor replies have used on
the current UTC date, a Redis counter keyed by Agent and date that ``record_usage`` increments
with each reply's actual usage. Once the day's usage reaches the budget, messages are refused
until the budget is raised or the date changes (midnight UTC starts a new counter, so the reset
needs no job).

Then ``admit`` checks the Agent's rate limits (Operational Settings) with sliding one-minute windows
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
from datetime import UTC, date, datetime

from redis.asyncio import Redis

from app.core.clock import Clock

WINDOW_SECONDS = 60
_KEY_PREFIX = "widget-rate:"
# Seconds kept in Redis beyond the window, so a window never expires while it still counts.
_EXPIRY_MARGIN_SECONDS = 60
_BUDGET_PREFIX = "widget-budget:"
# A day's counter outlives its day, then expires.
_BUDGET_EXPIRY_SECONDS = 2 * 24 * 60 * 60

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

    TOKEN_BUDGET = "token_budget"  # noqa: S105 (a reason, not a secret)
    CONVERSATION_RATE = "conversation_rate"
    IP_RATE = "ip_rate"


@dataclass(frozen=True)
class Limits:
    """An Agent's rate limits and Token Budget, from its Operational Settings."""

    public_id: str
    conversation_messages_per_minute: int
    ip_messages_per_minute: int
    daily_token_budget: int


def utc_date(moment: datetime) -> date:
    """The UTC date a moment falls on: the day whose Token Budget it uses."""
    return moment.astimezone(UTC).date()


def _budget_key(public_id: str, day: date) -> str:
    return f"{_BUDGET_PREFIX}{public_id}:{day.isoformat()}"


class Admission:
    def __init__(self, redis: "Redis", clock: Clock) -> None:
        self._redis = redis
        self._clock = clock

    async def admit(self, agent: Limits, token: str, ip: str) -> Refusal | None:
        """None when the message is admitted (and counted), else why it was refused."""
        now_at = self._clock.now()
        if await self.tokens_used(agent.public_id, utc_date(now_at)) >= agent.daily_token_budget:
            return Refusal.TOKEN_BUDGET
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
        now = now_at.timestamp()
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

    async def tokens_used(self, public_id: str, day: date) -> int:
        """The tokens the Agent's Visitor replies used on that UTC date."""
        used = await self._redis.get(_budget_key(public_id, day))
        return 0 if used is None else int(used)

    async def record_usage(self, public_id: str, tokens: int) -> int:
        """Adds a reply's actual usage to today's counter (the date of the Clock now); returns
        the day's usage so far."""
        key = _budget_key(public_id, utc_date(self._clock.now()))
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incrby(key, tokens)
            pipe.expire(key, _BUDGET_EXPIRY_SECONDS)
            total, _ = await pipe.execute()
        return int(total)
