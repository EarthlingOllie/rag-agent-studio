"""Reading and saving the Organisation's Theme, and setting its logo and default avatar.

An Organisation that has never saved a Theme has the default one; its row is written on the
first save that changes something (or the first image). Each change records ``theme.updated``
with only what changed. Every change locks the Organisation's row first, so concurrent changes
apply one after the other and each one's Audit Event describes the Theme it replaced.
"""

import enum
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


class ThemeImageKind(enum.StrEnum):
    # Shown in the widget's header.
    LOGO = "logo"
    # The default Agent avatar, shown beside the Agent's name and Messages.
    AVATAR = "avatar"


@dataclass(frozen=True)
class StoredImage:
    object_key: str
    content_type: str
    size_bytes: int
    # SHA-256 of the image, hex.
    content_hash: str
    uploaded_at: datetime

    def audited(self) -> dict[str, Any]:
        """What an Audit Event records about the image (not where it is stored)."""
        return {
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "content_hash": self.content_hash,
        }

    def stored(self) -> dict[str, Any]:
        return self.audited() | {
            "object_key": self.object_key,
            "uploaded_at": self.uploaded_at.isoformat(),
        }

    @classmethod
    def from_stored(cls, value: dict[str, Any]) -> "StoredImage":
        return cls(
            object_key=value["object_key"],
            content_type=value["content_type"],
            size_bytes=value["size_bytes"],
            content_hash=value["content_hash"],
            uploaded_at=datetime.fromisoformat(value["uploaded_at"]),
        )


@dataclass(frozen=True)
class SavedTheme:
    settings: ThemeSettings
    # None while the Organisation still has the default Theme.
    updated_at: datetime | None
    images: dict[ThemeImageKind, StoredImage | None]


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


def _image(row: Theme, kind: ThemeImageKind) -> StoredImage | None:
    value: dict[str, Any] | None = getattr(row, kind.value)
    return None if value is None else StoredImage.from_stored(value)


def _saved(row: Theme | None) -> SavedTheme:
    if row is None:
        return SavedTheme(DEFAULT_THEME, None, dict.fromkeys(ThemeImageKind))
    images = {kind: _image(row, kind) for kind in ThemeImageKind}
    return SavedTheme(_settings(row), row.updated_at, images)


async def _row(session: AsyncSession, scope: OrganisationScope) -> Theme | None:
    return await session.scalar(select(Theme).where(Theme.organisation_id == scope.organisation_id))


async def _locked_row(session: AsyncSession, scope: OrganisationScope) -> Theme | None:
    """The Theme's row, after locking the Organisation's row so changes apply one at a time."""
    await session.execute(
        select(Organisation.id).where(Organisation.id == scope.organisation_id).with_for_update()
    )
    return await _row(session, scope)


def _write_settings(row: Theme, settings: ThemeSettings) -> None:
    values = settings.model_dump(mode="json")
    row.colours = values["colours"]
    row.radius = values["radius"]
    row.font = values["font"]
    row.mode = values["mode"]
    row.launcher_type = values["launcher_type"]
    row.launcher_position = values["launcher_position"]


def _new_row(session: AsyncSession, scope: OrganisationScope) -> Theme:
    row = Theme(id=uuid.uuid4(), organisation_id=scope.organisation_id, logo=None, avatar=None)
    _write_settings(row, DEFAULT_THEME)
    session.add(row)
    return row


async def read_theme(session: AsyncSession, scope: OrganisationScope) -> SavedTheme:
    """The Organisation's Theme, or the default if it never saved one."""
    return _saved(await _row(session, scope))


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


async def _record(
    session: AsyncSession,
    scope: OrganisationScope,
    row: Theme,
    before: dict[str, Any],
    after: dict[str, Any],
    now: datetime,
) -> None:
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


async def save_theme(
    session: AsyncSession, scope: OrganisationScope, settings: ThemeSettings, *, now: datetime
) -> SavedTheme:
    """Replaces the Theme's settings (not its images) and records ``theme.updated``; saving the
    same Theme is a no-op."""
    row = await _locked_row(session, scope)
    current = DEFAULT_THEME if row is None else _settings(row)
    before, after = _changes(current.model_dump(mode="json"), settings.model_dump(mode="json"))
    if not after:
        await session.rollback()
        return _saved(row)
    if row is None:
        row = _new_row(session, scope)
    _write_settings(row, settings)
    row.updated_at = now
    await _record(session, scope, row, before, after, now)
    await session.commit()
    return _saved(row)


@dataclass(frozen=True)
class ImageChange:
    theme: SavedTheme
    # The image it replaced or removed, whose file the caller deletes after the commit.
    replaced: StoredImage | None


async def set_image(
    session: AsyncSession,
    scope: OrganisationScope,
    kind: ThemeImageKind,
    image: StoredImage | None,
    *,
    now: datetime,
) -> ImageChange:
    """Sets (or, with None, removes) one of the Theme's images and records ``theme.updated``.
    Removing an image there is none of is a no-op."""
    row = await _locked_row(session, scope)
    previous = None if row is None else _image(row, kind)
    if previous is None and image is None:
        await session.rollback()
        return ImageChange(_saved(row), None)
    if row is None:
        row = _new_row(session, scope)
    setattr(row, kind.value, None if image is None else image.stored())
    row.updated_at = now
    before = {kind.value: None if previous is None else previous.audited()}
    after = {kind.value: None if image is None else image.audited()}
    await _record(session, scope, row, before, after, now)
    await session.commit()
    return ImageChange(_saved(row), previous)
