"""Admission control: whether a message may be answered now, and the cost it reserves.

Visitors (``admit``): first the Agent's Token Budget: the tokens its Visitor replies have used on
the current UTC date, a Redis counter keyed by Agent and date that ``record_usage`` increments
with each reply's actual usage. Once the day's usage reaches the budget, messages are refused
until the budget is raised or the date changes (midnight UTC starts a new counter, so the reset
needs no job).

A reply's usage is only known once it has streamed, so admission also reserves an estimate of
its cost (``RESERVED_TOKENS``) in a per-Agent set of in-flight reservations. While the day's
usage plus the tokens held by replies still streaming reaches the budget, further messages are
refused as busy (not as a spent budget: they may try again shortly). ``record_usage`` settles a
reservation with the reply's actual usage; ``release`` gives one back when no reply is recorded
(a provider failure, a turn that couldn't be prepared, a client that went away). So concurrent
messages can't all pass the same "under budget" check.

A reply can cost more than it reserved (its cost has no fixed ceiling: an agentic reply makes
several model calls), so admission also caps the replies in flight: ``REPLIES_IN_FLIGHT`` (4)
per Agent, and one per address (``Limits.replies_in_flight_per_address``). The bound: a message
is admitted only while the day's usage is under the budget, so however much each reply costs,
the day ends at most ``REPLIES_IN_FLIGHT`` replies over its Token Budget. And the Agent stays
available: it answers that many Visitors at once, and one client (one address) holds at most
one of those places.

A place is held only while its reply's response lasts. A reservation is a lease of
``LEASE_SECONDS`` that ``hold`` renews while the response is being sent (``HeldStream``), for
at most ``LONGEST_REPLY_SECONDS``; the response gives the reservation back however it ends,
even when the client went away before the stream started. A reservation nothing renews (its
process died) lapses after one lease.

Then ``admit`` checks the Agent's rate limits (Operational Settings) with sliding one-minute
windows in Redis: one per Conversation token, one per IP address for that Agent, and one for the
Agent as a whole (``AGENT_MESSAGES_PER_MINUTE``), which also bounds clients that send no Origin
from many addresses. Each window
is a sorted set of the admitted messages' times; a message is admitted only if every window holds
fewer than its limit, and only then is it counted in each, so refused messages never count
and waiting always works. The budget check, the reservation and the windows are one Lua script,
so concurrent messages can't both take the last place.

The Playground (``admit_playground``) has its own limits, separate from Visitors': a rate limit
per Member and per Organisation, and a daily Playground Token Budget per Organisation, reserved
and settled the same way (``record_playground_usage``), with at most
``PlaygroundLimits.answers_in_flight`` answers streaming per Organisation at once. Its usage
never counts against an Agent's Visitor budget.

Times come from the Clock port, not from Redis, so tests can move time forward. Redis expiry
only clears windows nobody has used for longer than a window.
"""

import asyncio
import enum
import hashlib
import secrets
import uuid
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import UTC, date, datetime

import anyio
from redis.asyncio import Redis
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from app.agents.config import MAX_OUTPUT_TOKENS_MAX
from app.core.clock import Clock

