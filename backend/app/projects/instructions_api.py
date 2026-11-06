"""Project Instructions Version routes: the Version history, publishing the Draft and reverting
the Current Version. Editors and Owners may use them; every publish and revert is audited.

Versions are immutable, so there is no route that changes or deletes one."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, StringConstraints

from app.auth.api import Db, ErrorResponse
from app.projects import instructions, service
from app.projects.api import PROJECT_ARCHIVED, ClockDep
from app.projects.models import NOTE_MAX
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, Scope

router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["project-instructions"])

NOTHING_TO_PUBLISH = "The Draft is the same as the Current Version, so there's nothing to publish."
NOTHING_TO_REVERT = "There's no earlier Version to revert to."

_PATH = "/projects/{project_id}/instructions"


def _errors(*codes: tuple[int, str]) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ErrorResponse, "description": text} for code, text in codes}


class VersionAuthor(BaseModel):
    id: uuid.UUID
    name: str


class InstructionsVersionOut(BaseModel):
    id: uuid.UUID
    number: int
    markdown: str
    note: str
    # Who published it; none for the v1 made from the Instructions already there when Versions
    # were introduced.
    author: VersionAuthor | None
    created_at: datetime
    # The Version that was Current when this one was published: reverting while this one is
    # Current goes back to it.
    previous_version_id: uuid.UUID | None


class InstructionsHistoryOut(BaseModel):
    # None until the Instructions are first published.
    current_version_id: uuid.UUID | None
    # Newest first.
    versions: list[InstructionsVersionOut]


class PublishInstructionsRequest(BaseModel):
    # Why this Version exists, shown in the history.
    note: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NOTE_MAX)
    ]


def _out(view: instructions.VersionView) -> InstructionsVersionOut:
    version = view.version
    author = view.author and VersionAuthor(id=view.author.id, name=view.author.name)
    return InstructionsVersionOut(
        id=version.id,
        number=version.number,
        markdown=version.markdown,
        note=version.note,
        author=author,
        created_at=version.created_at,
        previous_version_id=version.previous_version_id,
    )


@router.get(
    f"{_PATH}/versions",
    operation_id="listProjectInstructionsVersions",
    responses=_errors((404, NOT_FOUND)),
)
async def list_versions(project_id: uuid.UUID, scope: Scope, db: Db) -> InstructionsHistoryOut:
    """The Project Instructions Versions, newest first, and which is the Current Version."""
    try:
        found = await instructions.history(db, scope, project_id)
    except service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return InstructionsHistoryOut(
        current_version_id=found.current_version_id,
        versions=[_out(view) for view in found.versions],
    )


@router.post(
    f"{_PATH}/versions",
    operation_id="publishProjectInstructions",
    status_code=status.HTTP_201_CREATED,
    responses=_errors((404, NOT_FOUND), (409, f"{PROJECT_ARCHIVED} Or: {NOTHING_TO_PUBLISH}")),
)
async def publish_instructions(
    project_id: uuid.UUID,
    body: PublishInstructionsRequest,
    scope: Scope,
    db: Db,
    clock: ClockDep,
) -> InstructionsVersionOut:
    """Publishes the Instructions Draft with a note as the next Version, which becomes the
    Current Version. Records ``project.instructions_published``."""
    try:
        view = await instructions.publish(db, scope, project_id, body.note, now=clock.now())
    except service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except service.ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    except instructions.NothingToPublishError:
        raise HTTPException(status.HTTP_409_CONFLICT, NOTHING_TO_PUBLISH) from None
    return _out(view)


@router.post(
    f"{_PATH}/revert",
    operation_id="revertProjectInstructions",
    responses=_errors((404, NOT_FOUND), (409, f"{PROJECT_ARCHIVED} Or: {NOTHING_TO_REVERT}")),
)
async def revert_instructions(
    project_id: uuid.UUID, scope: Scope, db: Db, clock: ClockDep
) -> InstructionsVersionOut:
    """Moves the Current Version back to the Version that was Current before it, and returns
    it. The Draft is unchanged. Records ``project.instructions_reverted``."""
    try:
        view = await instructions.revert(db, scope, project_id, now=clock.now())
    except service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except service.ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    except instructions.NothingToRevertError:
        raise HTTPException(status.HTTP_409_CONFLICT, NOTHING_TO_REVERT) from None
    return _out(view)
