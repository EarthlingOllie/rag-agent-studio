"""Agent routes: a Project's Agents, creating one, reading one, saving its Draft and archiving
it, which Editors and Owners may do, and restoring or permanently deleting an archived Agent,
which only Owners may do."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints

from app.agents import service
from app.agents.config import AgentConfig
from app.agents.models import NAME_MAX
from app.agents.validation import InvalidDraftError
from app.auth.api import Db, ErrorResponse
from app.core.clock import Clock, get_clock
from app.projects.api import PROJECT_ARCHIVED
from app.projects.service import ProjectArchivedError, ProjectNotFoundError
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY, OwnerScope, Scope

router = APIRouter(prefix=ORGANISATION_PREFIX + "/projects/{project_id}", tags=["agents"])

ClockDep = Annotated[Clock, Depends(get_clock)]
AgentName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX)
]

AGENT_ARCHIVED = "This Agent is archived. An Owner can restore it."
AGENT_NOT_ARCHIVED = "This Agent isn't archived."
ARCHIVE_BEFORE_DELETING = "Only an archived Agent can be deleted. Archive it first."
NAME_MISMATCH = "Type the Agent's name exactly to delete it."
STALE_DRAFT = (
    "Someone else saved this Draft after you opened it. Load their changes, or save yours over "
    "them."
)

NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": NOT_FOUND}
}
ARCHIVED_RESPONSE: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": PROJECT_ARCHIVED}
}
AGENT_ARCHIVED_RESPONSE: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": f"{PROJECT_ARCHIVED} Or: {AGENT_ARCHIVED}"}
}
OWNERS_ONLY_RESPONSE: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse, "description": OWNERS_ONLY}
}


class LiveVersionOut(BaseModel):
    id: uuid.UUID
    number: int


class AgentOut(BaseModel):
    id: uuid.UUID
    # Unguessable; the embed (spec 06) addresses the Agent by it.
    public_id: str
    project_id: uuid.UUID
    name: str
    created_at: datetime
    archived_at: datetime | None
    draft: AgentConfig
    draft_updated_at: datetime
    # Moves on with every change of the Draft. Send it as ``base_revision`` with a change so
    # that a Draft someone has changed since is not overwritten.
    draft_revision: int
    # The Version Visitors are served; null while the Agent has never been published, so it
    # is not live.
    live_version: LiveVersionOut | None
    # Whether the Draft differs from the Live Version; false while the Agent is not live.
    has_unpublished_changes: bool
    # The budget alert: the Agent's daily Token Budget ran out, so Visitors get its unavailable
    # text. Cleared at midnight UTC, when a new day's budget starts.
    budget_exhausted: bool
    # The Block rate alert: in the last hourly rollup, the share of Visitor messages the input
    # Guardrail blocked had spiked against the week before, as in an attack.
    block_rate_alert: bool


class DraftConflictOut(BaseModel):
    detail: str
    # The latest Draft, when the change was refused because the Draft had moved on from the
    # revision it was made on.
    latest: AgentOut | None = None


BaseRevision = Annotated[
    int | None,
    Query(
        description=(
            "The Draft revision the change was made on. When the Draft has moved on since, the "
            "change is refused with 409 and the latest Draft. Left out, the Draft is replaced."
        )
    ),
]

STALE_DRAFT_RESPONSE: dict[int | str, dict[str, Any]] = {
    409: {
        "model": DraftConflictOut,
        "description": f"{STALE_DRAFT} Or: {PROJECT_ARCHIVED} Or: {AGENT_ARCHIVED}",
    }
}


class CreateAgentRequest(BaseModel):
    name: AgentName


def agent_out(found: service.AgentWithDraft) -> AgentOut:
    agent = found.agent
    return AgentOut(
        id=agent.id,
        public_id=agent.public_id,
        project_id=agent.project_id,
        name=agent.name,
        created_at=agent.created_at,
        archived_at=agent.archived_at,
        draft=found.draft,
        draft_updated_at=found.draft_updated_at,
        draft_revision=found.draft_revision,
        live_version=found.live_version
        and LiveVersionOut(id=found.live_version.id, number=found.live_version.number),
        has_unpublished_changes=found.has_unpublished_changes,
        budget_exhausted=agent.budget_exhausted_at is not None,
        block_rate_alert=agent.block_rate_alert_at is not None,
    )


def stale_draft(error: service.StaleDraftError) -> JSONResponse:
    """The 409 for a Draft change made on a revision the Draft has moved on from."""
    conflict = DraftConflictOut(detail=STALE_DRAFT, latest=agent_out(error.latest))
    return JSONResponse(conflict.model_dump(mode="json"), status.HTTP_409_CONFLICT)


def not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)


def archived() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED)


def agent_archived() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, AGENT_ARCHIVED)


@router.get("/agents", operation_id="listAgents", responses=NOT_FOUND_RESPONSE)
async def list_agents(
    project_id: uuid.UUID,
    scope: Scope,
    db: Db,
    archived: Annotated[bool, Query(description="List archived Agents instead.")] = False,
) -> list[AgentOut]:
    """The Project's active Agents, oldest first, or with ``archived=true`` its archived ones."""
    try:
        found = await service.list_agents(db, scope, project_id, archived=archived)
    except ProjectNotFoundError:
        raise not_found() from None
    return [agent_out(agent) for agent in found]


