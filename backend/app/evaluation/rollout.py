"""Rollout evaluation: before Bulk publish rolls a Project Instructions Version out, one Run per
selected Agent with an Evaluation Set, the Live Version as it is against its rollout side (the
Live Version's AgentConfig answering with the new Instructions Version).

Starting skips the selected Agents that can't be evaluated: not the Project's, archived, never
published, or without an Evaluation Set. It starts every Run in one transaction, so a refusal
for one Agent (a Run already in progress, or its Live Version's Provider Credential gone) starts
none. A rollout side is created only here, never through the general Run API.

The read gives each Agent's state for the rollout dialog, from its latest Rollout evaluation of
its current Live Version with that Instructions Version that is in progress or completed:
``running``, ``regressions`` or ``clear``, else ``not_evaluated``. It is advisory: Bulk publish
never depends on it.
"""

import enum
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.agents.resolution import ProviderCredentialGoneError
from app.agents.service import AgentNotFoundError, get_agent
from app.evaluation.models import (
    IN_PROGRESS,
    EvaluationCase,
    EvaluationRun,
    EvaluationRunSide,
    RunKind,
    RunStatus,
)
from app.evaluation.service import (
    REGRESSION,
    CaseResults,
    EmptySetError,
    RunDetail,
    RunInProgressError,
    add_run,
    get_run,
    plan_run,
    run_results,
)
from app.projects.instructions import project_version
from app.projects.models import InstructionsVersion
from app.projects.service import active_project, get_project
from app.tenancy.repository import OrganisationScope


class RolloutInProgressError(Exception):
    """A selected Agent already has a Run in progress."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


class RolloutCredentialGoneError(Exception):
    """A selected Agent's Live Version names a Provider Credential that no longer exists."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


class RolloutState(enum.StrEnum):
    # No Evaluation Set, not live, or no Rollout evaluation of the Live Version with these
    # Instructions that is in progress or completed.
    NOT_EVALUATED = "not_evaluated"
    RUNNING = "running"
    REGRESSIONS = "regressions"
    CLEAR = "clear"


@dataclass(frozen=True)
class AgentRollout:
    agent: Agent
    has_set: bool
    state: RolloutState
    # The Rollout evaluation the state comes from; None while not evaluated.
    run: RunDetail | None
    # Its Regressions, in set order, once completed.
    regressions: list[CaseResults]


@dataclass(frozen=True)
class Rollout:
    instructions: InstructionsVersion
    agents: list[AgentRollout]


async def start_rollout(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    instructions_version_id: uuid.UUID,
    agent_ids: Sequence[uuid.UUID],
    *,
    now: datetime,
) -> list[uuid.UUID]:
    """Starts a Rollout evaluation of each selected Agent that can be evaluated, returning the
    queued Runs' IDs for the caller to enqueue. Refused for an archived Project, Instructions
    that aren't the Project's (``InstructionsVersionNotFoundError``), an Agent with a Run in
    progress (``RolloutInProgressError``) or whose Live Version can't be resolved
    (``RolloutCredentialGoneError``), and with neither an Evaluation Model nor a Default Model
    to judge."""
    project = await active_project(session, scope, project_id)
    instructions = await project_version(session, project, instructions_version_id)
    started: list[uuid.UUID] = []
    # In a stable order, so concurrent starts lock the Agents' rows in the same order.
    for agent_id in sorted(set(agent_ids)):
        try:
            found = await get_agent(session, scope, project_id, agent_id)
        except AgentNotFoundError:
            continue
        if found.agent.archived_at is not None or found.agent.live_version_id is None:
            continue
        try:
            plan = await plan_run(
                session,
                scope,
                project_id,
                agent_id,
                sides=None,
                instructions_version_id=None,
                instructions_draft=False,
                starting=True,
                now=now,
                rollout=instructions,
            )
        except EmptySetError:
            continue
        except RunInProgressError:
            raise RolloutInProgressError(found.agent.name) from None
        except ProviderCredentialGoneError:
            raise RolloutCredentialGoneError(found.agent.name) from None
        run = await add_run(
            session, scope, plan, RunKind.ROLLOUT, now=now, started_by=scope.member_id
        )
        started.append(run.id)
    await session.commit()
    return started


def _counts(
    sides: list[EvaluationRunSide], live: uuid.UUID, instructions: InstructionsVersion
) -> bool:
    """Whether a Rollout evaluation's sides are the Live Version and it with ``instructions``."""
    first, second = sides
    return first.agent_version_id == live and second.instructions_version_id == instructions.id


async def _agent_rollout(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent: Agent,
    instructions: InstructionsVersion,
) -> AgentRollout:
    has_set = (
        await session.scalar(
            select(EvaluationCase.id).where(EvaluationCase.agent_id == agent.id).limit(1)
        )
        is not None
    )
    runs = list(
        await session.scalars(
            select(EvaluationRun)
            .where(
                EvaluationRun.agent_id == agent.id,
                EvaluationRun.kind == RunKind.ROLLOUT,
                EvaluationRun.status.in_([*IN_PROGRESS, RunStatus.COMPLETED]),
            )
            .order_by(EvaluationRun.created_at.desc(), EvaluationRun.id)
        )
    )
    sides: dict[uuid.UUID, list[EvaluationRunSide]] = {}
    for side in await session.scalars(
        select(EvaluationRunSide)
        .where(EvaluationRunSide.run_id.in_([run.id for run in runs]))
        .order_by(EvaluationRunSide.position)
    ):
        sides.setdefault(side.run_id, []).append(side)
    live = agent.live_version_id
    counting = [
        run
        for run in runs
        if has_set and live is not None and _counts(sides[run.id], live, instructions)
    ]
    if not counting:
        return AgentRollout(agent, has_set, RolloutState.NOT_EVALUATED, None, [])
    latest = counting[0]
    if latest.status in IN_PROGRESS:
        detail = await get_run(session, scope, project_id, agent.id, latest.id)
        return AgentRollout(agent, has_set, RolloutState.RUNNING, detail, [])
    detail, cases = await run_results(session, scope, project_id, agent.id, latest.id)
    regressions = [case for case in cases if case.change == REGRESSION]
    state = RolloutState.REGRESSIONS if regressions else RolloutState.CLEAR
    return AgentRollout(agent, has_set, state, detail, regressions)


async def rollout(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    instructions_version_id: uuid.UUID,
    agent_ids: Sequence[uuid.UUID] | None = None,
) -> Rollout:
    """Each of ``agent_ids`` (every active Agent of the Project when None) that is one of the
    Project's active Agents, oldest first, with its Rollout evaluation state for
    ``instructions_version_id`` (``InstructionsVersionNotFoundError`` when it isn't the
    Project's)."""
    project = await get_project(session, scope, project_id)
    instructions = await project_version(session, project, instructions_version_id)
    query = select(Agent).where(
        Agent.organisation_id == scope.organisation_id,
        Agent.project_id == project.id,
        Agent.archived_at.is_(None),
    )
    if agent_ids is not None:
        query = query.where(Agent.id.in_(agent_ids))
    agents = await session.scalars(query.order_by(Agent.created_at, Agent.id))
    return Rollout(
        instructions,
        [
            await _agent_rollout(session, scope, project_id, agent, instructions)
            for agent in agents.all()
        ],
    )
