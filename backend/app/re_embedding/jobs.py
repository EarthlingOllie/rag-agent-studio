"""Re-embedding as a job type of the job reliability module (``app.jobs.reliability``, ADR-0020).

Its rows are re-embed jobs, ``running`` throughout: one without a claim is queued, one with a
claim is in progress. A job whose heartbeat stopped loses its claim and is sent again; the
restarted job carries on from the Chunks still missing the pending model's vector. Interrupted
``re_embed_max_interruptions`` times in a row with no new Chunks embedded in between, it fails
instead, through the same failure path as any other failure, and the Project keeps its active
Embedding Model.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import load_settings
from app.jobs.reliability import JobTable, queued_values
from app.re_embedding.models import ReEmbedJob, ReEmbedStatus
from app.re_embedding.service import fail, model_chunks
from app.worker.celery_app import RE_EMBED_TASK
from app.worker.publisher import current_publisher

RE_EMBED_ROWS = JobTable(
    ReEmbedJob, ReEmbedJob.id, queued=ReEmbedStatus.RUNNING, in_progress=ReEmbedStatus.RUNNING
)

INTERRUPTED = (
    "Re-embedding was interrupted {times} times without embedding any new Chunks. "
    "The Project still uses {model}; choose the model again to retry."
)


class ReEmbedPolicy:
    """What the sweeper does with re-embed jobs."""

    job = RE_EMBED_TASK
    tables: Sequence[JobTable] = (RE_EMBED_ROWS,)

    async def recover(
        self, session: AsyncSession, table: JobTable, row_id: uuid.UUID, now: datetime
    ) -> None:
        """An interrupted re-embed: counted, then queued to carry on, or failed at the cap."""
        job = await session.get_one(ReEmbedJob, row_id)
        embedded = await model_chunks(session, job.project_id, job.model_id)
        progressed = job.chunks_at_interruption is None or embedded > job.chunks_at_interruption
        job.interruptions = 1 if progressed else job.interruptions + 1
        job.chunks_at_interruption = embedded
        cap = load_settings().re_embed_max_interruptions
        if job.interruptions >= cap:
            await fail(session, job, INTERRUPTED.format(times=cap, model=job.from_model_id))
            return
        for column, value in queued_values(now).items():
            setattr(job, column, value)

    async def resend(self, row_id: uuid.UUID) -> None:
        await current_publisher().re_embed(row_id)


RE_EMBED = ReEmbedPolicy()
