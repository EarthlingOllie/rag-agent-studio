"""Evaluation Runs as a job type of the job reliability module (``app.jobs.reliability``,
ADR-0020).

Its rows are Evaluation Runs: Queued is queued, Running is in progress. A Run is paid work, so a
Run whose job stopped writing heartbeats is never restarted: the sweeper ends it Interrupted,
keeping its answers, Verdicts and Cost, which frees the Agent. Its job claims a Run from Queued
only, so a second delivery, or the message the sweeper sends after a recovery, does nothing.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluation.models import EvaluationRun, RunStatus
from app.jobs.reliability import JobTable
from app.worker.celery_app import EVALUATION_RUN_TASK
from app.worker.publisher import current_publisher

RUN_ROWS = JobTable(
    EvaluationRun,
    EvaluationRun.id,
    queued=RunStatus.QUEUED,
    in_progress=RunStatus.RUNNING,
    reclaims_stale=False,
)


class EvaluationRunPolicy:
    """What the sweeper does with Evaluation Runs."""

    job = EVALUATION_RUN_TASK
    tables: Sequence[JobTable] = (RUN_ROWS,)

    async def recover(
        self, session: AsyncSession, table: JobTable, row_id: uuid.UUID, now: datetime
    ) -> None:
        """An interrupted Run: it ends Interrupted, keeping what it answered and spent."""
        await session.execute(
            update(EvaluationRun)
            .where(EvaluationRun.id == row_id)
            .values(status=RunStatus.INTERRUPTED, finished_at=now, claim_id=None, heartbeat_at=None)
            .execution_options(synchronize_session=False)
        )

    async def resend(self, row_id: uuid.UUID) -> None:
        await current_publisher().run_evaluation(row_id)


EVALUATION_RUNS = EvaluationRunPolicy()
