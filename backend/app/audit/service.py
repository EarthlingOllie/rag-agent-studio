"""The audit module's one operation: ``record``."""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent


@dataclass(frozen=True)
class Target:
    type: str
    id: uuid.UUID | None


def record(
    session: AsyncSession,
    *,
    organisation_id: uuid.UUID,
    actor_member_id: uuid.UUID | None,
    action: str,
    target: Target,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Adds an Audit Event to the caller's transaction, so it commits with the change."""
    session.add(
        AuditEvent(
            organisation_id=organisation_id,
            actor_member_id=actor_member_id,
            action=action,
            target_type=target.type,
            target_id=target.id,
            before=before,
            after=after,
        )
    )
