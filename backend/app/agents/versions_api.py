"""Agent Version routes: publishing the Draft as the Live Version, reverting the Live Version,
the Version list, one Version, and the Live History. Editors and Owners may use them; every
publish and revert is audited.

Versions are immutable, so there is no route that changes or deletes one."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, StringConstraints

from app.agents import service, versions
from app.agents.api import (
    AGENT_ARCHIVED,
    ClockDep,
    agent_archived,
    archived,
    not_found,
)
from app.agents.config import AgentConfig
from app.auth.api import Db, ErrorResponse
from app.projects.api import PROJECT_ARCHIVED
from app.projects.models import NOTE_MAX
from app.projects.service import ProjectArchivedError, ProjectNotFoundError
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, Scope

router = APIRouter(
    prefix=ORGANISATION_PREFIX + "/projects/{project_id}/agents/{agent_id}", tags=["agent-versions"]
)

UNKNOWN_INSTRUCTIONS_VERSION = "That Instructions Version isn't one of this Project's."
NOTHING_TO_REVERT = "There's no earlier Live Version to revert to."
REVERT_TARGET_INVALID = (
    "The Version that was Live before uses a Provider Credential or model that is no longer "
    "available, so it can't be made Live again. Publish a fixed Version instead."
)


def _errors(*codes: tuple[int, str]) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ErrorResponse, "description": text} for code, text in codes}


class PersonOut(BaseModel):
    id: uuid.UUID
    name: str


class VersionNumberOut(BaseModel):
    id: uuid.UUID
    number: int


class AgentVersionOut(BaseModel):
    id: uuid.UUID
    number: int
    note: str
    author: PersonOut
    created_at: datetime
    # The Draft's configuration when it was published.
    config: AgentConfig
    # The Project Instructions Version it runs with; null when the Project had none, so it
    # runs with no Project Instructions.
    instructions_version: VersionNumberOut | None


class AgentVersionsOut(BaseModel):
    # Null while the Agent has never been published (not live).
    live_version_id: uuid.UUID | None
    # Newest first.
    versions: list[AgentVersionOut]


class LiveHistoryEntryOut(BaseModel):
    # Null for the first publish.
    from_version: VersionNumberOut | None
    to_version: VersionNumberOut
    # publish, revert, bulk_publish or bulk_revert.
    action: str
    actor: PersonOut
    occurred_at: datetime
    # Set when a bulk action made the change.
    bulk_operation_id: uuid.UUID | None


class PublishAgentRequest(BaseModel):
    # Why this Version exists, shown in the history.
    note: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NOTE_MAX)
    ]
    # The Project Instructions Version to pin; the Project's Current Version when left out.
    instructions_version_id: uuid.UUID | None = None


def _number(found: versions.VersionNumber | versions.PinnedInstructions) -> VersionNumberOut:
    return VersionNumberOut(id=found.id, number=found.number)


def _person(person: versions.Person) -> PersonOut:
    return PersonOut(id=person.id, name=person.name)


def _out(view: versions.VersionView) -> AgentVersionOut:
    version = view.version
    return AgentVersionOut(
        id=version.id,
        number=version.number,
        note=version.note,
        author=_person(view.author),
        created_at=version.created_at,
        config=view.config,
        instructions_version=view.instructions and _number(view.instructions),
    )


@router.post(
    "/versions",
    operation_id="publishAgent",
    status_code=status.HTTP_201_CREATED,
    responses=_errors(
        (404, NOT_FOUND),
        (409, f"{PROJECT_ARCHIVED} Or: {AGENT_ARCHIVED}"),
        (422, UNKNOWN_INSTRUCTIONS_VERSION),
    ),
)
async def publish_agent(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: PublishAgentRequest,
    scope: Scope,
    db: Db,
    clock: ClockDep,
) -> AgentVersionOut:
    """Publishes the Agent's Draft with a note as its next Version, pinning the chosen Project
    Instructions Version (the Current Version by default), and makes it the Live Version.
    Records ``agent.published`` and a Live History entry."""
    try:
        view = await versions.publish(
            db,
            scope,
            project_id,
            agent_id,
            body.note,
            instructions_version_id=body.instructions_version_id,
            now=clock.now(),
        )
    except (ProjectNotFoundError, service.AgentNotFoundError):
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    except service.AgentArchivedError:
        raise agent_archived() from None
    except versions.InstructionsVersionNotFoundError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, UNKNOWN_INSTRUCTIONS_VERSION
        ) from None
    return _out(view)


@router.post(
    "/revert",
    operation_id="revertAgent",
    responses=_errors(
        (404, NOT_FOUND),
        (
            409,
            f"{NOTHING_TO_REVERT} Or: {REVERT_TARGET_INVALID} Or: {PROJECT_ARCHIVED} "
            f"Or: {AGENT_ARCHIVED}",
        ),
    ),
)
async def revert_agent(
    project_id: uuid.UUID, agent_id: uuid.UUID, scope: Scope, db: Db, clock: ClockDep
) -> AgentVersionOut:
    """Moves the Live Version back one step in the Live History, to the Version that was Live
    before the current one was published, restoring its configuration and pinned Instructions.
    Returns that Version. The Draft is unchanged. Records ``agent.reverted`` and a Live History
    entry."""
    try:
        view = await versions.revert(db, scope, project_id, agent_id, now=clock.now())
    except (ProjectNotFoundError, service.AgentNotFoundError):
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    except service.AgentArchivedError:
        raise agent_archived() from None
    except versions.NothingToRevertError:
        raise HTTPException(status.HTTP_409_CONFLICT, NOTHING_TO_REVERT) from None
    except versions.RevertTargetInvalidError:
        raise HTTPException(status.HTTP_409_CONFLICT, REVERT_TARGET_INVALID) from None
    return _out(view)


@router.get("/versions", operation_id="listAgentVersions", responses=_errors((404, NOT_FOUND)))
async def list_agent_versions(
    project_id: uuid.UUID, agent_id: uuid.UUID, scope: Scope, db: Db
) -> AgentVersionsOut:
    """The Agent's Versions, newest first, and which is the Live Version."""
    try:
        found = await versions.list_versions(db, scope, project_id, agent_id)
    except (ProjectNotFoundError, service.AgentNotFoundError):
        raise not_found() from None
    return AgentVersionsOut(
        live_version_id=found.live_version_id, versions=[_out(view) for view in found.versions]
    )


