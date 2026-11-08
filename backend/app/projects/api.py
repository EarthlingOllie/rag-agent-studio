"""Project routes: the Projects list, a Project, renaming and describing it (Editors), Archive
(Editors), restore (Owners) and permanent deletion (Owners). Each takes the Organisation from
its path through the policy dependency, and finds the Project only inside that Organisation."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints

from app.auth.api import Db, ErrorResponse
from app.core.clock import Clock, get_clock
from app.projects import service
from app.projects.models import (
    DESCRIPTION_MAX,
    INSTRUCTIONS_MAX,
    NAME_MAX,
    FlaggedChunkMode,
    Project,
)
from app.projects.tasks import enqueue_deletion
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY, OwnerScope, Scope

router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["projects"])

PROJECT_ARCHIVED = "This Project is archived. An Owner can restore it."
PROJECT_NOT_ARCHIVED = "This Project isn't archived."
ARCHIVE_BEFORE_DELETING = "Only an archived Project can be deleted. Archive it first."
NAME_MISMATCH = "Type the Project's name exactly to delete it."

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
    # Whether ingestion runs OCR on the Project's files, so scanned PDFs become readable.
    ocr_enabled: bool
    # The Provider Credential a provider Embedding Model is called through; none for the
    # built-in local model.
    embedding_credential_id: uuid.UUID | None
    # What retrieval does with Chunks the ingestion Guardrail scan flags: ``mark`` (retrieved,
    # marked in the Document viewer) or ``exclude`` (never retrieved; the Trace lists them).
    flagged_chunk_mode: FlaggedChunkMode


class CreateProjectRequest(BaseModel):
    name: ProjectName
    description: ProjectDescription = ""


class UpdateProjectRequest(BaseModel):
    """Only the fields given change."""

    name: ProjectName | None = None
    description: ProjectDescription | None = None
    # Turns OCR on or off for Documents processed from now on. Retry reprocesses an existing
    # Document with the new setting.
    ocr_enabled: bool | None = None
    # Marks or excludes flagged Chunks; retrieval follows the new setting at once.
    flagged_chunk_mode: FlaggedChunkMode | None = None


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
        ocr_enabled=project.ocr_enabled,
        embedding_credential_id=project.embedding_credential_id,
        flagged_chunk_mode=FlaggedChunkMode(project.flagged_chunk_mode),
    )


async def respond(db: Db, project: Project) -> ProjectOut:
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
    return await respond(db, project)


@router.get("/projects/{project_id}", operation_id="getProject", responses=_NOT_FOUND)
async def get_project(project_id: uuid.UUID, scope: Scope, db: Db) -> ProjectOut:
    """The Project, archived or not."""
    try:
        project = await service.get_project(db, scope, project_id)
    except service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return await respond(db, project)


@router.patch(
    "/projects/{project_id}",
    operation_id="updateProject",
    responses={**_NOT_FOUND, **_ARCHIVED},
)
async def update_project(
    project_id: uuid.UUID, body: UpdateProjectRequest, scope: Scope, db: Db
) -> ProjectOut:
    """Renames the Project, edits its description, turns OCR on or off or sets whether Chunks
    the ingestion Guardrail scan flags are marked or excluded from retrieval. An archived
    Project is refused."""
    try:
        project = await service.update_project(
            db,
            scope,
            project_id,
            name=body.name,
            description=body.description,
            ocr_enabled=body.ocr_enabled,
            flagged_chunk_mode=body.flagged_chunk_mode,
        )
    except service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except service.ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    return await respond(db, project)


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
    return await respond(db, project)


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
    return await respond(db, project)


class DeleteProjectRequest(BaseModel):
    # The Project's name, typed by the Owner to confirm; it must match exactly.
    confirm_name: str


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=Response,
    operation_id="deleteProject",
    responses={
        400: {"model": ErrorResponse, "description": NAME_MISMATCH},
        403: {"model": ErrorResponse, "description": OWNERS_ONLY},
        **_NOT_FOUND,
        409: {"model": ErrorResponse, "description": ARCHIVE_BEFORE_DELETING},
    },
)
async def delete_project(
    project_id: uuid.UUID, body: DeleteProjectRequest, scope: OwnerScope, db: Db, clock: ClockDep
) -> Response:
    """Permanently deletes an archived Project (Owners only), once ``confirm_name`` is its
    name. A Celery task removes the Project and everything in it (Documents, Chunks, stored
    files, Agents and Conversations) and records ``project.deleted``. This can't be undone."""
    try:
        await service.check_deletion(db, scope, project_id, confirm_name=body.confirm_name)
    except service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except service.ProjectNotArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, ARCHIVE_BEFORE_DELETING) from None
    except service.ProjectNameMismatchError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NAME_MISMATCH) from None
    # End the read transaction before the task (eager in tests) locks the row.
    await db.rollback()
    await enqueue_deletion(project_id, actor_id=scope.member_id, requested_at=clock.now())
    return Response(status_code=status.HTTP_202_ACCEPTED)


