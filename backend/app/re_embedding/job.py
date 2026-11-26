"""The re-embed job: moves a Project's Knowledge Base from its active Embedding Model to the
pending one.

1. Walk the Project's Chunks that have an active-model vector but no pending-model one, a batch
   at a time. Embed each batch's texts (headings and text, as ingestion embeds them) with the
   pending model and write them as new Chunk rows tagged with the pending model, next to the
   old ones. Each batch commits, so progress shows as it goes; retrieval only reads the active
   model's rows, so the old vectors keep serving.
2. When no Chunk is missing its pending vector, switch in the same transaction: the pending
   model becomes the active one and every other model's vectors are deleted.

Uploads during the job embed with both models (``app.documents.pipeline``); one whose
pending-model vectors couldn't be made is picked up by step 1. Each step holds the Project's
lock, so no upload writes Chunks between the last check and the switch.

A failure leaves the Project on its active model: the job is marked failed with a readable
message and the pending model's vectors are deleted. A provider that doesn't answer is retried
with backoff, like ingestion, keeping the vectors written so far.

The job claims its row and writes a heartbeat while it holds the claim (job reliability,
ADR-0020, ``app.re_embedding.jobs``): a second copy can't claim it and exits, and every step
checks the claim first, so a copy given up for dead and replaced writes nothing. Waiting on a
retry, the job gives its claim up and records when the retry is due, so a lost retry is sent
again by the sweeper.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Row, Select, delete, exists, func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from app import audit
from app.core.clock import Clock
from app.credentials.models import ProviderCredential
from app.documents import limits
from app.documents.chunking import embedding_text
from app.documents.models import Chunk
from app.documents.pipeline import Attempt
from app.documents.ports import IngestionPorts
from app.embeddings.port import EmbeddingProviderError
from app.embeddings.provider import UNUSABLE_ERRORS, EmbeddingSizeError, resolve_embedder
from app.embeddings.registry import embedding_model
from app.gateway.gateway import ModelGateway
from app.jobs import reliability
from app.jobs.reliability import Claim, Timings
from app.projects.models import Project
from app.re_embedding.jobs import RE_EMBED_ROWS
from app.re_embedding.models import ReEmbedJob, ReEmbedStatus
from app.re_embedding.service import end, fail

logger = logging.getLogger(__name__)

# Recorded when the job switches the Project over; the same action as an immediate change.
CHANGED = "project.embedding_model_changed"

PROVIDER_FAILED = (
    "The Embedding Model's provider didn't respond after {attempts} attempts. "
    "The Project still uses {model}; choose the model again to retry."
)
PROVIDER_UNUSABLE = (
    "The Embedding Model's provider can't be used: {reason} "
    "The Project still uses {model}; choose the model again once it is fixed."
)
UNEXPECTED = (
    "Re-embedding stopped on an unexpected error. "
    "The Project still uses {model}; choose the model again to retry."
)


@dataclass(frozen=True)
class _Job:
    id: uuid.UUID
    project_id: uuid.UUID
    from_model_id: str
    model_id: str
    # The job's hold on its row (job reliability, ADR-0020).
    claim: Claim


def _missing(job: _Job) -> Select[uuid.UUID, str, list[str]]:
    """The Project's active-model Chunks that have no pending-model vector yet."""
    pending = aliased(Chunk)
    return (
        select(Chunk.id, Chunk.text, Chunk.heading_path)
        .where(
            Chunk.project_id == job.project_id,
            Chunk.embedding_model_id == job.from_model_id,
            ~exists().where(
                pending.document_id == Chunk.document_id,
                pending.edition == Chunk.edition,
                pending.ordinal == Chunk.ordinal,
                pending.embedding_model_id == job.model_id,
            ),
        )
        .order_by(Chunk.id)
    )


async def _held(session: AsyncSession, job: _Job) -> ReEmbedJob | None:
    """The job's row, locked, if this copy still holds its claim: it may have been cancelled
    meanwhile, or given up for dead and taken over by another copy."""
    if not await reliability.holds(session, job.claim):
        return None
    return await session.get_one(ReEmbedJob, job.id)


Embedded = list[tuple[uuid.UUID, list[float]]]
"""Chunk IDs with their pending-model vectors, to write."""

_COPIED = [
    "id",
    "organisation_id",
    "project_id",
    "document_id",
    "edition",
    "ordinal",
    "text",
    "heading_path",
    "page_start",
    "page_end",
    "embedding",
    "embedding_model_id",
    "guardrail_label",
    "guardrail_score",
    "guardrail_reason",
]


async def _write(session: AsyncSession, job: _Job, embedded: Embedded) -> None:
    """Writes a pending-model copy of each Chunk with its new vector. A Chunk deleted meanwhile
    (its Document deleted or replaced) is skipped, as is one an upload already wrote both
    vectors for."""
    for chunk_id, vector in embedded:
        copy = select(
            func.gen_random_uuid(),
            Chunk.organisation_id,
            Chunk.project_id,
            Chunk.document_id,
            Chunk.edition,
            Chunk.ordinal,
            Chunk.text,
            Chunk.heading_path,
            Chunk.page_start,
            Chunk.page_end,
            literal(vector, Chunk.embedding.type),
            literal(job.model_id, Chunk.embedding_model_id.type),
            Chunk.guardrail_label,
            Chunk.guardrail_score,
            Chunk.guardrail_reason,
        ).where(Chunk.id == chunk_id)
        await session.execute(
            insert(Chunk)
            .from_select(_COPIED, copy)
            .on_conflict_do_nothing(constraint="uq_chunks_position")
        )


Batch = list[Row[uuid.UUID, str, list[str]]]


