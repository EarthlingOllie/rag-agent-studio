"""A Suggestion's check (spec 16): a Run of kind ``suggestion``, the Version the Suggestion was
made from against a ``suggestion`` side, that Version's AgentConfig with the suggested changes,
answering with the Instructions the Version pins.

A suggestion side is created only here, for a Suggestion run, never through the general Run API.
The check is in the Agent's Run history and never counts in the Evaluation summary, which reads
only Runs of the Draft. The ``suggestions`` module starts, stops and reads it through this
interface, never through the Run tables.
"""

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.config import AgentConfig
from app.evaluation.models import (
    IN_PROGRESS,
    EvaluationCaseResult,
    EvaluationRun,
    RunKind,
    RunStatus,
)
from app.evaluation.service import (
    REGRESSION,
    CaseResults,
    SuggestionSide,
    add_run,
    plan_run,
    run_results,
)
from app.tenancy.repository import OrganisationScope


class CheckState(enum.StrEnum):
    RUNNING = "running"
    # Completed with no Regression.
    CLEAR = "clear"
    # Completed with at least one Regression: a warning, never a block.
    REGRESSIONS = "regressions"
    # Every answer errored.
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class CheckResult:
    state: CheckState
    run_id: uuid.UUID
    # Each side's Evaluation score; None while it has none.
    live_score: float | None
    suggestion_score: float | None
    # Its Regressions, in set order, with the answers whose Verdicts give their reasons.
    regressions: list[CaseResults]
    # The suggestion side, whose failing Verdicts are the Regressions' reasons.
    suggestion_side_id: uuid.UUID


async def start_check(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    version_id: uuid.UUID,
    config: AgentConfig,
    started_by: uuid.UUID | None,
    now: datetime,
) -> EvaluationRun:
    """Adds the queued check of ``config`` against the Version ``version_id``, for the caller to
    commit and run. The Agent's row is locked while it is added. Refused as ``plan_run`` refuses
    (an archived Agent, an empty set, a side that can't be resolved, no judge)."""
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
        suggestion=SuggestionSide(version_id, config),
    )
    return await add_run(session, scope, plan, RunKind.SUGGESTION, now=now, started_by=started_by)


async def stop_check(session: AsyncSession, run_id: uuid.UUID, now: datetime) -> None:
    """Cancels the check if it is still queued or running, for the caller to commit. Its job
    stops before its next answer; what it answered and spent so far is kept."""
    run = await session.get_one(EvaluationRun, run_id, with_for_update=True)
    if run.status in IN_PROGRESS:
        run.status = RunStatus.CANCELLED
        run.finished_at = now


async def fail_check(session: AsyncSession, run_id: uuid.UUID, reason: str, now: datetime) -> None:
    """Ends the check ``failed`` with ``reason`` if it is still queued or running, for the caller
    to commit: its Suggestion run hit an unexpected error. What it answered so far is kept."""
    run = await session.get_one(EvaluationRun, run_id, with_for_update=True)
    if run.status in IN_PROGRESS:
        run.status = RunStatus.FAILED
        run.error_message = reason
        run.finished_at = now


async def check_cost(session: AsyncSession, run_id: uuid.UUID) -> Decimal | None:
    """What the check has spent, answering and judging, at the prices frozen as each ran: nothing
    before its first answer, and None when it answered but no price was known."""
    answered, answers, judging = (
        await session.execute(
            select(
                func.count(EvaluationCaseResult.id),
                func.sum(EvaluationCaseResult.cost_usd),
                func.sum(EvaluationCaseResult.judge_cost_usd),
            ).where(EvaluationCaseResult.run_id == run_id)
        )
    ).one()
    if answered and answers is None and judging is None:
        return None
    return Decimal(answers or 0) + Decimal(judging or 0)


_STATES = {
    RunStatus.FAILED: CheckState.FAILED,
    RunStatus.CANCELLED: CheckState.CANCELLED,
    # Its worker stopped: read as a cancelled check (spec 21).
    RunStatus.INTERRUPTED: CheckState.CANCELLED,
}


async def read_check(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    run_id: uuid.UUID,
) -> CheckResult:
    """The check's state, both Evaluation scores and its Regressions."""
    detail, cases = await run_results(session, scope, project_id, agent_id, run_id)
    live, suggested = detail.sides
    regressions = [case for case in cases if case.change == REGRESSION]
    status = RunStatus(detail.run.status)
    if status in IN_PROGRESS:
        state = CheckState.RUNNING
    elif status == RunStatus.COMPLETED:
        state = CheckState.REGRESSIONS if regressions else CheckState.CLEAR
    else:
        state = _STATES[status]
    return CheckResult(
        state,
        run_id,
        detail.scores[live.id].score,
        detail.scores[suggested.id].score,
        regressions,
        suggested.id,
    )