@router.get(
    "/versions/{version_id}", operation_id="getAgentVersion", responses=_errors((404, NOT_FOUND))
)
async def get_agent_version(
    project_id: uuid.UUID, agent_id: uuid.UUID, version_id: uuid.UUID, scope: Scope, db: Db
) -> AgentVersionOut:
    """One of the Agent's Versions."""
    try:
        return _out(await versions.get_version(db, scope, project_id, agent_id, version_id))
    except (ProjectNotFoundError, service.AgentNotFoundError, versions.AgentVersionNotFoundError):
        raise not_found() from None


@router.get(
    "/live-history", operation_id="listAgentLiveHistory", responses=_errors((404, NOT_FOUND))
)
async def list_agent_live_history(
    project_id: uuid.UUID, agent_id: uuid.UUID, scope: Scope, db: Db
) -> list[LiveHistoryEntryOut]:
    """Every change of the Agent's Live Version, newest first: from which Version to which,
    by what action, who and when."""
    try:
        found = await versions.live_history(db, scope, project_id, agent_id)
    except (ProjectNotFoundError, service.AgentNotFoundError):
        raise not_found() from None
    return [
        LiveHistoryEntryOut(
            from_version=view.from_version and _number(view.from_version),
            to_version=_number(view.to_version),
            action=view.entry.action,
            actor=_person(view.actor),
            occurred_at=view.entry.occurred_at,
            bulk_operation_id=view.entry.bulk_operation_id,
        )
        for view in found
    ]