@router.post(
    "/agents",
    status_code=status.HTTP_201_CREATED,
    operation_id="createAgent",
    responses={**NOT_FOUND_RESPONSE, **ARCHIVED_RESPONSE},
)
async def create_agent(
    project_id: uuid.UUID, body: CreateAgentRequest, scope: Scope, db: Db, clock: ClockDep
) -> AgentOut:
    """Creates an Agent with a default Draft; records ``agent.created``."""
    try:
        found = await service.create_agent(db, scope, project_id, name=body.name, now=clock.now())
    except ProjectNotFoundError:
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    return agent_out(found)


@router.get("/agents/{agent_id}", operation_id="getAgent", responses=NOT_FOUND_RESPONSE)
async def get_agent(project_id: uuid.UUID, agent_id: uuid.UUID, scope: Scope, db: Db) -> AgentOut:
    """The Agent, archived or not."""
    try:
        return agent_out(await service.get_agent(db, scope, project_id, agent_id))
    except (ProjectNotFoundError, service.AgentNotFoundError):
        raise not_found() from None


@router.put(
    "/agents/{agent_id}/draft",
    operation_id="saveAgentDraft",
    response_model=AgentOut,
    responses={**NOT_FOUND_RESPONSE, **STALE_DRAFT_RESPONSE},
)
async def save_agent_draft(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: AgentConfig,
    scope: Scope,
    db: Db,
    clock: ClockDep,
    base_revision: BaseRevision = None,
) -> AgentOut | JSONResponse:
    """Replaces the Agent's Draft with a valid AgentConfig. Besides shapes and ranges, each
    credential must offer the chosen model for its setting's capability and each Tag must be
    the Project's; every problem is reported in one 422, located like a validation error. An
    archived Agent's Draft can't be changed. With ``base_revision``, a Draft someone has changed
    since is refused with 409 and the latest Draft."""
    try:
        found = await service.save_draft(
            db, scope, project_id, agent_id, body, base_revision=base_revision, now=clock.now()
        )
    except (ProjectNotFoundError, service.AgentNotFoundError):
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    except service.AgentArchivedError:
        raise agent_archived() from None
    except service.StaleDraftError as error:
        return stale_draft(error)
    except InvalidDraftError as error:
        raise RequestValidationError([p.as_error() for p in error.problems]) from None
    return agent_out(found)


@router.post(
    "/agents/{agent_id}/archive",
    operation_id="archiveAgent",
    responses={**NOT_FOUND_RESPONSE, **AGENT_ARCHIVED_RESPONSE},
)
async def archive_agent(
    project_id: uuid.UUID, agent_id: uuid.UUID, scope: Scope, db: Db, clock: ClockDep
) -> AgentOut:
    """Archives the Agent: it leaves the Agents list and starts no new Playground Conversation,
    but keeps its Draft and Conversations. Records ``agent.archived``."""
    try:
        found = await service.archive_agent(db, scope, project_id, agent_id, now=clock.now())
    except (ProjectNotFoundError, service.AgentNotFoundError):
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    except service.AgentArchivedError:
        raise agent_archived() from None
    return agent_out(found)


@router.post(
    "/agents/{agent_id}/restore",
    operation_id="restoreAgent",
    responses={
        **OWNERS_ONLY_RESPONSE,
        **NOT_FOUND_RESPONSE,
        409: {
            "model": ErrorResponse,
            "description": f"{AGENT_NOT_ARCHIVED} Or: {PROJECT_ARCHIVED}",
        },
    },
)
async def restore_agent(
    project_id: uuid.UUID, agent_id: uuid.UUID, scope: OwnerScope, db: Db, clock: ClockDep
) -> AgentOut:
    """Restores an archived Agent to the Agents list (Owners only). Records ``agent.restored``."""
    try:
        found = await service.restore_agent(db, scope, project_id, agent_id, now=clock.now())
    except (ProjectNotFoundError, service.AgentNotFoundError):
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    except service.AgentNotArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, AGENT_NOT_ARCHIVED) from None
    return agent_out(found)


class DeleteAgentRequest(BaseModel):
    # The Agent's name, typed by the Owner to confirm; it must match exactly.
    confirm_name: str


@router.delete(
    "/agents/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="deleteAgent",
    responses={
        400: {"model": ErrorResponse, "description": NAME_MISMATCH},
        **OWNERS_ONLY_RESPONSE,
        **NOT_FOUND_RESPONSE,
        409: {
            "model": ErrorResponse,
            "description": f"{ARCHIVE_BEFORE_DELETING} Or: {PROJECT_ARCHIVED}",
        },
    },
)
async def delete_agent(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: DeleteAgentRequest,
    scope: OwnerScope,
    db: Db,
    clock: ClockDep,
) -> Response:
    """Permanently deletes an archived Agent (Owners only), once ``confirm_name`` is its name.
    Its Draft, Conversations and their Messages and Traces go with it, and ``agent.deleted``
    is recorded. This can't be undone."""
    try:
        await service.delete_agent(
            db, scope, project_id, agent_id, confirm_name=body.confirm_name, now=clock.now()
        )
    except (ProjectNotFoundError, service.AgentNotFoundError):
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    except service.AgentNotArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, ARCHIVE_BEFORE_DELETING) from None
    except service.AgentNameMismatchError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NAME_MISMATCH) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
