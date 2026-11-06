"""The re-embed Celery task. The API enqueues it when a Project's Embedding Model changes while
the Project has Documents; the task re-enqueues itself, after a backoff, when the provider fails."""

import asyncio
import uuid

import httpx2

from app.core.db import create_engine, create_sessionmaker
from app.core.settings import load_settings
from app.documents.pipeline import Attempt
from app.documents.ports import current_ports
from app.re_embedding.job import re_embed
from app.worker.celery_app import celery_app

RE_EMBED_TASK = "projects.re_embed"


async def _re_embed(job_id: uuid.UUID, attempt_number: int) -> float | None:
    settings = load_settings()
    engine = create_engine(settings)
    ports = current_ports()
    try:
        async with httpx2.AsyncClient(timeout=settings.model_timeout_seconds) as client:
            return await re_embed(
                create_sessionmaker(engine),
                ports,
                ports.open_gateway(client),
                job_id,
                batch_size=settings.re_embed_batch_size,
                attempt=Attempt(
                    number=attempt_number,
                    max_attempts=settings.ingestion_max_attempts,
                    retry_base_seconds=settings.ingestion_retry_base_seconds,
                    retry_max_seconds=settings.ingestion_retry_max_seconds,
                ),
            )
    finally:
        await engine.dispose()


@celery_app.task(name=RE_EMBED_TASK)
def re_embed_project(job_id: str, attempt: int = 1) -> None:
    """Runs a re-embed job until it switches, fails or is cancelled. After a provider failure
    the task sends itself again with the next attempt number, delayed by the backoff. (In eager
    mode, in tests, the next attempt runs at once.)"""
    delay = asyncio.run(_re_embed(uuid.UUID(job_id), attempt))
    if delay is not None:
        re_embed_project.apply_async((job_id,), {"attempt": attempt + 1}, countdown=delay)


async def enqueue_re_embed(job_id: uuid.UUID) -> None:
    """Sends the task from a thread, as ``enqueue_ingestion`` does."""
    await asyncio.to_thread(re_embed_project.delay, str(job_id))