WINDOW_SECONDS = 60
_KEY_PREFIX = "widget-rate:"
# Seconds kept in Redis beyond the window, so a window never expires while it still counts.
_EXPIRY_MARGIN_SECONDS = 60
_BUDGET_PREFIX = "widget-budget:"
_RESERVED_PREFIX = "widget-reserved:"
_PLAYGROUND_RATE_PREFIX = "playground-rate:"
_PLAYGROUND_BUDGET_PREFIX = "playground-budget:"
_PLAYGROUND_RESERVED_PREFIX = "playground-reserved:"
# A day's counter outlives its day, then expires.
_BUDGET_EXPIRY_SECONDS = 2 * 24 * 60 * 60
# The cost a reply reserves while it streams: the most output any Agent may be configured to
# write in one reply. Settled with the actual usage when the reply is recorded.
RESERVED_TOKENS = MAX_OUTPUT_TOKENS_MAX
# A reservation lapses this long after it was made or last renewed: while its response lasts,
# ``hold`` renews it every ``RENEW_SECONDS``, so it outlives only a response nobody sends.
LEASE_SECONDS = 30
RENEW_SECONDS = 10
# The in-flight reservations' key outlives every lease in it.
_RESERVATIONS_EXPIRY_SECONDS = LEASE_SECONDS + _EXPIRY_MARGIN_SECONDS
# The longest a reply's response renews its reservation: a response still open after this (a
# client that stopped reading) no longer holds a place.
LONGEST_REPLY_SECONDS = 5 * 60
# Messages an Agent answers per minute across all its Conversations and addresses: a bound on
# clients that send no Origin (so no Allowed Origins check applies) from many addresses.
AGENT_MESSAGES_PER_MINUTE = 120
# A reply's actual cost has no fixed ceiling (an agentic reply makes several model calls, each
# carrying the prompt, Chunks and history), so a reservation can be exceeded. So at most this
# many replies of one Agent stream at once: however much each costs, the day ends at most this
# many replies over its Token Budget.
REPLIES_IN_FLIGHT = 4

# KEYS: the day's budget counter, the in-flight reservations, then the windows. ARGV: now, the
# window length, a unique member, the windows' expiry, the budget, the reservation's ID, its
# tokens, when its lease lapses, the reservations' expiry, the most replies in flight, the most
# for one holder, the holder (an address's hash, or a Member), then each window's limit.
# A reservation is the member "ID:holder:tokens", scored by when its lease lapses.
# Returns 0 when admitted (counted in every window, its cost reserved); -1 when the day's budget
# is spent; -2 when replies still streaming hold the rest of it, or as many replies as may be in
# flight (in all, or for the holder) are; else the 1-based index of the first window that is
# full.
_ADMIT = """
local now = tonumber(ARGV[1])
local budget = tonumber(ARGV[5])
local used = tonumber(redis.call('GET', KEYS[1]) or '0')
if used >= budget then
  return -1
end
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now)
local held = 0
local mine = 0
local holder = ':' .. ARGV[12] .. ':'
for _, reservation in ipairs(redis.call('ZRANGE', KEYS[2], 0, -1)) do
  held = held + tonumber(string.match(reservation, ':(%d+)$'))
  if string.find(reservation, holder, 1, true) then
    mine = mine + 1
  end
end
if used + held >= budget or redis.call('ZCARD', KEYS[2]) >= tonumber(ARGV[10])
    or mine >= tonumber(ARGV[11]) then
  return -2
end
for i = 3, #KEYS do
  redis.call('ZREMRANGEBYSCORE', KEYS[i], '-inf', now - tonumber(ARGV[2]))
  if redis.call('ZCARD', KEYS[i]) >= tonumber(ARGV[10 + i]) then
    return i - 2
  end
end
for i = 3, #KEYS do
  redis.call('ZADD', KEYS[i], now, ARGV[3])
  redis.call('EXPIRE', KEYS[i], ARGV[4])
end
redis.call('ZADD', KEYS[2], ARGV[8], ARGV[6] .. ':' .. ARGV[12] .. ':' .. ARGV[7])
redis.call('EXPIRE', KEYS[2], ARGV[9])
return 0
"""


class Refusal(enum.StrEnum):
    """Why a message wasn't admitted."""

    TOKEN_BUDGET = "token_budget"  # noqa: S105 (a reason, not a secret)
    # The budget isn't spent, but replies still streaming have reserved the rest of it, or as
    # many replies as may stream at once are streaming.
    BUDGET_IN_USE = "budget_in_use"
    CONVERSATION_RATE = "conversation_rate"
    IP_RATE = "ip_rate"
    # The Agent's own limit across all Conversations and addresses.
    AGENT_RATE = "agent_rate"
    MEMBER_RATE = "member_rate"
    ORGANISATION_RATE = "organisation_rate"


@dataclass(frozen=True)
class Limits:
    """An Agent's rate limits and Token Budget, from its Operational Settings."""

    public_id: str
    conversation_messages_per_minute: int
    ip_messages_per_minute: int
    daily_token_budget: int
    agent_messages_per_minute: int = AGENT_MESSAGES_PER_MINUTE
    replies_in_flight: int = REPLIES_IN_FLIGHT
    # So one client can't hold every place the Agent has.
    replies_in_flight_per_address: int = 1


