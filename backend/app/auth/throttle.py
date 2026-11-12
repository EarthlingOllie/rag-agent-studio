"""Sign-in protection: failure counters per account, per IP address and per Member's MFA codes,
and limits on password-reset requests per email and per IP address, all in Redis.

Each counter remembers how many sign-ins failed and when the last one did. A few failures
are free; after that every attempt must wait a progressively longer delay, and after more
the counter locks sign-in out for a while. Attempts refused this way are not counted, so
waiting out a lockout always works. A counter is forgotten when the next failure comes
the lockout length or more after the last one; by then no delay or lockout applies.

MFA codes are counted per Member, apart from the password's counters: a correct password
doesn't clear them, so signing in again doesn't buy fresh guesses at a code (AUTH-F1). Only a
correct code clears them. Each try at a code is counted before the code is checked, in one
atomic step with the throttle check, so parallel tries can't all pass the check uncounted.

Times come from the Clock port, not from Redis expiry, so tests can move time forward.
Redis expiry only clears counters nobody has touched for longer than that.
"""

import enum
import hashlib
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from redis.asyncio import Redis

from app.core.clock import Clock
from app.core.settings import Settings

# Every key of this module starts with this (tests clear it between tests).
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
    MFA = "mfa"


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


class _FailureCounters:
    """Failure counters with free failures, then growing delays, then a lockout."""

    def __init__(
        self, redis: "Redis", clock: Clock, settings: Settings, limits: dict[CounterScope, _Limits]
    ) -> None:
        self._redis = redis
        self._clock = clock
        self._delay_base = settings.sign_in_delay_base_seconds
        self._delay_max = settings.sign_in_delay_max_seconds
        self._lockout_seconds = settings.sign_in_lockout_seconds
        self._limits = limits

    def _blocked_for(self, scope: CounterScope, failures: int) -> tuple[int, bool] | None:
        """How long after the last failure attempts are refused, and whether that is a lockout."""
        limits = self._limits[scope]
        if failures >= limits.lockout_after:
            return self._lockout_seconds, True
        if failures < limits.delay_after:
            return None
        delay = self._delay_base * 2 ** (failures - limits.delay_after)
        return min(delay, self._delay_max), False

    async def _check(self, keys: dict[CounterScope, str]) -> Refusal | None:
        """A refusal if any counter currently blocks this attempt, else None."""
        now = self._clock.now().timestamp()
        refusals = []
        for scope, key in keys.items():
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

    async def _record_failure(self, keys: dict[CounterScope, str]) -> list[Lockout]:
        """Counts a failure on every counter; returns the counters it has just locked."""
        now = self._clock.now()
        expiry = self._lockout_seconds + _EXPIRY_MARGIN_SECONDS
        lockouts = []
        for scope, key in keys.items():
            failures = int(
                await self._redis.eval(
                    _RECORD_FAILURE, 1, key, str(now.timestamp()), self._lockout_seconds, expiry
                )
            )
            if failures == self._limits[scope].lockout_after:
                locked_until = now + timedelta(seconds=self._lockout_seconds)
                lockouts.append(Lockout(scope, failures, locked_until))
        return lockouts


class SignInThrottle(_FailureCounters):
    def __init__(self, redis: "Redis", clock: Clock, settings: Settings) -> None:
        super().__init__(
            redis,
            clock,
            settings,
            {
                CounterScope.ACCOUNT: _Limits(
                    settings.sign_in_account_delay_after_failures,
                    settings.sign_in_account_lockout_after_failures,
                ),
                CounterScope.IP: _Limits(
                    settings.sign_in_ip_delay_after_failures,
                    settings.sign_in_ip_lockout_after_failures,
                ),
            },
        )

    def _keys(self, email: str, ip: str) -> dict[CounterScope, str]:
        return {
            CounterScope.ACCOUNT: f"{_KEY_PREFIX}account:{_email_hash(email)}",
            CounterScope.IP: f"{_KEY_PREFIX}ip:{ip}",
        }

    async def check(self, email: str, ip: str) -> Refusal | None:
        """A refusal if either counter currently blocks this attempt, else None."""
        return await self._check(self._keys(email, ip))

    async def record_failure(self, email: str, ip: str) -> list[Lockout]:
        """Counts a failed sign-in on both counters; returns the counters it has just locked."""
        return await self._record_failure(self._keys(email, ip))

    async def record_success(self, email: str, ip: str) -> None:
        """A successful sign-in clears the account's counter; the IP's keeps counting.

        It leaves the Member's MFA counter alone: a password is not a code."""
        await self._redis.delete(self._keys(email, ip)[CounterScope.ACCOUNT])


# Wrong MFA codes per Member: one pending sign-in's five attempts are free, then each code
# waits progressively longer, and the tenth locks the Member's codes out for the sign-in
# lockout length. The delays and the lockout length are the sign-in settings.
MFA_DELAY_AFTER_FAILURES = 5
MFA_LOCKOUT_AFTER_FAILURES = 10


