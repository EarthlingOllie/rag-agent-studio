"""The Organisation switcher context: which of their Organisations a Member last chose.

The choice is a preference, not a permission. It decides which Organisation the Studio opens
(``/api/auth/me`` reports it as ``active_organisation_id``); every Organisation-scoped route
still takes the Organisation from its path and checks the membership there.

It is kept in Redis, one key per Member with no expiry, so it outlives sessions and sign-ins.
Losing it is harmless: the Member's first Organisation is active again.
"""

import uuid
from collections.abc import Sequence
from typing import cast

from redis.asyncio import Redis

_KEY_PREFIX = "active-organisation:"


def _key(member_id: uuid.UUID) -> str:
    return f"{_KEY_PREFIX}{member_id}"


class ActiveOrganisations:
    def __init__(self, redis: "Redis") -> None:
        self._redis = redis

    async def remember(self, member_id: uuid.UUID, organisation_id: uuid.UUID) -> None:
        await self._redis.set(_key(member_id), str(organisation_id))

    async def active(
        self, member_id: uuid.UUID, memberships: Sequence[uuid.UUID]
    ) -> uuid.UUID | None:
        """The remembered Organisation if the Member still belongs to it, else their first."""
        value = cast(bytes | None, await self._redis.get(_key(member_id)))
        remembered = None if value is None else uuid.UUID(value.decode())
        if remembered in memberships:
            return remembered
        return next(iter(memberships), None)
