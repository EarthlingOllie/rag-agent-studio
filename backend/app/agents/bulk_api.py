"""Bulk routes: publishing several Agents with a Project Instructions Version, reverting several
Agents, and the Instructions rollout summary ("N Agents behind"). Editors and Owners may use
them; every bulk action is audited per Agent and once on the Project."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints

from app.agents import bulk, versions
from app.agents.api import ClockDep, archived, not_found
from app.agents.versions_api import (
    UNKNOWN_INSTRUCTIONS_VERSION,
    VersionNumberOut,
    _errors,
    _number,
)
from app.auth.api import Db
from app.projects.api import PROJECT_ARCHIVED
from app.projects.models import NOTE_MAX
from app.projects.service import ProjectArchivedError, ProjectNotFoundError
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, Scope

router = APIRouter(prefix=ORGANISATION_PREFIX + "/projects/{project_id}", tags=["agent-bulk"])

# How many Agents one bulk action may name.
BULK_MAX = 200
AgentIds = Annotated[list[uuid.UUID], Field(min_length=1, max_length=BULK_MAX)]


class BulkPublishRequest(BaseModel):
    agent_ids: AgentIds
    # The Project Instructions Version each new Agent Version pins.
    instructions_version_id: uuid.UUID
    # Why these Versions exist; "Bulk published with Instructions vN" when left out.
    note: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NOTE_MAX)]
        | None
    ) = None


class BulkRevertRequest(BaseModel):
    agent_ids: AgentIds


class BulkOutcomeOut(BaseModel):
    agent_id: uuid.UUID
    # Null when no such Agent was found in the Project.
    name: str | None
    status: Literal["succeeded", "skipped", "failed"]
    # Why it was skipped or failed.
    reason: str | None
    # After a success: the Version that is now Live and the Instructions Version it pins.
    live_version: VersionNumberOut | None
    instructions_version: VersionNumberOut | None


class BulkResultOut(BaseModel):
    # Recorded on every Live History entry and Audit Event the action made.
    bulk_operation_id: uuid.UUID
    # One per Agent, in the order asked (a repeated ID once).
    results: list[BulkOutcomeOut]


class RolloutAgentOut(BaseModel):
    id: uuid.UUID
    name: str
    # Null while the Agent has never been published.
    live_version: VersionNumberOut | None
    # The Instructions Version the Live Version pins; null when not live or it pins none.
    instructions_version: VersionNumberOut | None
    # The Draft differs from the Live Version; a bulk publish doesn't include those edits.
    has_draft_changes: bool
    # Live, but not pinning the Current Instructions Version.
    behind: bool


class InstructionsRolloutOut(BaseModel):
    # Null until the Instructions are first published.
    current_version: VersionNumberOut | None
    # How many Agents are behind the Current Version.
    behind: int
    # The Project's active Agents, oldest first.
    agents: list[RolloutAgentOut]


def _result(result: bulk.BulkResult) -> BulkResultOut:
    return BulkResultOut(
        bulk_operation_id=result.bulk_operation_id,
        results=[
            BulkOutcomeOut(
                agent_id=outcome.agent_id,
                name=outcome.name,
                status=outcome.status,
                reason=outcome.reason,
                live_version=outcome.live_version and _number(outcome.live_version),
                instructions_version=outcome.instructions_version
                and _number(outcome.instructions_version),
            )
            for outcome in result.outcomes
        ],
    )


_BULK_ERRORS = _errors((404, NOT_FOUND), (409, PROJECT_ARCHIVED))


@router.post(
    "/agents/bulk-publish",
    operation_id="bulkPublishAgents",
    responses=_errors(
        (404, NOT_FOUND), (409, PROJECT_ARCHIVED), (422, UNKNOWN_INSTRUCTIONS_VERSION)
    ),
)
async def bulk_publish_agents(
    project_id: uuid.UUID, body: BulkPublishRequest, scope: Scope, db: Db, clock: ClockDep
) -> BulkResultOut:
    """Publishes a new Version of each Agent from its Live configuration (never its Draft)
    pinning the chosen Instructions Version, and makes it Live. Each Agent is processed in its
    own transaction; never-published Agents and Agents already on that Version are skipped.
    Records ``agent.bulk_published`` per Agent and ``project.agents_bulk_published``."""
    try:
        result = await bulk.bulk_publish(
            db,
            scope,
            project_id,
            body.agent_ids,
            body.instructions_version_id,
            body.note,
            now=clock.now(),
        )
    except ProjectNotFoundError:
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    except versions.InstructionsVersionNotFoundError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, UNKNOWN_INSTRUCTIONS_VERSION
        ) from None
    return _result(result)


@router.post("/agents/bulk-revert", operation_id="bulkRevertAgents", responses=_BULK_ERRORS)
async def bulk_revert_agents(
    project_id: uuid.UUID, body: BulkRevertRequest, scope: Scope, db: Db, clock: ClockDep
) -> BulkResultOut:
    """Moves each Agent's Live Version back one step in its Live History. Each Agent is
    processed in its own transaction; Agents with nothing to revert to are skipped. Records
    ``agent.bulk_reverted`` per Agent and ``project.agents_bulk_reverted``."""
    try:
        result = await bulk.bulk_revert(db, scope, project_id, body.agent_ids, now=clock.now())
    except ProjectNotFoundError:
        raise not_found() from None
    except ProjectArchivedError:
        raise archived() from None
    return _result(result)


@router.get(
    "/instructions/rollout",
    operation_id="getInstructionsRollout",
    responses=_errors((404, NOT_FOUND)),
)
async def get_instructions_rollout(
    project_id: uuid.UUID, scope: Scope, db: Db
) -> InstructionsRolloutOut:
    """Which Instructions Version each active Agent's Live Version pins, whether its Draft has
    unpublished changes, and how many Agents are behind the Current Version."""
    try:
        found = await bulk.rollout(db, scope, project_id)
    except ProjectNotFoundError:
        raise not_found() from None
    return InstructionsRolloutOut(
        current_version=found.current_version and _number(found.current_version),
        behind=found.behind,
        agents=[
            RolloutAgentOut(
                id=agent.agent.id,
                name=agent.agent.name,
                live_version=agent.live_version and _number(agent.live_version),
                instructions_version=agent.instructions_version
                and _number(agent.instructions_version),
                has_draft_changes=agent.has_draft_changes,
                behind=agent.behind,
            )
            for agent in found.agents
        ],
    )
