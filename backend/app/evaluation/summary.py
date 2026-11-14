"""The Evaluation summary for Publish: whether the Draft has been evaluated against the current
Live Version with the Instructions being published, and what that Run found.

Only completed Runs of the Draft against the current Live Version qualify (the Draft alone while
the Agent has never been Published). The summary is advisory: the Publish dialog reads it, and
Publishing never depends on it.
"""

import enum
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import AgentVersion
from app.agents.service import get_agent
from app.evaluation.models import (
    EvaluationCase,
    EvaluationRun,
    EvaluationRunSide,
    RunStatus,
    SideKind,
)
from app.evaluation.service import REGRESSION, CaseResults, RunDetail, run_results
from app.projects.instructions import project_version
from app.projects.models import InstructionsVersion
from app.projects.service import get_project
from app.tenancy.repository import OrganisationScope


class SummaryState(enum.StrEnum):
    # The Agent has no Evaluation Set.
    NO_SET = "no_set"
    # No completed Run of the Draft (against a Live Version or alone) exists.
    NO_RUN = "no_run"
    # The Draft was only compared with a Version that is no longer Live.
    LIVE_CHANGED = "live_changed"
    # The qualifying Run describes an earlier Draft revision.
    STALE = "stale"
    # The qualifying Run's Draft answered with other Instructions than those being published.
    INSTRUCTIONS_DIFFER = "instructions_differ"
    # The qualifying Run found Regressions, or the Draft's Evaluation score is lower than Live's.
    REGRESSIONS = "regressions"
    CLEAR = "clear"


@dataclass(frozen=True)
class PublishSummary:
    state: SummaryState
    # The latest qualifying Run, with its cases' results; None without one.
    run: RunDetail | None
    regressions: list[CaseResults]
    # Whether the Draft's Evaluation score is lower than the Live Version's in that Run.
    lower_score: bool
    # For ``live_changed``: the Version the Draft's latest Run was compared with.
    evaluated_live_version_number: int | None
    # The Instructions Version being published: the one chosen, else the Current one (None when
    # the Project has none).
    publishing_instructions_version_number: int | None


def _draft_last(sides: list[EvaluationRunSide]) -> bool:
    """Whether the Run is of the Draft: the Draft alone, or a Version against the Draft."""
    if sides[-1].kind != SideKind.DRAFT:
        return False
    return len(sides) == 1 or sides[0].kind == SideKind.VERSION


def _against(sides: list[EvaluationRunSide]) -> uuid.UUID | None:
    """The Version the Draft was compared with; None when it ran alone."""
    return sides[0].agent_version_id if len(sides) == 2 else None


async def publish_summary(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    instructions_version_id: uuid.UUID | None,
) -> PublishSummary:
    """The summary for publishing the Draft with ``instructions_version_id`` (the Project's
    Current Instructions Version when None; ``InstructionsVersionNotFoundError`` when it isn't
    the Project's)."""
    project = await get_project(session, scope, project_id)
    found = await get_agent(session, scope, project_id, agent_id)
    publishing = (
        await project_version(session, project, instructions_version_id)
        if instructions_version_id is not None
        else None
        if project.current_instructions_version_id is None
        else await session.get_one(InstructionsVersion, project.current_instructions_version_id)
    )

    def summary(
        state: SummaryState,
        run: RunDetail | None = None,
        regressions: list[CaseResults] | None = None,
        *,
        lower_score: bool = False,
        evaluated_live: int | None = None,
    ) -> PublishSummary:
        return PublishSummary(
            state,
            run,
            regressions or [],
            lower_score,
            evaluated_live,
            None if publishing is None else publishing.number,
        )

    has_case = await session.scalar(
        select(EvaluationCase.id).where(EvaluationCase.agent_id == found.agent.id).limit(1)
    )
    if has_case is None:
        return summary(SummaryState.NO_SET)
    runs = list(
        await session.scalars(
            select(EvaluationRun)
            .where(
                EvaluationRun.agent_id == found.agent.id,
                EvaluationRun.status == RunStatus.COMPLETED,
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
    of_draft = [run for run in runs if _draft_last(sides[run.id])]
    live = found.agent.live_version_id
    qualifying = [run for run in of_draft if _against(sides[run.id]) == live]
    if not qualifying:
        # Compared with a Version that is no longer Live; the Draft running alone describes no
        # Live Version, so it isn't evidence about this one.
        against = [_against(sides[run.id]) for run in of_draft if len(sides[run.id]) == 2]
        if not against:
            return summary(SummaryState.NO_RUN)
        number = await session.scalar(
            select(AgentVersion.number).where(AgentVersion.id == against[0])
        )
        return summary(SummaryState.LIVE_CHANGED, evaluated_live=number)
    detail, cases = await run_results(session, scope, project_id, agent_id, qualifying[0].id)
    regressions = [case for case in cases if case.change == REGRESSION]
    scores = [detail.scores[side.id].score for side in detail.sides]
    live_score, draft_score = scores if len(scores) == 2 else (None, None)
    lower = live_score is not None and draft_score is not None and draft_score < live_score
    draft = detail.sides[-1]
    if detail.stale:
        state = SummaryState.STALE
    elif draft.instructions_draft or draft.instructions_version_id != (
        None if publishing is None else publishing.id
    ):
        state = SummaryState.INSTRUCTIONS_DIFFER
    elif regressions or lower:
        state = SummaryState.REGRESSIONS
    else:
        state = SummaryState.CLEAR
    return summary(state, detail, regressions, lower_score=lower)
