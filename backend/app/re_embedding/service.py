"""Starting, cancelling and reading re-embed jobs.

Choosing a new Embedding Model for a Project that has Documents makes it the Project's pending
model and starts a job (``app.re_embedding.job``) that writes the pending model's vectors next
to the active model's. Retrieval keeps using the active model's until the job switches over.

A Project has at most one running job. Choosing again while one runs cancels it: its vectors
are deleted, and the new choice switches at once or starts a new job.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.documents.models import Chunk
from app.projects.models import Project
from app.re_embedding.models import ReEmbedJob, ReEmbedStatus

STARTED = "project.re_embed_started"
FAILED = "project.re_embed_failed"
CANCELLED = "project.re_embed_cancelled"


async def running_job(
    session: AsyncSession, project_id: uuid.UUID, *, lock: bool = False
) -> ReEmbedJob | None:
    """The Project's running job, if it has one: its pending Embedding Model."""
    query = select(ReEmbedJob).where(
        ReEmbedJob.project_id == project_id, ReEmbedJob.status == ReEmbedStatus.RUNNING
    )
    if lock:
        query = query.with_for_update()
    return await session.scalar(query)


async def latest_job(session: AsyncSession, project_id: uuid.UUID) -> ReEmbedJob | None:
    return await session.scalar(
        select(ReEmbedJob)
        .where(ReEmbedJob.project_id == project_id)
        .order_by(ReEmbedJob.created_at.desc(), ReEmbedJob.id)
        .limit(1)
    )


async def model_chunks(session: AsyncSession, project_id: uuid.UUID, model_id: str) -> int:
    """How many of the Project's Chunks have a vector of the model."""
    count = await session.scalar(
        select(func.count()).where(
            Chunk.project_id == project_id, Chunk.embedding_model_id == model_id
        )
    )
    return count or 0


@dataclass(frozen=True)
class Progress:
    embedded: int
    total: int


async def progress(session: AsyncSession, job: ReEmbedJob) -> Progress:
    """How many of the Knowledge Base's Chunks have the pending model's vector, of how many.
    Counted live while the job runs (uploads during the job add to both), stored once it ends."""
    if job.status != ReEmbedStatus.RUNNING:
        return Progress(job.embedded_chunks, job.total_chunks)
    return Progress(
        await model_chunks(session, job.project_id, job.model_id),
        await model_chunks(session, job.project_id, job.from_model_id),
    )


async def end(
    session: AsyncSession, job: ReEmbedJob, status: ReEmbedStatus, *, error: str | None = None
) -> None:
    """Ends a running job in the caller's transaction, recording its final progress. A job that
    didn't complete has its vectors deleted (the job's model is never the active one while it
    runs); a completed one's become the Project's."""
    final = await progress(session, job)
    job.embedded_chunks, job.total_chunks = final.embedded, final.total
    job.status = status
    job.error_message = error
    job.finished_at = func.now()
    if status != ReEmbedStatus.COMPLETED:
        await session.execute(
            delete(Chunk).where(
                Chunk.project_id == job.project_id, Chunk.embedding_model_id == job.model_id
            )
        )


def summary(project: Project, job: ReEmbedJob | None) -> dict[str, str | None]:
    """The Project's Embedding Model choice, with the pending one, for Audit Events."""
    credential_id = project.embedding_credential_id
    return {
        "model_id": project.embedding_model_id,
        "credential_id": None if credential_id is None else str(credential_id),
        "pending_model_id": None if job is None else job.model_id,
        "pending_credential_id": None
        if job is None or job.credential_id is None
        else str(job.credential_id),
    }


async def cancel(
    session: AsyncSession, project: Project, job: ReEmbedJob, *, actor_id: uuid.UUID, now: datetime
) -> None:
    """Cancels the running job in the caller's transaction, deleting its vectors; records
    ``project.re_embed_cancelled``."""
    before = summary(project, job)
    await end(session, job, ReEmbedStatus.CANCELLED)
    await audit.record(
        session,
        organisation_id=project.organisation_id,
        actor_id=actor_id,
        action=CANCELLED,
        target=audit.AuditTarget("project", project.id),
        before=before,
        after=summary(project, None),
        occurred_at=now,
    )


async def start(
    session: AsyncSession,
    project: Project,
    *,
    model_id: str,
    credential_id: uuid.UUID | None,
    actor_id: uuid.UUID,
    now: datetime,
) -> ReEmbedJob:
    """Makes the model the Project's pending one with a running job, in the caller's
    transaction; records ``project.re_embed_started``. The caller enqueues the job once
    committed."""
    job = ReEmbedJob(
        organisation_id=project.organisation_id,
        project_id=project.id,
        from_model_id=project.embedding_model_id,
        model_id=model_id,
        credential_id=credential_id,
        status=ReEmbedStatus.RUNNING,
        embedded_chunks=0,
        total_chunks=0,
        started_by=actor_id,
    )
    session.add(job)
    await session.flush()
    await audit.record(
        session,
        organisation_id=project.organisation_id,
        actor_id=actor_id,
        action=STARTED,
        target=audit.AuditTarget("project", project.id),
        before=summary(project, None),
        after=summary(project, job),
        occurred_at=now,
    )
    return job