async def _step(
    sessionmaker: async_sessionmaker[AsyncSession],
    job: _Job,
    embedded: Embedded,
    batch_size: int,
) -> Batch | None:
    """One transaction of the job: writes the vectors embedded since the last step, then
    either returns the next batch of Chunks to embed or, when none is left, switches the
    Project over. ``None`` once switched, or if the job was cancelled meanwhile (its vectors
    are then not written)."""
    async with sessionmaker() as session, session.begin():
        # The Project before the job, as choosing a model locks them, so the two never deadlock;
        # holding the Project also keeps uploads from writing Chunks while the job switches.
        project = await session.get_one(Project, job.project_id, with_for_update=True)
        running = await _held(session, job)
        if running is None:
            return None
        await _write(session, job, embedded)
        batch = list((await session.execute(_missing(job).limit(batch_size))).all())
        if batch:
            return batch
        before = {
            "model_id": project.embedding_model_id,
            "credential_id": _id(project.embedding_credential_id),
        }
        await end(session, running, ReEmbedStatus.COMPLETED)
        project.embedding_model_id = running.model_id
        project.embedding_credential_id = running.credential_id
        await session.execute(
            delete(Chunk).where(
                Chunk.project_id == project.id, Chunk.embedding_model_id != running.model_id
            )
        )
        await audit.record(
            session,
            organisation_id=project.organisation_id,
            actor_id=None,
            action=CHANGED,
            target=audit.AuditTarget("project", project.id),
            before=before,
            after={"model_id": running.model_id, "credential_id": _id(running.credential_id)},
        )
    return None


def _id(value: uuid.UUID | None) -> str | None:
    return None if value is None else str(value)


async def _fail(sessionmaker: async_sessionmaker[AsyncSession], job: _Job, message: str) -> None:
    """Marks the job failed with the message, if this copy still holds it (``service.fail``)."""
    async with sessionmaker() as session, session.begin():
        running = await _held(session, job)
        if running is not None:
            await fail(session, running, message)


async def _queue_retry(
    sessionmaker: async_sessionmaker[AsyncSession], job: _Job, due: datetime
) -> bool:
    """Gives the claim up until the retry, due then. ``False`` if this copy no longer holds the
    job (it was cancelled, or another copy took it over): no retry is sent."""
    async with sessionmaker() as session, session.begin():
        running = await _held(session, job)
        if running is None:
            return False
        reliability.released(running)
        running.queued_at = due
    return True


async def re_embed(
    sessionmaker: async_sessionmaker[AsyncSession],
    ports: IngestionPorts,
    gateway: ModelGateway,
    job_id: uuid.UUID,
    *,
    batch_size: int,
    attempt: Attempt,
    clock: Clock,
    timings: Timings,
) -> float | None:
    """Runs the job until it switches, fails or is cancelled. Returns the seconds to wait before
    running again when the provider failed and attempts remain, and ``None`` otherwise (also
    when another copy holds the job, or it isn't running). A heartbeat is written for as long as
    the job holds its claim."""
    async with sessionmaker() as session, session.begin():
        claim = await reliability.claim(
            session, RE_EMBED_ROWS, job_id, now=clock.now(), dead_after=timings.dead_after
        )
        if claim is None:
            return None
        record, credential = (
            await session.execute(
                select(ReEmbedJob, ProviderCredential)
                .outerjoin(ProviderCredential, ProviderCredential.id == ReEmbedJob.credential_id)
                .where(ReEmbedJob.id == job_id)
            )
        ).one()
    job = _Job(record.id, record.project_id, record.from_model_id, record.model_id, claim)
    async with reliability.heartbeat(sessionmaker, claim, clock, timings.heartbeat_seconds):
        return await _run(sessionmaker, ports, gateway, job, credential, batch_size, attempt, clock)


async def _run(
    sessionmaker: async_sessionmaker[AsyncSession],
    ports: IngestionPorts,
    gateway: ModelGateway,
    job: _Job,
    credential: ProviderCredential | None,
    batch_size: int,
    attempt: Attempt,
    clock: Clock,
) -> float | None:
    try:
        embedder = resolve_embedder(
            embedding_model(job.model_id), credential, ports.embedders, gateway
        )
    except UNUSABLE_ERRORS as error:
        await _fail(sessionmaker, job, _unusable(job, str(error)))
        return None
    try:
        embedded: Embedded = []
        while (batch := await _step(sessionmaker, job, embedded, batch_size)) is not None:
            vectors = await embedder.embed_passages(
                [embedding_text(heading_path, text) for _, text, heading_path in batch]
            )
            embedded = [(chunk_id, v) for (chunk_id, _, _), v in zip(batch, vectors, strict=True)]
        return None
    except EmbeddingSizeError as error:
        await _fail(sessionmaker, job, _unusable(job, str(error)))
        return None
    except EmbeddingProviderError:
        logger.warning(
            "Re-embedding: the provider failed",
            extra={"re_embed_job_id": str(job.id), "attempt": attempt.number},
        )
        if attempt.number >= attempt.max_attempts:
            message = PROVIDER_FAILED.format(attempts=attempt.max_attempts, model=job.from_model_id)
            await _fail(sessionmaker, job, message)
            return None
        delay = limits.retry_delay(
            attempt.number,
            base_seconds=attempt.retry_base_seconds,
            max_seconds=attempt.retry_max_seconds,
        )
        due = clock.now() + timedelta(seconds=delay)
        return delay if await _queue_retry(sessionmaker, job, due) else None
    except Exception:
        logger.exception("Re-embedding failed", extra={"re_embed_job_id": str(job.id)})
        await _fail(sessionmaker, job, UNEXPECTED.format(model=job.from_model_id))
        return None


def _unusable(job: _Job, reason: str) -> str:
    return PROVIDER_UNUSABLE.format(reason=reason, model=job.from_model_id)