@dataclass(frozen=True)
class PlaygroundLimits:
    """The Playground's limits, separate from Visitors': messages per minute per Member and per
    Organisation, and the tokens an Organisation's Playground replies may use per UTC date."""

    member_messages_per_minute: int = 20
    organisation_messages_per_minute: int = 120
    daily_token_budget: int = 2_000_000
    # Answers an Organisation's Members may have streaming at once: the day ends at most this
    # many answers over the Playground Token Budget, however much each costs.
    answers_in_flight: int = 4
    # So one Member can't hold every place their Organisation has.
    answers_in_flight_per_member: int = 2


@dataclass(frozen=True)
class Reservation:
    """The cost an admitted reply holds until ``record_usage`` settles it or ``release`` gives
    it back."""

    key: str
    member: str


def utc_date(moment: datetime) -> date:
    """The UTC date a moment falls on: the day whose Token Budget it uses."""
    return moment.astimezone(UTC).date()


def _budget_key(public_id: str, day: date) -> str:
    return f"{_BUDGET_PREFIX}{public_id}:{day.isoformat()}"


def _playground_budget_key(organisation_id: uuid.UUID, day: date) -> str:
    return f"{_PLAYGROUND_BUDGET_PREFIX}{organisation_id}:{day.isoformat()}"


