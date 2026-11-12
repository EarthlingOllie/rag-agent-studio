"""The invite email limit: how many invite emails an Owner and an Organisation may send.

Invite emails go to any address an Owner types, with names the Owner chose, so unlimited
sending would make the Studio a spam relay. Each send is counted in two sliding one-hour
windows in Redis, one per Owner (across all their Organisations) and one per Organisation.
A send is allowed only if both windows hold fewer than their limit, and only then is it
counted in both, so refused sends never count. The check and the count are one Lua script,
so concurrent sends can't both take the last place.

Only emails are limited: an Invite whose email is refused is still created (or renewed), and
the Owner can copy its link.

Times come from the Clock port, not from Redis, so tests can move time forward. Redis expiry
only clears windows nobody has used for longer than a window.
"""

import secrets
import uuid

from redis.asyncio import Redis

from app.core.clock import Clock

WINDOW_SECONDS = 60 * 60
PER_OWNER_LIMIT = 20
PER_ORGANISATION_LIMIT = 50
_KEY_PREFIX = "invite-emails:"
# Seconds kept in Redis beyond the window, so a window never expires while it still counts.
_EXPIRY_MARGIN_SECONDS = 60

# KEYS: the windows. ARGV: now, the window length, a unique member, the expiry, then each
# window's limit. Returns 1 when allowed (and counted in every window), else 0.
_ALLOW = """
local now = tonumber(ARGV[1])
for i, key in ipairs(KEYS) do
  redis.call('ZREMRANGEBYSCORE', key, '-inf', now - tonumber(ARGV[2]))
  if redis.call('ZCARD', key) >= tonumber(ARGV[4 + i]) then
    return 0
  end
end
for _, key in ipairs(KEYS) do
  redis.call('ZADD', key, now, ARGV[3])
  redis.call('EXPIRE', key, ARGV[4])
end
return 1
"""


class InviteEmailThrottle:
    def __init__(self, redis: "Redis", clock: Clock) -> None:
        self._redis = redis
        self._clock = clock

    async def allow(self, *, organisation_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        """Whether one more invite email may be sent now; if so, it is counted."""
        keys = [f"{_KEY_PREFIX}owner:{owner_id}", f"{_KEY_PREFIX}organisation:{organisation_id}"]
        allowed = await self._redis.eval(
            _ALLOW,
            len(keys),
            *keys,
            str(self._clock.now().timestamp()),
            WINDOW_SECONDS,
            secrets.token_hex(8),
            WINDOW_SECONDS + _EXPIRY_MARGIN_SECONDS,
            PER_OWNER_LIMIT,
            PER_ORGANISATION_LIMIT,
        )
        return int(allowed) == 1
