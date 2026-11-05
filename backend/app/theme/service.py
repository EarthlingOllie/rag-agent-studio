"""Reading and saving the Organisation's Theme.

An Organisation that has never saved a Theme has the default one; its row is written on the
first save that changes something. Each change records ``theme.updated`` with only what
changed. Saving locks the Organisation's row first, so concurrent saves apply one after the
other and each one's Audit Event describes the Theme it replaced.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.tenancy.models import Organisation
from app.tenancy.repository import OrganisationScope
from app.theme.models import Theme
from app.theme.schema import DEFAULT_THEME, ThemeSettings


@dataclass(frozen=True)
class SavedTheme:
    settings: ThemeSettings
    # None while the Organisation still has the default Theme.
    updated_at: datetime | None


def _settings(row: Theme) -> ThemeSettings:
    return ThemeSettings.model_validate(
        {
            "colours": row.colours,
            "radius": row.radius,
            "font": row.font,
            "mode": row.mode,
            "launcher_type": row.launcher_type,
            "launcher_position": row.launcher_position,
        }
    )


async def _row(session: AsyncSession, scope: OrganisationScope) -> Theme | None:
    return await session.scalar(select(Theme).where(Theme.organisation_id == scope.organisation_id))


async def read_theme(session: AsyncSession, scope: OrganisationScope) -> SavedTheme:
    """The Organisation's Theme, or the default if it never saved one."""
    row = await _row(session, scope)
    if row is None:
        return SavedTheme(DEFAULT_THEME, None)
    return SavedTheme(_settings(row), row.updated_at)


def _changes(
    before: dict[str, Any], after: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The parts of ``before`` and ``after`` that differ, keeping nested dicts' shape."""
    old: dict[str, Any] = {}
    new: dict[str, Any] = {}
    for key, value in after.items():
        previous = before[key]
        if value == previous:
            continue
        if isinstance(value, dict):
            old[key], new[key] = _changes(previous, value)
        else:
            old[key], new[key] = previous, value
    return old, new


async def save_theme(
    session: AsyncSession, scope: OrganisationScope, settings: ThemeSettings, *, now: datetime
) -> SavedTheme:
    """Replaces the Theme and records ``theme.updated``; saving the same Theme is a no-op."""
    await session.execute(
        select(Organisation.id).where(Organisation.id == scope.organisation_id).with_for_update()
    )
    row = await _row(session, scope)
    current = DEFAULT_THEME if row is None else _settings(row)
    before, after = _changes(current.model_dump(mode="json"), settings.model_dump(mode="json"))
    if not after:
        await session.rollback()
        return SavedTheme(current, None if row is None else row.updated_at)
    if row is None:
        row = Theme(id=uuid.uuid4(), organisation_id=scope.organisation_id)
        session.add(row)
    values = settings.model_dump(mode="json")
    row.colours = values["colours"]
    row.radius = values["radius"]
    row.font = values["font"]
    row.mode = values["mode"]
    row.launcher_type = values["launcher_type"]
    row.launcher_position = values["launcher_position"]
    row.updated_at = now
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action="theme.updated",
        target=audit.AuditTarget("theme", row.id),
        before=before,
        after=after,
        occurred_at=now,
    )
    await session.commit()
    return SavedTheme(settings, now)
