"""Writing and reading Audit Events."""

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.tenancy.models import Member
from app.tenancy.repository import OrganisationScope

REDACTED = "[Redacted]"

# Keys whose values are never stored, at any depth of the before/after values.
SECRET_LIKE_KEY = re.compile(
    r"password|passwd|passphrase|secret|token|credential|private[._ -]?key|api[._ -]?key"
    r"|access[._ -]?key|authori[sz]ation|cookie|session|recovery[._ -]?codes?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AuditTarget:
    """What an Audit Event is about: a kind of thing and, when it has one, its ID."""

    type: str
    id: str | uuid.UUID | None = None


def redact(value: Any) -> Any:
    """``value`` with every secret-like key's value replaced, through nested dicts and lists."""
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if SECRET_LIKE_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(item) for item in value]
    return value


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

    ``action`` is a dotted name such as ``organisation.created``. Secret-like fields in
    ``before`` and ``after`` are redacted before anything is stored. ``occurred_at`` defaults
    to the database's transaction time.
    """
    event = AuditEvent(
        organisation_id=organisation_id,
        actor_id=actor_id,
        action=action,
        target_type=target.type,
        target_id=None if target.id is None else str(target.id),
        before=None if before is None else redact(before),
        after=None if after is None else redact(after),
    )
    if occurred_at is not None:
        event.occurred_at = occurred_at
    session.add(event)
    await session.flush()
    return event


@dataclass(frozen=True)
class AuditFilter:
    actor_id: uuid.UUID | None = None
    action: str | None = None
    start: datetime | None = None
    end: datetime | None = None


@dataclass(frozen=True)
class AuditEventRow:
    event: AuditEvent
    actor: Member | None


@dataclass(frozen=True)
class AuditPage:
    rows: list[AuditEventRow]
    total: int


def _filtered(scope: OrganisationScope, where: AuditFilter) -> Select[AuditEvent]:
    query = select(AuditEvent).where(AuditEvent.organisation_id == scope.organisation_id)
    if where.actor_id is not None:
        query = query.where(AuditEvent.actor_id == where.actor_id)
    if where.action is not None:
        query = query.where(AuditEvent.action == where.action)
    if where.start is not None:
        query = query.where(AuditEvent.occurred_at >= where.start)
    if where.end is not None:
        query = query.where(AuditEvent.occurred_at < where.end)
    return query


async def list_events(
    session: AsyncSession, scope: OrganisationScope, where: AuditFilter, *, page: int, size: int
) -> AuditPage:
    """One page of the Organisation's Audit Events matching ``where``, newest first."""
    query = _filtered(scope, where)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.execute(
        query.add_columns(Member)
        .outerjoin(Member, Member.id == AuditEvent.actor_id)
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return AuditPage(rows=[AuditEventRow(event, actor) for event, actor in rows], total=total or 0)


@dataclass(frozen=True)
class AuditFacets:
    """The values the Organisation's Audit Events can be filtered by."""

    actors: list[Member]
    actions: list[str]


async def list_facets(session: AsyncSession, scope: OrganisationScope) -> AuditFacets:
    in_organisation = AuditEvent.organisation_id == scope.organisation_id
    actors = await session.scalars(
        select(Member)
        .where(Member.id.in_(select(AuditEvent.actor_id).where(in_organisation)))
        .order_by(Member.name, Member.email)
    )
    actions = await session.scalars(
        select(AuditEvent.action).where(in_organisation).distinct().order_by(AuditEvent.action)
    )
    return AuditFacets(actors=list(actors), actions=list(actions))
