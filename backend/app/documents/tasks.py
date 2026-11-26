"""The ingestion Celery task. The API enqueues it when an upload is confirmed or a Failed
Document is retried; the task re-enqueues itself, after a backoff, for transient failures. The
attempt number is read from the Document's row, never from the message."""

import asyncio
import uuid
from functools import partial

import httpx2

from app.core.db import create_engine, create_sessionmaker
from app.core.settings import load_settings
from app.documents import pipeline
from app.documents.ports import current_ports
from app.evaluation.expectations import recheck_document
from app.jobs.reliability import Timings
from app.worker.celery_app import DELETE_OBJECTS_TASK, INGEST_TASK, celery_app
from app.worker.publisher import current_publisher


async def _ingest(document_id: uuid.UUID) -> None:
    delay = await _run_ingestion(document_id)
    if delay is not None:
        await current_publisher().ingest_document(document_id, countdown=delay)


async def _run_ingestion(document_id: uuid.UUID) -> float | None:
    settings = load_settings()
    engine = create_engine(settings)
    ports = current_ports()
    sessionmaker = create_sessionmaker(engine)
    try:
        async with httpx2.AsyncClient(timeout=settings.model_timeout_seconds) as client:
            return await pipeline.ingest(
                sessionmaker,
                ports,
                ports.open_gateway(client),
                document_id,
                chunk_max_tokens=settings.chunk_max_tokens,
                conversion_timeout_seconds=settings.ingestion_conversion_timeout_seconds,
                delete_objects=enqueue_object_deletion,
                on_new_edition=partial(recheck_document, sessionmaker),
                attempt=pipeline.Attempt(
                    max_attempts=settings.ingestion_max_attempts,
                    retry_base_seconds=settings.ingestion_retry_base_seconds,
                    retry_max_seconds=settings.ingestion_retry_max_seconds,
                ),
                clock=ports.clock(),
                timings=Timings.from_settings(settings),
            )
    finally:
        await engine.dispose()


@celery_app.task(name=INGEST_TASK, ignore_result=True)
def ingest_document(document_id: str, attempt: int | None = None) -> None:
    """Runs ingestion for one Document (Queued to Ready or Failed). After a transient failure,
    the task sends itself again, through the Job publisher, delayed by the backoff the pipeline
    asks for. (In eager mode, in tests, the next attempt runs at once.) ``attempt`` is ignored:
    messages sent before the attempt number moved to the row carry it."""
    del attempt
    asyncio.run(_ingest(uuid.UUID(document_id)))


async def enqueue_ingestion(document_id: uuid.UUID) -> None:
    """Sends the ingestion job through the Job publisher."""
    await current_publisher().ingest_document(document_id)


async def _delete_objects(keys: list[str]) -> None:
    store = current_ports().object_store
    for key in keys:
        await store.delete(key)


@celery_app.task(name=DELETE_OBJECTS_TASK, ignore_result=True)
def delete_stored_objects(keys: list[str]) -> None:
    """Deletes stored objects (originals and converted markdown) nothing refers to any more:
    a deleted Document's, or a replaced edition's. Deleting a missing object is not an error."""
    asyncio.run(_delete_objects(keys))


async def enqueue_object_deletion(keys: list[str]) -> None:
    """Schedules deletion of the objects through the Job publisher."""
    await current_publisher().delete_objects(keys)
