"""Writing Audit Events.

This is the ``record`` operation spec 01 describes, with the signature ticket 01-05 uses.
Ticket 01-05 adds redaction of secret-like fields and the Owner-only list endpoint.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent


@dataclass(frozen=True)
class AuditTarget:
    """What an Audit Event is about: a kind of thing and, when it has one, its ID."""

    type: str
    id: str | uuid.UUID | None = None


async def record(
    session: AsyncSession,
    *,
    organisation_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    action: str,
    target: AuditTarget,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> AuditEvent:
    """Adds an Audit Event to the session's transaction; the caller commits it with the change.

    ``action`` is a dotted name such as ``member.password_reset``. ``occurred_at`` defaults to
    the database's transaction time.
    """
    event = AuditEvent(
        organisation_id=organisation_id,
        actor_id=actor_id,
        action=action,
        target_type=target.type,
        target_id=None if target.id is None else str(target.id),
        before=None if before is None else dict(before),
        after=None if after is None else dict(after),
        # Left out when None, so the column's database default applies.
        **({} if occurred_at is None else {"occurred_at": occurred_at}),
    )
    session.add(event)
    await session.flush()
    return event
