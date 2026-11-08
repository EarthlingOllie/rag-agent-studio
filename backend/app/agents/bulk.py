"""Bulk publish, bulk revert and the Project Instructions rollout.

- **Bulk publish** rolls a Project Instructions Version out to several Agents at once. Each new
  Agent Version is built from the Agent's **Live** configuration plus the chosen Instructions
  Version, never from its Draft (ADR-0003), so unreviewed Draft edits are never shipped by
  accident. An Agent that has never been published is skipped (its first Version must be
  reviewed), and so is one whose Live Version already pins that Instructions Version.
- **Bulk revert** steps several Agents back at once, each by the Live History revert rule
  (``app.agents.versions``).

Both take a list of Agent IDs in one Project. Each Agent is processed in **its own
transaction**, under its row lock (``SELECT … FOR UPDATE``), so a failure on one Agent rolls
back only that Agent and never leaves another half-updated. The result is one outcome per
Agent, in request order: succeeded, skipped with the reason, or failed with the reason. A
repeated ID is processed once; an ID that isn't one of the Project's Agents fails as "not
found", whether it is another Project's, another Organisation's or no Agent at all.

Every bulk action gets a **bulk operation ID**. It is written on each Live History entry the
action makes (``bulk_publish`` or ``bulk_revert``), on each Agent's Audit Event
(``agent.bulk_published`` or ``agent.bulk_reverted``) and on one summary Audit Event on the
Project (``project.agents_bulk_published`` or ``project.agents_bulk_reverted``) with the counts.

The **rollout** summary lists the Project's active Agents with the Instructions Version each
one's Live Version pins, whether its Draft differs from its Live Version, and whether it is
**behind**: live but not pinning the Current Instructions Version.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.agents import versions
from app.agents.api import AGENT_ARCHIVED
from app.agents.config import AgentConfig
from app.agents.models import Agent, AgentVersion
from app.agents.service import AgentNotFoundError, AgentWithDraft, get_agent, list_agents
from app.projects.models import InstructionsVersion
from app.projects.service import active_project, get_project
from app.tenancy.repository import OrganisationScope

logger = logging.getLogger(__name__)

NEVER_PUBLISHED = (
    "Never published, so it has no Live configuration to build from. Publish it from its page "
    "first."
)
NOT_FOUND = "Not found."
UNEXPECTED_FAILURE = "Something went wrong, so nothing was changed for this Agent. Try again."

Status = Literal["succeeded", "skipped", "failed"]


@dataclass(frozen=True)
class Outcome:
    agent_id: uuid.UUID
    # None when the Agent wasn't found.
    name: str | None
    status: Status
    reason: str | None = None
    # After a success: the Version that is now Live and the Instructions Version it pins.
    live_version: versions.VersionNumber | None = None
    instructions_version: versions.PinnedInstructions | None = None


@dataclass(frozen=True)
class BulkResult:
    bulk_operation_id: uuid.UUID
    outcomes: list[Outcome]


class _SkippedError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


class _FailedError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


Work = Callable[[AgentWithDraft], Awaitable[versions.VersionView]]


async def _each(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    work: Work,
) -> Outcome:
    """Runs ``work`` on one Agent in its own transaction, under its row lock."""
    name = None
    try:
        found = await get_agent(session, scope, project_id, agent_id, lock=True)
        name = found.agent.name
        if found.agent.archived_at is not None:
            raise _FailedError(AGENT_ARCHIVED)
        view = await work(found)
        live = versions.VersionNumber(view.version.id, view.version.number)
        await session.commit()
    except AgentNotFoundError:
        await session.rollback()
        return Outcome(agent_id, None, "failed", NOT_FOUND)
    except _SkippedError as skipped:
        await session.rollback()
        return Outcome(agent_id, name, "skipped", skipped.reason)
    except _FailedError as failed:
        await session.rollback()
        return Outcome(agent_id, name, "failed", failed.reason)
    except Exception:
        await session.rollback()
        logger.exception("Bulk action failed for Agent %s", agent_id)
        return Outcome(agent_id, name, "failed", UNEXPECTED_FAILURE)
    # Plain values: a later Agent's rollback expires every loaded row.
    return Outcome(
        agent_id,
        name,
        "succeeded",
        live_version=live,
        instructions_version=view.instructions,
    )


async def _run(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_ids: list[uuid.UUID],
    move: versions.Move,
    operation_id: uuid.UUID,
    work: Work,
    summary: dict[str, object],
    now: datetime,
) -> BulkResult:
    # Ends the transaction that checked the Project, so each Agent gets a fresh one.
    await session.commit()
    outcomes = [
        await _each(session, scope, project_id, agent_id, work)
        for agent_id in dict.fromkeys(agent_ids)
    ]
    counts = {
        status: sum(o.status == status for o in outcomes)
        for status in ("succeeded", "skipped", "failed")
    }
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action=f"project.agents_{move.audit_action.removeprefix('agent.')}",
        target=audit.AuditTarget("project", project_id),
        after={"bulk_operation_id": str(operation_id), **summary, **counts},
        occurred_at=now,
    )
    await session.commit()
    return BulkResult(operation_id, outcomes)


async def bulk_publish(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_ids: list[uuid.UUID],
    instructions_version_id: uuid.UUID,
    note: str | None,
    *,
    now: datetime,
) -> BulkResult:
    """Publishes a new Version of each Agent from its Live configuration, pinning
    ``instructions_version_id``, and makes it Live. See the module docstring."""
    project = await active_project(session, scope, project_id)
    pinned_id = await versions.project_instructions_version(
        session, project.id, instructions_version_id
    )
    pinned = await session.get_one(InstructionsVersion, pinned_id)
    number = pinned.number
    note = note or f"Bulk published with Instructions v{number}"
    operation_id = uuid.uuid4()
    move = versions.Move(versions.BULK_PUBLISH, operation_id)

    async def publish_one(found: AgentWithDraft) -> versions.VersionView:
        agent = found.agent
        if agent.live_version_id is None:
            raise _SkippedError(NEVER_PUBLISHED)
        live = await session.get_one(AgentVersion, agent.live_version_id)
        if live.instructions_version_id == pinned_id:
            raise _SkippedError(f"Already Live with Instructions v{number}.")
        return await versions.make_live(
            session, scope, agent, live.config, pinned_id, note, move, now=now
        )

    summary: dict[str, object] = {
        "instructions_version": {"version_id": str(pinned_id), "number": number}
    }
    return await _run(
        session, scope, project.id, agent_ids, move, operation_id, publish_one, summary, now
    )


async def bulk_revert(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_ids: list[uuid.UUID],
    *,
    now: datetime,
) -> BulkResult:
    """Reverts each Agent one step back in its Live History. See the module docstring."""
    project = await active_project(session, scope, project_id)
    operation_id = uuid.uuid4()
    move = versions.Move(versions.BULK_REVERT, operation_id)

    async def revert_one(found: AgentWithDraft) -> versions.VersionView:
        try:
            return await versions.step_back(session, scope, found.agent, move, now=now)
        except versions.NothingToRevertError:
            raise _SkippedError(versions.NOTHING_TO_REVERT) from None
        except versions.RevertTargetInvalidError:
            raise _FailedError(versions.REVERT_TARGET_INVALID) from None

    return await _run(
        session, scope, project.id, agent_ids, move, operation_id, revert_one, {}, now
    )


@dataclass(frozen=True)
class RolloutAgent:
    agent: Agent
    live_version: versions.VersionNumber | None
    instructions_version: versions.PinnedInstructions | None
    has_draft_changes: bool
    behind: bool


@dataclass(frozen=True)
class Rollout:
    current_version: versions.PinnedInstructions | None
    agents: list[RolloutAgent]

    @property
    def behind(self) -> int:
        return sum(agent.behind for agent in self.agents)


async def rollout(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID
) -> Rollout:
    """The Project's active Agents, oldest first, with the Instructions Version each one's Live
    Version pins and whether it is behind the Current Version. Archived Projects can be read."""
    project = await get_project(session, scope, project_id)
    rows = await session.execute(
        select(InstructionsVersion.id, InstructionsVersion.number).where(
            InstructionsVersion.project_id == project.id
        )
    )
    numbers = {version_id: number for version_id, number in rows}

    def pinned(version_id: uuid.UUID | None) -> versions.PinnedInstructions | None:
        if version_id is None:
            return None
        return versions.PinnedInstructions(version_id, numbers[version_id])

    current_id = project.current_instructions_version_id
    agents = []
    for found in await list_agents(session, scope, project.id):
        if found.live_version is None:
            agents.append(RolloutAgent(found.agent, None, None, False, False))
            continue
        live = await session.get_one(AgentVersion, found.live_version.id)
        agents.append(
            RolloutAgent(
                found.agent,
                versions.VersionNumber(live.id, live.number),
                pinned(live.instructions_version_id),
                found.draft != AgentConfig.model_validate(live.config),
                current_id is not None and live.instructions_version_id != current_id,
            )
        )
    return Rollout(pinned(current_id), agents)


async def pinned_to(
    session: AsyncSession, project_id: uuid.UUID, instructions_version_id: uuid.UUID
) -> list[tuple[Agent, versions.VersionNumber]]:
    """The Project's active Agents whose Live Version pins ``instructions_version_id``, oldest
    first: the candidates for a bulk revert after that Instructions Version is reverted."""
    rows = await session.execute(
        select(Agent, AgentVersion.id, AgentVersion.number)
        .join(AgentVersion, AgentVersion.id == Agent.live_version_id)
        .where(
            Agent.project_id == project_id,
            Agent.archived_at.is_(None),
            AgentVersion.instructions_version_id == instructions_version_id,
        )
        .order_by(Agent.created_at, Agent.id)
    )
    return [(agent, versions.VersionNumber(vid, number)) for agent, vid, number in rows]
