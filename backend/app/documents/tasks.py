"""The ingestion Celery task. The API enqueues it when an upload is confirmed or a Failed
Document is retried; the task re-enqueues itself, after a backoff, for transient failures."""

import asyncio
import uuid

from app.core.db import create_engine, create_sessionmaker
from app.core.settings import load_settings
from app.documents import pipeline
from app.documents.ports import current_ports
from app.worker.celery_app import celery_app

INGEST_TASK = "documents.ingest"


async def _ingest(document_id: uuid.UUID, attempt_number: int) -> float | None:
    settings = load_settings()
    engine = create_engine(settings)
    try:
        return await pipeline.ingest(
            create_sessionmaker(engine),
            current_ports(),
            document_id,
            chunk_max_tokens=settings.chunk_max_tokens,
            attempt=pipeline.Attempt(
                number=attempt_number,
                max_attempts=settings.ingestion_max_attempts,
                retry_base_seconds=settings.ingestion_retry_base_seconds,
                retry_max_seconds=settings.ingestion_retry_max_seconds,
            ),
        )
    finally:
        await engine.dispose()


@celery_app.task(name=INGEST_TASK)
def ingest_document(document_id: str, attempt: int = 1) -> None:
    """Runs ingestion for one Document (Queued to Ready or Failed). After a transient failure,
    the task sends itself again with the next attempt number, delayed by the backoff the
    pipeline asks for. (In eager mode, in tests, the next attempt runs at once.)"""
    delay = asyncio.run(_ingest(uuid.UUID(document_id), attempt))
    if delay is not None:
        ingest_document.apply_async((document_id,), {"attempt": attempt + 1}, countdown=delay)


async def enqueue_ingestion(document_id: uuid.UUID) -> None:
    """Sends the task from a thread: sending blocks on the broker, and in eager mode (tests) the
    task itself runs there, with its own event loop."""
    await asyncio.to_thread(ingest_document.delay, str(document_id))
