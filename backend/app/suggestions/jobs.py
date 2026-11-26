"""Suggestion runs as a job type of the job reliability module (``app.jobs.reliability``,
ADR-0020).

Its rows are Suggestions: Queued is queued, and gathering, proposing and checking are in
progress. A run is paid work, so its job claims it from Queued only (a second delivery, or the
message the sweeper sends after a recovery, does nothing: no evidence, changes or gaps are added
and the proposer isn't paid twice), and a run whose job stopped writing heartbeats is never
restarted. The sweeper settles it instead: with no proposal stored, it fails with the reason
``interrupted``; with one stored (it was checking), it keeps the proposal and its proposing Cost
and completes as not checked, and its check Run becomes Interrupted. A check Run an Editor
cancels directly settles its Suggestion the same way (``check_stopped``), so it is never stranded
on checking.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluation.models import IN_PROGRESS as RUN_IN_PROGRESS
from app.evaluation.models import EvaluationCaseResult, EvaluationRun, RunStatus
from app.jobs import reliability
from app.jobs.reliability import JobTable
from app.suggestions.models import (
    WORKING,
    Suggestion,
    SuggestionFailure,
    SuggestionStatus,
)
from app.worker.celery_app import SUGGESTION_RUN_TASK
from app.worker.publisher import current_publisher


@dataclass(frozen=True)
class _SuggestionRows(JobTable):
    """The job claims a run into gathering; it is in progress through all of its phases."""

    def _in_progress(self) -> ColumnElement[bool]:
        in_progress: ColumnElement[bool] = self.model.status.in_(WORKING)
        return in_progress


SUGGESTION_ROWS = _SuggestionRows(
    Suggestion,
    Suggestion.id,
    queued=SuggestionStatus.QUEUED,
    in_progress=SuggestionStatus.GATHERING,
    reclaims_stale=False,
)


async def check_cost(session: AsyncSession, run_id: uuid.UUID) -> Decimal | None:
    """What a Suggestion's check has spent, answering and judging, at the prices frozen as each
    ran: nothing before its first answer, and None when it answered but no price was known."""
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


async def _not_checked(
    session: AsyncSession, check_run_id: uuid.UUID, now: datetime
) -> dict[str, Any]:
    """What a run whose check stopped before it finished becomes: completed, keeping its
    proposal and what proposing cost, with what the check spent frozen. It reads as not
    checked."""
    return {
        "status": SuggestionStatus.COMPLETED,
        "finished_at": now,
        "checking_cost_usd": await check_cost(session, check_run_id),
        "claim_id": None,
        "heartbeat_at": None,
    }


async def check_stopped(session: AsyncSession, run_id: uuid.UUID, now: datetime) -> None:
    """The check Run ``run_id`` was cancelled directly, in the caller's transaction: its
    Suggestion, if it is still checking, completes as not checked."""
    await session.execute(
        update(Suggestion)
        .where(Suggestion.check_run_id == run_id, Suggestion.status == SuggestionStatus.CHECKING)
        .values(**await _not_checked(session, run_id, now))
        .execution_options(synchronize_session=False)
    )


class SuggestionRunPolicy:
    """What the sweeper does with Suggestion runs."""

    job = SUGGESTION_RUN_TASK
    tables: Sequence[JobTable] = (SUGGESTION_ROWS,)

    async def recover(
        self, session: AsyncSession, table: JobTable, row_id: uuid.UUID, now: datetime
    ) -> None:
        """An interrupted run: not checked when its proposal was stored (its check Run becomes
        Interrupted), else Failed as interrupted."""
        suggestion = await session.get_one(Suggestion, row_id)
        check_run_id = suggestion.check_run_id
        if check_run_id is None:
            suggestion.status = SuggestionStatus.FAILED
            suggestion.failure_reason = SuggestionFailure.INTERRUPTED
            suggestion.finished_at = now
            reliability.released(suggestion)
            return
        await session.execute(
            update(EvaluationRun)
            .where(
                EvaluationRun.id == check_run_id,
                EvaluationRun.status.in_(RUN_IN_PROGRESS),
            )
            .values(status=RunStatus.INTERRUPTED, finished_at=now, claim_id=None, heartbeat_at=None)
            .execution_options(synchronize_session=False)
        )
        await session.execute(
            update(Suggestion)
            .where(Suggestion.id == row_id)
            .values(**await _not_checked(session, check_run_id, now))
            .execution_options(synchronize_session=False)
        )

    async def resend(self, row_id: uuid.UUID) -> None:
        await current_publisher().run_suggestion(row_id)


SUGGESTION_RUNS = SuggestionRunPolicy()
