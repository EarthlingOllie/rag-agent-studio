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

# A key is split into lower-case words at separators and case changes ("wrappedDataKey" is
# wrapped/data/key), and whole words are matched, so "token_budget" and "max_tokens" keep
# their values while "session_token" does not.
_KEY_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
# A key holding any of these words is secret wherever the word sits: "password_hash".
_SECRET_ANYWHERE = frozenset(
    {
        "password",
        "passwd",
        "passphrase",
        "pwd",
        "secret",
        "secrets",
        "authorization",
        "authorisation",
        "cookie",
        "cookies",
    }
)
# A key ending in one of these words names the secret itself: "api_key", "wrapped_data_key",
# "refresh_token", "seed", "sentry_dsn". "key_id" or "token_budget" only describe one.
_SECRET_LAST_WORD = frozenset(
    {"key", "keys", "token", "seed", "dsn", "session", "credential", "credentials"}
)
# Pairs of final words that name a secret: "recovery_codes", "session_id".
_SECRET_LAST_PAIR = frozenset({("recovery", "codes"), ("recovery", "code"), ("session", "id")})


def _is_secret_like(key: str) -> bool:
    """Whether the value under ``key`` is never stored."""
    words = [word.lower() for word in _KEY_WORD.findall(key)]
    if not words:
        return False
    return (
        not _SECRET_ANYWHERE.isdisjoint(words)
        or words[-1] in _SECRET_LAST_WORD
        or tuple(words[-2:]) in _SECRET_LAST_PAIR
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
            str(key): REDACTED if _is_secret_like(str(key)) else redact(item)
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
    to the database's clock at the insert.
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
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.sequence.desc())
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
