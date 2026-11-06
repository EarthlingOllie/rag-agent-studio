"""Agent routes: a Project's Agents, creating one, reading one and saving its Draft. Editors
and Owners may use them."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.exceptions import RequestValidationError
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
from app.tenancy.policy import NOT_FOUND, Scope

router = APIRouter(prefix=ORGANISATION_PREFIX + "/projects/{project_id}", tags=["agents"])

ClockDep = Annotated[Clock, Depends(get_clock)]
AgentName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX)
]

NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": NOT_FOUND}
}
ARCHIVED_RESPONSE: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": PROJECT_ARCHIVED}
}


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


class CreateAgentRequest(BaseModel):
    name: AgentName


def _out(found: service.AgentWithDraft) -> AgentOut:
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
    )


def not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)


def archived() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED)


@router.get("/agents", operation_id="listAgents", responses=NOT_FOUND_RESPONSE)
async def list_agents(project_id: uuid.UUID, scope: Scope, db: Db) -> list[AgentOut]:
    """The Project's Agents, oldest first."""
    try:
        return [_out(found) for found in await service.list_agents(db, scope, project_id)]
    except ProjectNotFoundError:
        raise not_found() from None


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
    return _out(found)


@router.get("/agents/{agent_id}", operation_id="getAgent", responses=NOT_FOUND_RESPONSE)
async def get_agent(project_id: uuid.UUID, agent_id: uuid.UUID, scope: Scope, db: Db) -> AgentOut:
    try:
        return _out(await service.get_agent(db, scope, project_id, agent_id))
    except (ProjectNotFoundError, service.AgentNotFoundError):
        raise not_found() from None


@router.put(
    "/agents/{agent_id}/draft",
    operation_id="saveAgentDraft",
    responses={**NOT_FOUND_RESPONSE, **ARCHIVED_RESPONSE},
)
async def save_agent_draft(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: AgentConfig,
    scope: Scope,
    db: Db,
    clock: ClockDep,
) -> AgentOut:
    """Replaces the Agent's Draft with a valid AgentConfig. Besides shapes and ranges, each
    credential must offer the chosen model for its setting's capability and each Tag must be
    the Project's; every problem is reported in one 422, located like a validation error."""
    try:
        found = await service.save_draft(db, scope, project_id, agent_id, body, now=clock.now())
    except (ProjectNotFoundError, service.AgentNotFoundError):
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    except InvalidDraftError as error:
        raise RequestValidationError([p.as_error() for p in error.problems]) from None
    return _out(found)