# Atomically: forget a stale counter; refuse while the counter blocks another attempt (returns
# 0, the seconds remaining as text and 1 if locked); otherwise count this attempt as a wrong
# code before it is checked and stamp its time (returns 1 and the count). Counting before the
# check means parallel attempts can't all pass the throttle before any of them is counted.
_RESERVE_ATTEMPT = """
local now = tonumber(ARGV[1])
local lockout_seconds = tonumber(ARGV[2])
local delay_after = tonumber(ARGV[3])
local lockout_after = tonumber(ARGV[4])
local failures = tonumber(redis.call('HGET', KEYS[1], 'failures'))
local last = tonumber(redis.call('HGET', KEYS[1], 'last'))
if last and now - last >= lockout_seconds then
  redis.call('DEL', KEYS[1])
elseif failures and last and failures >= delay_after then
  local wait = lockout_seconds
  local locked = 1
  if failures < lockout_after then
    wait = math.min(tonumber(ARGV[5]) * 2 ^ (failures - delay_after), tonumber(ARGV[6]))
    locked = 0
  end
  local remaining = last + wait - now
  if remaining > 0 then
    return {0, tostring(remaining), locked}
  end
end
failures = redis.call('HINCRBY', KEYS[1], 'failures', 1)
redis.call('HSET', KEYS[1], 'last', ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[7])
return {1, failures}
"""


@dataclass(frozen=True)
class MfaAttempt:
    """An attempt at a code, already counted as wrong; a correct code clears the count."""

    lockout_if_wrong: Lockout | None


class MfaThrottle(_FailureCounters):
    def __init__(self, redis: "Redis", clock: Clock, settings: Settings) -> None:
        super().__init__(
            redis,
            clock,
            settings,
            {CounterScope.MFA: _Limits(MFA_DELAY_AFTER_FAILURES, MFA_LOCKOUT_AFTER_FAILURES)},
        )

    def _key(self, member_id: uuid.UUID) -> str:
        return f"{_KEY_PREFIX}mfa:{member_id}"

    async def attempt(self, member_id: uuid.UUID) -> Refusal | MfaAttempt:
        """A refusal if the Member's wrong codes currently block another try; otherwise the
        try is counted as a wrong code, atomically, before the code is checked."""
        now = self._clock.now()
        result = cast(
            list[bytes | int],
            await self._redis.eval(
                _RESERVE_ATTEMPT,
                1,
                self._key(member_id),
                str(now.timestamp()),
                self._lockout_seconds,
                MFA_DELAY_AFTER_FAILURES,
                MFA_LOCKOUT_AFTER_FAILURES,
                self._delay_base,
                self._delay_max,
                self._lockout_seconds + _EXPIRY_MARGIN_SECONDS,
            ),
        )
        if result[0] == 0:
            return Refusal(math.ceil(float(result[1])), bool(result[2]))
        failures = int(result[1])
        if failures != MFA_LOCKOUT_AFTER_FAILURES:
            return MfaAttempt(None)
        locked_until = now + timedelta(seconds=self._lockout_seconds)
        return MfaAttempt(Lockout(CounterScope.MFA, failures, locked_until))

    async def record_success(self, member_id: uuid.UUID) -> None:
        """A correct code clears the Member's wrong-code counter."""
        await self._redis.delete(self._key(member_id))


def _email_hash(email: str) -> str:
    # The email is hashed so Redis holds no addresses; unknown emails count the same way.
    return hashlib.sha256(email.encode()).hexdigest()


# Password-reset emails: per email address and per IP address, at most this many requests are
# acted on in an hour from the first. Over either limit the request is answered the same but
# sends nothing (AUTH-R2-F2).
RESETS_PER_EMAIL = 3
RESETS_PER_IP = 20
RESET_WINDOW_SECONDS = 60 * 60

# Atomically, for every key (with its limit in ARGV[2 + i]): forget a window that has ended,
# and refuse if any key is at its limit; otherwise count the request on every key.
_ALLOW_REQUEST = """
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
for i, key in ipairs(KEYS) do
  local start = tonumber(redis.call('HGET', key, 'start'))
  if start and now - start >= window then
    redis.call('DEL', key)
  end
end
for i, key in ipairs(KEYS) do
  local count = tonumber(redis.call('HGET', key, 'count') or '0')
  if count >= tonumber(ARGV[2 + i]) then
    return 0
  end
end
for i, key in ipairs(KEYS) do
  redis.call('HINCRBY', key, 'count', 1)
  redis.call('HSETNX', key, 'start', ARGV[1])
  redis.call('EXPIRE', key, window + tonumber(ARGV[3 + #KEYS]))
end
return 1
"""


class PasswordResetLimit:
    def __init__(self, redis: "Redis", clock: Clock) -> None:
        self._redis = redis
        self._clock = clock

    async def allow(self, email: str, ip: str) -> bool:
        """Whether to act on a reset request; counts it when it is allowed."""
        keys = [
            f"{_KEY_PREFIX}password-reset:email:{_email_hash(email)}",
            f"{_KEY_PREFIX}password-reset:ip:{ip}",
        ]
        allowed = await self._redis.eval(
            _ALLOW_REQUEST,
            len(keys),
            *keys,
            str(self._clock.now().timestamp()),
            RESET_WINDOW_SECONDS,
            RESETS_PER_EMAIL,
            RESETS_PER_IP,
            _EXPIRY_MARGIN_SECONDS,
        )
        return bool(allowed)
