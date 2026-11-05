"""Project routes: the Projects list, a Project, renaming and describing it (Editors), Archive
(Editors) and restore (Owners). Each takes the Organisation from its path through the policy
dependency, and finds the Project only inside that Organisation."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, StringConstraints

from app.auth.api import Db, ErrorResponse
from app.core.clock import Clock, get_clock
from app.projects import service
from app.projects.models import DESCRIPTION_MAX, INSTRUCTIONS_MAX, NAME_MAX, Project
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY, OwnerScope, Scope

router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["projects"])

PROJECT_ARCHIVED = "This Project is archived. An Owner can restore it."
PROJECT_NOT_ARCHIVED = "This Project isn't archived."

ClockDep = Annotated[Clock, Depends(get_clock)]

ProjectName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX)
]
ProjectDescription = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX)
]

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": NOT_FOUND}
}
_ARCHIVED: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": PROJECT_ARCHIVED}
}


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    created_at: datetime
    # Set while the Project is archived.
    archived_at: datetime | None
    document_count: int
    agent_count: int
    # The Embedding Model the Project's Documents are embedded with.
    embedding_model_id: str


class CreateProjectRequest(BaseModel):
    name: ProjectName
    description: ProjectDescription = ""


class UpdateProjectRequest(BaseModel):
    """Only the fields given change."""

    name: ProjectName | None = None
    description: ProjectDescription | None = None


def _out(summary: service.ProjectSummary) -> ProjectOut:
    project = summary.project
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        archived_at=project.archived_at,
        document_count=summary.document_count,
        agent_count=summary.agent_count,
        embedding_model_id=project.embedding_model_id,
    )


async def _respond(db: Db, project: Project) -> ProjectOut:
    return _out(await service.summarise(db, project))


@router.get("/projects", operation_id="listProjects", responses=_NOT_FOUND)
async def list_projects(
    scope: Scope,
    db: Db,
    archived: Annotated[bool, Query(description="List archived Projects instead.")] = False,
) -> list[ProjectOut]:
    """The Organisation's active Projects by name, or with ``archived=true`` its archived ones."""
    return [_out(s) for s in await service.list_projects(db, scope, archived=archived)]


@router.post(
    "/projects",
    status_code=status.HTTP_201_CREATED,
    operation_id="createProject",
    responses=_NOT_FOUND,
)
async def create_project(
    body: CreateProjectRequest, scope: Scope, db: Db, clock: ClockDep
) -> ProjectOut:
    """Creates a Project; records ``project.created``."""
    project = await service.create_project(
        db, scope, name=body.name, description=body.description, now=clock.now()
    )
    return await _respond(db, project)


@router.get("/projects/{project_id}", operation_id="getProject", responses=_NOT_FOUND)
async def get_project(project_id: uuid.UUID, scope: Scope, db: Db) -> ProjectOut:
    """The Project, archived or not."""
    try:
        project = await service.get_project(db, scope, project_id)
    except service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return await _respond(db, project)


@router.patch(
    "/projects/{project_id}",
    operation_id="updateProject",
    responses={**_NOT_FOUND, **_ARCHIVED},
)
async def update_project(
    project_id: uuid.UUID, body: UpdateProjectRequest, scope: Scope, db: Db
) -> ProjectOut:
    """Renames the Project or edits its description. An archived Project is refused."""
    try:
        project = await service.update_project(
            db, scope, project_id, name=body.name, description=body.description
        )
    except service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except service.ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    return await _respond(db, project)


@router.post(
    "/projects/{project_id}/archive",
    operation_id="archiveProject",
    responses={**_NOT_FOUND, **_ARCHIVED},
)
async def archive_project(
    project_id: uuid.UUID, scope: Scope, db: Db, clock: ClockDep
) -> ProjectOut:
    """Archives the Project: it leaves the main list and stops serving. Records
    ``project.archived``."""
    try:
        project = await service.archive_project(db, scope, project_id, now=clock.now())
    except service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except service.ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    return await _respond(db, project)


@router.post(
    "/projects/{project_id}/restore",
    operation_id="restoreProject",
    responses={
        403: {"model": ErrorResponse, "description": OWNERS_ONLY},
        **_NOT_FOUND,
        409: {"model": ErrorResponse, "description": PROJECT_NOT_ARCHIVED},
    },
)
async def restore_project(
    project_id: uuid.UUID, scope: OwnerScope, db: Db, clock: ClockDep
) -> ProjectOut:
    """Restores an archived Project to the main list (Owners only). Records
    ``project.restored``."""
    try:
        project = await service.restore_project(db, scope, project_id, now=clock.now())
    except service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except service.ProjectNotArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_NOT_ARCHIVED) from None
    return await _respond(db, project)


class ProjectInstructions(BaseModel):
    """The Project Instructions: markdown every Agent in the Project follows, kept exactly."""

    markdown: Annotated[str, StringConstraints(max_length=INSTRUCTIONS_MAX)]


@router.get(
    "/projects/{project_id}/instructions",
    operation_id="getProjectInstructions",
    responses=_NOT_FOUND,
)
async def get_project_instructions(
    project_id: uuid.UUID, scope: Scope, db: Db
) -> ProjectInstructions:
    """The Project Instructions, archived Project or not."""
    try:
        project = await service.get_project(db, scope, project_id)
    except service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return ProjectInstructions(markdown=project.instructions)


@router.put(
    "/projects/{project_id}/instructions",
    operation_id="saveProjectInstructions",
    responses={**_NOT_FOUND, **_ARCHIVED},
)
async def save_project_instructions(
    project_id: uuid.UUID, body: ProjectInstructions, scope: Scope, db: Db, clock: ClockDep
) -> ProjectInstructions:
    """Replaces the Project Instructions; records ``project.instructions_updated`` when they
    change. An archived Project is refused."""
    try:
        project = await service.save_instructions(
            db, scope, project_id, body.markdown, now=clock.now()
        )
    except service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except service.ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    return ProjectInstructions(markdown=project.instructions)
