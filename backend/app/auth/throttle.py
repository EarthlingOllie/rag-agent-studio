"""Sign-in protection: counters per account and per IP address in Redis.

Each counter remembers how many sign-ins failed and when the last one did. A few failures
are free; after that every attempt must wait a progressively longer delay, and after more
the counter locks sign-in out for a while. Attempts refused this way are not counted, so
waiting out a lockout always works. A counter is forgotten when the next failure comes
the lockout length or more after the last one; by then no delay or lockout applies.

Times come from the Clock port, not from Redis expiry, so tests can move time forward.
Redis expiry only clears counters nobody has touched for longer than that.
"""

import enum
import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from redis.asyncio import Redis

from app.core.clock import Clock
from app.core.settings import Settings

_KEY_PREFIX = "sign-in-failures:"
# Seconds kept in Redis beyond the lockout, so a counter never expires while it still counts.
_EXPIRY_MARGIN_SECONDS = 60

# Atomically: forget a stale counter, count one more failure and stamp its time.
_RECORD_FAILURE = """
local last = tonumber(redis.call('HGET', KEYS[1], 'last'))
local now = tonumber(ARGV[1])
if last and now - last >= tonumber(ARGV[2]) then
  redis.call('DEL', KEYS[1])
end
local failures = redis.call('HINCRBY', KEYS[1], 'failures', 1)
redis.call('HSET', KEYS[1], 'last', ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[3])
return failures
"""


class CounterScope(enum.StrEnum):
    ACCOUNT = "account"
    IP = "ip"


@dataclass(frozen=True)
class Refusal:
    """Sign-in is refused without checking the password until ``retry_after_seconds`` pass."""

    retry_after_seconds: int
    locked: bool


@dataclass(frozen=True)
class Lockout:
    """A failure that has just locked one counter."""

    scope: CounterScope
    failures: int
    locked_until: datetime


@dataclass(frozen=True)
class _Limits:
    delay_after: int
    lockout_after: int


class SignInThrottle:
    def __init__(self, redis: "Redis", clock: Clock, settings: Settings) -> None:
        self._redis = redis
        self._clock = clock
        self._delay_base = settings.sign_in_delay_base_seconds
        self._delay_max = settings.sign_in_delay_max_seconds
        self._lockout_seconds = settings.sign_in_lockout_seconds
        self._limits = {
            CounterScope.ACCOUNT: _Limits(
                settings.sign_in_account_delay_after_failures,
                settings.sign_in_account_lockout_after_failures,
            ),
            CounterScope.IP: _Limits(
                settings.sign_in_ip_delay_after_failures,
                settings.sign_in_ip_lockout_after_failures,
            ),
        }

    def _keys(self, email: str, ip: str) -> dict[CounterScope, str]:
        # The email is hashed so Redis holds no addresses; unknown emails count the same way.
        account = hashlib.sha256(email.encode()).hexdigest()
        return {
            CounterScope.ACCOUNT: f"{_KEY_PREFIX}account:{account}",
            CounterScope.IP: f"{_KEY_PREFIX}ip:{ip}",
        }

    def _blocked_for(self, scope: CounterScope, failures: int) -> tuple[int, bool] | None:
        """How long after the last failure attempts are refused, and whether that is a lockout."""
        limits = self._limits[scope]
        if failures >= limits.lockout_after:
            return self._lockout_seconds, True
        if failures < limits.delay_after:
            return None
        delay = self._delay_base * 2 ** (failures - limits.delay_after)
        return min(delay, self._delay_max), False

    async def check(self, email: str, ip: str) -> Refusal | None:
        """A refusal if either counter currently blocks this attempt, else None."""
        now = self._clock.now().timestamp()
        refusals = []
        for scope, key in self._keys(email, ip).items():
            failures, last = cast(
                list[bytes | None], await self._redis.hmget(key, "failures", "last")
            )
            if failures is None or last is None:
                continue
            blocked = self._blocked_for(scope, int(failures))
            if blocked is None:
                continue
            seconds, locked = blocked
            remaining = float(last) + seconds - now
            if remaining > 0:
                refusals.append(Refusal(math.ceil(remaining), locked))
        if not refusals:
            return None
        return Refusal(
            max(r.retry_after_seconds for r in refusals), any(r.locked for r in refusals)
        )

    async def record_failure(self, email: str, ip: str) -> list[Lockout]:
        """Counts a failed sign-in on both counters; returns the counters it has just locked."""
        now = self._clock.now()
        expiry = self._lockout_seconds + _EXPIRY_MARGIN_SECONDS
        lockouts = []
        for scope, key in self._keys(email, ip).items():
            failures = int(
                await self._redis.eval(
                    _RECORD_FAILURE, 1, key, str(now.timestamp()), self._lockout_seconds, expiry
                )
            )
            if failures == self._limits[scope].lockout_after:
                locked_until = now + timedelta(seconds=self._lockout_seconds)
                lockouts.append(Lockout(scope, failures, locked_until))
        return lockouts

    async def record_success(self, email: str, ip: str) -> None:
        """A successful sign-in clears the account's counter; the IP's keeps counting."""
        await self._redis.delete(self._keys(email, ip)[CounterScope.ACCOUNT])
