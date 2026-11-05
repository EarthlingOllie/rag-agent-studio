"""Creating, listing, renaming, Archiving and restoring an Organisation's Projects.

Every function takes an ``OrganisationScope``, so a Project is only ever found inside the
Organisation the Member is working in: another Organisation's Project is "not found".

An archived Project is hidden from the main list and stops serving. ``active_project`` is the
one gate for everything that serves or changes a Project (renaming here; uploads and Agents in
later specs): it refuses an archived Project. Reading an archived Project still works, so its
page can offer restoring it.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.documents.models import Document
from app.projects.models import Project
from app.tenancy.repository import OrganisationScope


class ProjectNotFoundError(Exception):
    """No Project with that ID in the Organisation."""


class ProjectArchivedError(Exception):
    """The Project is archived, so it can't be changed or serve until it is restored."""


class ProjectNotArchivedError(Exception):
    """Only an archived Project can be restored."""


@dataclass(frozen=True)
class ProjectSummary:
    """A Project with the counts the Projects list shows."""

    project: Project
    document_count: int
    agent_count: int


async def _summaries(session: AsyncSession, projects: list[Project]) -> list[ProjectSummary]:
    # Agents arrive in ticket 04-01, which adds their count here. Until then there are none.
    counts: dict[uuid.UUID, int] = {}
    if projects:
        rows = await session.execute(
            select(Document.project_id, func.count())
            .where(Document.project_id.in_([project.id for project in projects]))
            .group_by(Document.project_id)
        )
        counts = {project_id: count for project_id, count in rows}
    return [
        ProjectSummary(project, document_count=counts.get(project.id, 0), agent_count=0)
        for project in projects
    ]


async def list_projects(
    session: AsyncSession, scope: OrganisationScope, *, archived: bool
) -> list[ProjectSummary]:
    """The Organisation's active Projects, or its archived ones, by name."""
    archived_at = Project.archived_at
    archived_filter = archived_at.is_not(None) if archived else archived_at.is_(None)
    projects = await session.scalars(
        select(Project)
        .where(Project.organisation_id == scope.organisation_id, archived_filter)
        .order_by(func.lower(Project.name), Project.created_at)
    )
    return await _summaries(session, list(projects))


async def summarise(session: AsyncSession, project: Project) -> ProjectSummary:
    (summary,) = await _summaries(session, [project])
    return summary


def _audit_fields(project: Project) -> dict[str, str]:
    return {"name": project.name, "description": project.description}


async def create_project(
    session: AsyncSession,
    scope: OrganisationScope,
    *,
    name: str,
    description: str,
    now: datetime,
) -> Project:
    """Creates an active Project and records ``project.created``."""
    project = Project(organisation_id=scope.organisation_id, name=name, description=description)
    session.add(project)
    await session.flush()
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action="project.created",
        target=audit.AuditTarget("project", project.id),
        after=_audit_fields(project),
        occurred_at=now,
    )
    await session.commit()
    await session.refresh(project)
    return project


async def get_project(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, *, lock: bool = False
) -> Project:
    """The Project, archived or not, if it belongs to the Organisation."""
    query = select(Project).where(
        Project.id == project_id, Project.organisation_id == scope.organisation_id
    )
    project = await session.scalar(query.with_for_update() if lock else query)
    if project is None:
        raise ProjectNotFoundError
    return project


async def active_project(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, *, lock: bool = False
) -> Project:
    """The Project, if it belongs to the Organisation and isn't archived."""
    project = await get_project(session, scope, project_id, lock=lock)
    if project.archived_at is not None:
        raise ProjectArchivedError
    return project


async def update_project(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    *,
    name: str | None,
    description: str | None,
) -> Project:
    """Renames the Project and/or replaces its description. Archived Projects are refused."""
    project = await active_project(session, scope, project_id, lock=True)
    if name is not None:
        project.name = name
    if description is not None:
        project.description = description
    await session.commit()
    return project


async def archive_project(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, *, now: datetime
) -> Project:
    """Archives the Project and records ``project.archived``."""
    project = await active_project(session, scope, project_id, lock=True)
    project.archived_at = now
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action="project.archived",
        target=audit.AuditTarget("project", project.id),
        before={"name": project.name, "archived": False},
        after={"name": project.name, "archived": True},
        occurred_at=now,
    )
    await session.commit()
    return project


async def restore_project(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, *, now: datetime
) -> Project:
    """Restores an archived Project to the main list and records ``project.restored``."""
    project = await get_project(session, scope, project_id, lock=True)
    if project.archived_at is None:
        raise ProjectNotArchivedError
    project.archived_at = None
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action="project.restored",
        target=audit.AuditTarget("project", project.id),
        before={"name": project.name, "archived": True},
        after={"name": project.name, "archived": False},
        occurred_at=now,
    )
    await session.commit()
    return project