class ProjectInstructions(BaseModel):
    """The Project Instructions: markdown every Agent in the Project follows, kept exactly."""

    markdown: Annotated[str, StringConstraints(max_length=INSTRUCTIONS_MAX)]


class ProjectInstructionsOut(BaseModel):
    markdown: str
    # Moves on whenever the Draft's text changes. Send it as ``base_revision`` with a save so
    # that a Draft someone has changed since is not overwritten.
    revision: int


class InstructionsConflictOut(BaseModel):
    detail: str
    # The latest Draft, when the save was refused because the Draft had moved on from the
    # revision it was made on.
    latest: ProjectInstructionsOut | None = None


STALE_INSTRUCTIONS = (
    "Someone else saved these Instructions after you opened them. Load their changes, or save "
    "yours over them."
)


def _instructions(project: Project) -> ProjectInstructionsOut:
    return ProjectInstructionsOut(
        markdown=project.instructions, revision=project.instructions_revision
    )


@router.get(
    "/projects/{project_id}/instructions",
    operation_id="getProjectInstructions",
    responses=_NOT_FOUND,
)
async def get_project_instructions(
    project_id: uuid.UUID, scope: Scope, db: Db
) -> ProjectInstructionsOut:
    """The Project Instructions, archived Project or not."""
    try:
        project = await service.get_project(db, scope, project_id)
    except service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return _instructions(project)


@router.put(
    "/projects/{project_id}/instructions",
    operation_id="saveProjectInstructions",
    response_model=ProjectInstructionsOut,
    responses={
        **_NOT_FOUND,
        409: {
            "model": InstructionsConflictOut,
            "description": f"{STALE_INSTRUCTIONS} Or: {PROJECT_ARCHIVED}",
        },
    },
)
async def save_project_instructions(
    project_id: uuid.UUID,
    body: ProjectInstructions,
    scope: Scope,
    db: Db,
    clock: ClockDep,
    base_revision: Annotated[
        int | None,
        Query(
            description=(
                "The Draft revision the save was made on. When the Draft has moved on since, "
                "the save is refused with 409 and the latest Draft. Left out, it is replaced."
            )
        ),
    ] = None,
) -> ProjectInstructionsOut | JSONResponse:
    """Replaces the Project Instructions; records ``project.instructions_updated`` when they
    change. An archived Project is refused. With ``base_revision``, a Draft someone has changed
    since is refused with 409 and the latest Draft."""
    try:
        project = await service.save_instructions(
            db, scope, project_id, body.markdown, base_revision=base_revision, now=clock.now()
        )
    except service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except service.ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    except service.StaleInstructionsError as error:
        conflict = InstructionsConflictOut(
            detail=STALE_INSTRUCTIONS, latest=_instructions(error.latest)
        )
        return JSONResponse(conflict.model_dump(mode="json"), status.HTTP_409_CONFLICT)
    return _instructions(project)
