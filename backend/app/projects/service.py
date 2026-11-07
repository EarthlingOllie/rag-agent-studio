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

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app import audit
from app.agents.models import Agent
from app.documents.models import Document
from app.projects.models import FlaggedChunkMode, Project
from app.tenancy.repository import OrganisationScope


class ProjectNotFoundError(Exception):
    """No Project with that ID in the Organisation."""


class ProjectArchivedError(Exception):
    """The Project is archived, so it can't be changed or serve until it is restored."""


class ProjectNotArchivedError(Exception):
    """Only an archived Project can be restored or permanently deleted."""


class StaleInstructionsError(Exception):
    """The Instructions Draft has moved on since the revision the save was made on."""

    def __init__(self, latest: Project) -> None:
        self.latest = latest


class ProjectNameMismatchError(Exception):
    """The name typed to confirm a permanent deletion isn't the Project's name."""


@dataclass(frozen=True)
class ProjectSummary:
    """A Project with the counts the Projects list shows."""

    project: Project
    document_count: int
    agent_count: int


async def _summaries(session: AsyncSession, projects: list[Project]) -> list[ProjectSummary]:
    ids = [project.id for project in projects]
    documents: dict[uuid.UUID, int] = {}
    agents: dict[uuid.UUID, int] = {}
    if ids:
        documents = await _counts(session, Document.project_id, ids)
        agents = await _counts(session, Agent.project_id, ids)
    return [
        ProjectSummary(
            project,
            document_count=documents.get(project.id, 0),
            agent_count=agents.get(project.id, 0),
        )
        for project in projects
    ]


async def _counts(
    session: AsyncSession, column: InstrumentedAttribute[uuid.UUID], ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    rows = await session.execute(
        select(column, func.count()).where(column.in_(ids)).group_by(column)
    )
    return {project_id: count for project_id, count in rows}


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
    ocr_enabled: bool | None = None,
    flagged_chunk_mode: FlaggedChunkMode | None = None,
) -> Project:
    """Renames the Project, replaces its description, turns OCR on or off and/or sets its
    Flagged Chunk mode. Archived Projects are refused."""
    project = await active_project(session, scope, project_id, lock=True)
    if name is not None:
        project.name = name
    if description is not None:
        project.description = description
    if ocr_enabled is not None:
        project.ocr_enabled = ocr_enabled
    if flagged_chunk_mode is not None:
        project.flagged_chunk_mode = flagged_chunk_mode
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


async def save_instructions(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    markdown: str,
    *,
    base_revision: int | None = None,
    now: datetime,
) -> Project:
    """Replaces the Project Instructions and records ``project.instructions_updated`` when
    the text changed, moving the Draft to its next revision. Archived Projects are refused.
    With ``base_revision``, a Draft that has moved on from it is refused with
    ``StaleInstructionsError``, so nobody silently overwrites a colleague's edits."""
    project = await active_project(session, scope, project_id, lock=True)
    if base_revision is not None and base_revision != project.instructions_revision:
        raise StaleInstructionsError(project)
    if project.instructions != markdown:
        project.instructions_revision += 1
        await audit.record(
            session,
            organisation_id=scope.organisation_id,
            actor_id=scope.member_id,
            action="project.instructions_updated",
            target=audit.AuditTarget("project", project.id),
            before={"instructions": project.instructions},
            after={"instructions": markdown},
            occurred_at=now,
        )
        project.instructions = markdown
    await session.commit()
    return project


def storage_prefix(organisation_id: uuid.UUID, project_id: uuid.UUID) -> str:
    """Where every object stored for the Project lives: its Documents' originals, converted
    markdown and staged editions, and uploads never confirmed."""
    return f"organisations/{organisation_id}/projects/{project_id}/"


async def check_deletion(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, *, confirm_name: str
) -> None:
    """Refuses a permanent deletion unless the Project is archived and ``confirm_name`` is its
    name, exactly. Owners only; the route checks the role."""
    project = await get_project(session, scope, project_id)
    if project.archived_at is None:
        raise ProjectNotArchivedError
    if confirm_name != project.name:
        raise ProjectNameMismatchError


async def delete_project(
    session: AsyncSession, project_id: uuid.UUID, *, actor_id: uuid.UUID, requested_at: datetime
) -> str | None:
    """The deletion cascade's database step: deletes the Project and, through the foreign keys'
    ``ON DELETE CASCADE``, everything in it (Documents and their staged editions, Chunks, Tags,
    Agents, their Conversations and Messages), and records ``project.deleted``, in one
    transaction. Returns the storage prefix whose objects the caller deletes next.

    Does nothing, returning None, if the Project is gone already or was restored after the
    deletion was asked for: only an archived Project is ever deleted."""
    project = await session.scalar(
        select(Project).where(Project.id == project_id).with_for_update()
    )
    if project is None or project.archived_at is None:
        return None
    (summary,) = await _summaries(session, [project])
    await audit.record(
        session,
        organisation_id=project.organisation_id,
        actor_id=actor_id,
        action="project.deleted",
        target=audit.AuditTarget("project", project.id),
        before={
            **_audit_fields(project),
            "document_count": summary.document_count,
            "agent_count": summary.agent_count,
        },
        occurred_at=requested_at,
    )
    await session.execute(delete(Project).where(Project.id == project.id))
    await session.commit()
    return storage_prefix(project.organisation_id, project.id)