class Admission:
    def __init__(self, redis: "Redis", clock: Clock) -> None:
        self._redis = redis
        self._clock = clock

    async def admit(self, agent: Limits, token: str, ip: str) -> Refusal | Reservation:
        """The reply's reservation when the message is admitted (and counted), else why it was
        refused."""
        # The token is hashed so Redis never holds a usable one, the address so a reservation
        # doesn't name it.
        conversation = hashlib.sha256(token.encode()).hexdigest()
        return await self._admit(
            _budget_key(agent.public_id, utc_date(self._clock.now())),
            f"{_RESERVED_PREFIX}{agent.public_id}",
            agent.daily_token_budget,
            (agent.replies_in_flight, agent.replies_in_flight_per_address),
            hashlib.sha256(ip.encode()).hexdigest()[:16],
            [
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
                (
                    Refusal.AGENT_RATE,
                    f"{_KEY_PREFIX}agent:{agent.public_id}",
                    agent.agent_messages_per_minute,
                ),
            ],
        )

    async def admit_playground(
        self, limits: PlaygroundLimits, organisation_id: uuid.UUID, member_id: uuid.UUID
    ) -> Refusal | Reservation:
        """A Playground message: the reply's reservation when admitted, else why it was
        refused."""
        return await self._admit(
            _playground_budget_key(organisation_id, utc_date(self._clock.now())),
            f"{_PLAYGROUND_RESERVED_PREFIX}{organisation_id}",
            limits.daily_token_budget,
            (limits.answers_in_flight, limits.answers_in_flight_per_member),
            str(member_id),
            [
                (
                    Refusal.MEMBER_RATE,
                    f"{_PLAYGROUND_RATE_PREFIX}member:{organisation_id}:{member_id}",
                    limits.member_messages_per_minute,
                ),
                (
                    Refusal.ORGANISATION_RATE,
                    f"{_PLAYGROUND_RATE_PREFIX}organisation:{organisation_id}",
                    limits.organisation_messages_per_minute,
                ),
            ],
        )

    async def _admit(
        self,
        budget_key: str,
        reserved_key: str,
        budget: int,
        in_flight: tuple[int, int],
        holder: str,
        windows: list[tuple[Refusal, str, int]],
    ) -> Refusal | Reservation:
        now = self._clock.now().timestamp()
        reservation = secrets.token_hex(8)
        found = int(
            await self._redis.eval(
                _ADMIT,
                2 + len(windows),
                budget_key,
                reserved_key,
                *(key for _, key, _ in windows),
                str(now),
                WINDOW_SECONDS,
                f"{now}:{secrets.token_hex(8)}",
                WINDOW_SECONDS + _EXPIRY_MARGIN_SECONDS,
                budget,
                reservation,
                RESERVED_TOKENS,
                str(now + LEASE_SECONDS),
                _RESERVATIONS_EXPIRY_SECONDS,
                *in_flight,
                holder,
                *(limit for _, _, limit in windows),
            )
        )
        if found == 0:
            return Reservation(reserved_key, f"{reservation}:{holder}:{RESERVED_TOKENS}")
        if found == -1:
            return Refusal.TOKEN_BUDGET
        if found == -2:
            return Refusal.BUDGET_IN_USE
        return windows[found - 1][0]

    async def tokens_used(self, public_id: str, day: date) -> int:
        """The tokens the Agent's Visitor replies used on that UTC date."""
        used = await self._redis.get(_budget_key(public_id, day))
        return 0 if used is None else int(used)

    async def record_usage(
        self, public_id: str, tokens: int, reservation: Reservation | None = None
    ) -> int:
        """Adds a reply's actual usage to today's counter (the date of the Clock now), settling
        its reservation; returns the day's usage so far. A caller that doesn't name the
        reservation settles the Agent's oldest one: every Visitor reservation is the same size,
        so which one goes makes no difference to the budget, and the reply's place in flight is
        given back either way."""
        key = _budget_key(public_id, utc_date(self._clock.now()))
        if reservation is None:
            return await self._record(key, tokens, f"{_RESERVED_PREFIX}{public_id}", None)
        return await self._record(key, tokens, reservation.key, reservation.member)

    async def record_playground_usage(
        self, organisation_id: uuid.UUID, tokens: int, reservation: Reservation
    ) -> int:
        """Adds a Playground reply's actual usage to the Organisation's counter for today,
        settling its reservation; returns the day's usage so far."""
        key = _playground_budget_key(organisation_id, utc_date(self._clock.now()))
        return await self._record(key, tokens, reservation.key, reservation.member)

    async def _record(self, key: str, tokens: int, reserved_key: str, member: str | None) -> int:
        """Adds the usage and settles the reservation ``member`` (None: the oldest one)."""
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incrby(key, tokens)
            pipe.expire(key, _BUDGET_EXPIRY_SECONDS)
            if member is None:
                pipe.zpopmin(reserved_key)
            else:
                pipe.zrem(reserved_key, member)
            total, *_ = await pipe.execute()
        return int(total)

    async def hold(self, reservation: Reservation, every: float = RENEW_SECONDS) -> None:
        """Renews the reservation's lease every ``every`` seconds while its response lasts (the
        caller cancels this when it ends), for at most ``LONGEST_REPLY_SECONDS``. A reservation
        already settled, released or lapsed isn't brought back."""
        started = self._clock.now().timestamp()
        while True:
            await asyncio.sleep(every)
            now = self._clock.now().timestamp()
            if now - started >= LONGEST_REPLY_SECONDS:
                return
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.zadd(reservation.key, {reservation.member: now + LEASE_SECONDS}, xx=True)
                pipe.expire(reservation.key, _RESERVATIONS_EXPIRY_SECONDS)
                await pipe.execute()

    async def release(self, reservation: Reservation) -> None:
        """Gives back a reservation no reply was recorded for."""
        await self._redis.zrem(reservation.key, reservation.member)


class HeldStream(StreamingResponse):
    """An answer's Server-Sent Events, holding its reservation (renewing its lease) for as long
    as the response is being sent, and giving it back however that ends: answered (a settled
    reservation is already gone, so giving it back changes nothing), failed, or the client gone
    away, even before the stream started (an async generator that never started runs no
    ``finally``). The release is shielded, so the cancellation that ends a disconnected
    response can't skip it."""

    def __init__(
        self, content: AsyncIterable[str], admission: Admission, reservation: Reservation
    ) -> None:
        super().__init__(
            content,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
        self._admission = admission
        self._reservation = reservation

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        holding = asyncio.create_task(self._admission.hold(self._reservation))
        try:
            await super().__call__(scope, receive, send)
        finally:
            holding.cancel()
            with anyio.CancelScope(shield=True):
                await self._admission.release(self._reservation)
