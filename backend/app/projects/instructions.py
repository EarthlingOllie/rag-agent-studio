"""Project Instructions Versions: publishing the Draft, the Version history and reverting.

The Project Instructions have one editable Draft (``Project.instructions``), an append-only
list of immutable, numbered Versions, and a Current Version pointer on the Project.

- **Publish** freezes the Draft into the next Version (1, 2, 3… per Project, allocated under the
  Project's row lock, so concurrent publishes never share a number) and makes it the Current
  Version. The Version remembers the Version that was Current when it was published.
- **Revert** moves the Current Version back to the Version that was Current when the present
  one was published. Reverting again keeps walking back that chain rather than toggling, so
  publish v1, v2, v3 then revert, revert lands on v1; and after v1, v2, revert (v1), publish v3,
  a revert returns to v1, skipping the reverted v2. With nothing before the Current Version,
  revert is refused. The Draft is never touched by a revert.

Publish and revert are recorded as Audit Events. Every operation goes through
``active_project``, so another Organisation's Project is "not found" and an archived one is
read-only.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.projects.models import InstructionsVersion, Project
from app.projects.service import active_project, get_project
from app.tenancy.models import Member
from app.tenancy.repository import OrganisationScope


class NothingToPublishError(Exception):
    """The Draft is the same as the Current Version (or empty, before the first publish)."""


class InstructionsVersionNotFoundError(Exception):
    """No Instructions Version with that ID in the Project."""


class NothingToRevertError(Exception):
    """No Version was Current before the Current Version."""


@dataclass(frozen=True)
class Author:
    id: uuid.UUID
    name: str


@dataclass(frozen=True)
class VersionView:
    """A Version with its author, as the history shows it. The v1 the migration made from the
    Instructions already there has no author."""

    version: InstructionsVersion
    author: Author | None


@dataclass(frozen=True)
class InstructionsHistory:
    current_version_id: uuid.UUID | None
    # Newest first.
    versions: list[VersionView]


async def _version(
    session: AsyncSession, version_id: uuid.UUID | None
) -> InstructionsVersion | None:
    if version_id is None:
        return None
    return await session.get(InstructionsVersion, version_id)


def _summary(version: InstructionsVersion | None) -> dict[str, object] | None:
    if version is None:
        return None
    return {"version_id": str(version.id), "number": version.number}


async def _view(session: AsyncSession, version: InstructionsVersion) -> VersionView:
    if version.author_id is None:
        return VersionView(version, None)
    name = await session.scalar(select(Member.name).where(Member.id == version.author_id))
    return VersionView(version, Author(version.author_id, name or ""))


async def project_version(
    session: AsyncSession, project: Project, version_id: uuid.UUID
) -> InstructionsVersion:
    """One of the Project's Instructions Versions, Current or not."""
    version = await session.scalar(
        select(InstructionsVersion).where(
            InstructionsVersion.id == version_id, InstructionsVersion.project_id == project.id
        )
    )
    if version is None:
        raise InstructionsVersionNotFoundError
    return version


async def version_numbers(
    session: AsyncSession, version_ids: set[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """The number of each of these Instructions Versions."""
    if not version_ids:
        return {}
    rows = await session.execute(
        select(InstructionsVersion.id, InstructionsVersion.number).where(
            InstructionsVersion.id.in_(version_ids)
        )
    )
    return {version_id: number for version_id, number in rows}


async def history(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID
) -> InstructionsHistory:
    """The Project's Instructions Versions, newest first, and which is Current. Archived
    Projects can still be read."""
    project = await get_project(session, scope, project_id)
    rows = await session.execute(
        select(InstructionsVersion, Member.id, Member.name)
        .outerjoin(Member, Member.id == InstructionsVersion.author_id)
        .where(InstructionsVersion.project_id == project.id)
        .order_by(InstructionsVersion.number.desc())
    )
    return InstructionsHistory(
        project.current_instructions_version_id,
        [
            VersionView(version, None if author_id is None else Author(author_id, name))
            for version, author_id, name in rows
        ],
    )


async def publish(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    note: str,
    *,
    now: datetime,
) -> VersionView:
    """Freezes the Draft into the next Version and makes it the Current Version."""
    project = await active_project(session, scope, project_id, lock=True)
    current = await _version(session, project.current_instructions_version_id)
    if project.instructions == (current.markdown if current else ""):
        raise NothingToPublishError
    latest = await session.scalar(
        select(func.max(InstructionsVersion.number)).where(
            InstructionsVersion.project_id == project.id
        )
    )
    version = InstructionsVersion(
        organisation_id=project.organisation_id,
        project_id=project.id,
        number=(latest or 0) + 1,
        markdown=project.instructions,
        note=note,
        author_id=scope.member_id,
        previous_version_id=current.id if current else None,
        created_at=now,
    )
    session.add(version)
    await session.flush()
    await _move(session, scope, project, current, version, "published", now)
    return await _view(session, version)


@dataclass(frozen=True)
class Reverted:
    """The Version that is Current again, and the one it replaced."""

    view: VersionView
    reverted_from: InstructionsVersion


async def revert(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, *, now: datetime
) -> Reverted:
    """Moves the Current Version back to the one that was Current before it."""
    project = await active_project(session, scope, project_id, lock=True)
    current = await _version(session, project.current_instructions_version_id)
    target = await _version(session, current.previous_version_id if current else None)
    if current is None or target is None:
        raise NothingToRevertError
    await _move(session, scope, project, current, target, "reverted", now)
    return Reverted(await _view(session, target), current)


async def _move(
    session: AsyncSession,
    scope: OrganisationScope,
    project: Project,
    current: InstructionsVersion | None,
    target: InstructionsVersion,
    action: str,
    now: datetime,
) -> None:
    project.current_instructions_version_id = target.id
    after = _summary(target)
    if action == "published":
        after = {**(after or {}), "note": target.note}
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action=f"project.instructions_{action}",
        target=audit.AuditTarget("project", project.id),
        before={"current_version": _summary(current)},
        after={"current_version": after},
        occurred_at=now,
    )
    await session.commit()
