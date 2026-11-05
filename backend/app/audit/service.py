"""The audit module: one ``record`` operation, and reading back an Organisation's events.

Events are only ever added. Ticket 01-05 adds redaction, the Owner-only list endpoint and
the Audit tab on top of this table.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.tenancy.repository import OrganisationScope


def record(
    session: AsyncSession,
    *,
    organisation_id: uuid.UUID,
    actor_member_id: uuid.UUID | None,
    action: str,
    target_type: str,
    target_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    at: datetime,
) -> None:
    """Adds an Audit Event to the session's transaction."""
    session.add(
        AuditEvent(
            organisation_id=organisation_id,
            actor_member_id=actor_member_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before=before,
            after=after,
            occurred_at=at,
        )
    )


async def list_events(session: AsyncSession, scope: OrganisationScope) -> list[AuditEvent]:
    """The Organisation's Audit Events, oldest first."""
    rows = await session.scalars(
        select(AuditEvent)
        .where(AuditEvent.organisation_id == scope.organisation_id)
        .order_by(AuditEvent.occurred_at, AuditEvent.created_at)
    )
    return list(rows)
