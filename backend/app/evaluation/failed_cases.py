"""Reading failed Evaluation Cases for other modules: the cases that failed on a side running an
Agent Version in the latest finished Evaluation Run with such a side (the evidence of a
Suggestion run, spec 16), and the copied cases with their Runs by ID (reading that evidence
back).

A side runs the Version when it is a ``version`` side of it; a Run is finished once it has
``completed``. A case fails on the side when most of its answered repeats there fail
(``app.evaluation.combining``). The Evaluation tables stay this module's own.
"""

import uuid
from collections.abc import Collection
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluation.combining import CaseOutcome, Repeat, SideResult, side_result
from app.evaluation.models import (
    EvaluationCaseResult,
    EvaluationRun,
    EvaluationRunCase,
    EvaluationRunSide,
    EvaluationVerdict,
    RunStatus,
    SideKind,
)


@dataclass(frozen=True)
class FailedCase:
    run: EvaluationRun
    run_case: EvaluationRunCase
    result: SideResult
    # Its repeats on the side, in order, each with its Verdicts.
    repeats: list[Repeat]


async def failed_cases(
    session: AsyncSession, agent_id: uuid.UUID, agent_version_id: uuid.UUID
) -> list[FailedCase]:
    """The cases, in set order, that failed on a side running the Agent Version in the Agent's
    latest finished Run with such a side; none without one."""
    found = (
        await session.execute(
            select(EvaluationRun, EvaluationRunSide)
            .join(EvaluationRunSide, EvaluationRunSide.run_id == EvaluationRun.id)
            .where(
                EvaluationRun.agent_id == agent_id,
                EvaluationRun.status == RunStatus.COMPLETED,
                EvaluationRunSide.kind == SideKind.VERSION,
                EvaluationRunSide.agent_version_id == agent_version_id,
            )
            .order_by(EvaluationRun.finished_at.desc(), EvaluationRunSide.position)
            .limit(1)
        )
    ).first()
    if found is None:
        return []
    run, side = found
    cases = await session.scalars(
        select(EvaluationRunCase)
        .where(EvaluationRunCase.run_id == run.id)
        .order_by(EvaluationRunCase.position)
    )
    results = list(
        await session.scalars(
            select(EvaluationCaseResult)
            .where(EvaluationCaseResult.side_id == side.id)
            .order_by(EvaluationCaseResult.repeat)
        )
    )
    verdicts: dict[uuid.UUID, list[EvaluationVerdict]] = {}
    for verdict in await session.scalars(
        select(EvaluationVerdict)
        .where(EvaluationVerdict.result_id.in_([r.id for r in results]))
        .order_by(EvaluationVerdict.position)
    ):
        verdicts.setdefault(verdict.result_id, []).append(verdict)
    failed: list[FailedCase] = []
    for run_case in cases:
        repeats = [
            Repeat(r, verdicts.get(r.id, [])) for r in results if r.run_case_id == run_case.id
        ]
        result = side_result(repeats)
        if result.outcome == CaseOutcome.FAIL:
            failed.append(FailedCase(run, run_case, result, repeats))
    return failed


async def run_cases_of(
    session: AsyncSession, run_case_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, tuple[EvaluationRunCase, EvaluationRun]]:
    """Each copied case with its Run, by the copied case's ID."""
    rows = await session.execute(
        select(EvaluationRunCase, EvaluationRun)
        .join(EvaluationRun, EvaluationRun.id == EvaluationRunCase.run_id)
        .where(EvaluationRunCase.id.in_(run_case_ids))
    )
    return {run_case.id: (run_case, run) for run_case, run in rows.all()}
