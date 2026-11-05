"""The ingestion Celery task. The API enqueues it when an upload is confirmed."""

import asyncio
import uuid

import httpx2

from app.core.db import create_engine, create_sessionmaker
from app.core.settings import load_settings
from app.documents import pipeline
from app.documents.ports import current_ports
from app.worker.celery_app import celery_app

INGEST_TASK = "documents.ingest"
DELETE_OBJECTS_TASK = "documents.delete_objects"


async def _ingest(document_id: uuid.UUID) -> None:
    settings = load_settings()
    engine = create_engine(settings)
    ports = current_ports()
    try:
        async with httpx2.AsyncClient(timeout=settings.model_timeout_seconds) as client:
            await pipeline.ingest(
                create_sessionmaker(engine),
                ports,
                ports.open_gateway(client),
                document_id,
                chunk_max_tokens=settings.chunk_max_tokens,
                delete_objects=enqueue_object_deletion,
            )
    finally:
        await engine.dispose()


@celery_app.task(name=INGEST_TASK)
def ingest_document(document_id: str) -> None:
    """Runs ingestion for one Document (Queued to Ready or Failed)."""
    asyncio.run(_ingest(uuid.UUID(document_id)))


async def enqueue_ingestion(document_id: uuid.UUID) -> None:
    """Sends the task from a thread: sending blocks on the broker, and in eager mode (tests) the
    task itself runs there, with its own event loop."""
    await asyncio.to_thread(ingest_document.delay, str(document_id))


async def _delete_objects(keys: list[str]) -> None:
    store = current_ports().object_store
    for key in keys:
        await store.delete(key)


@celery_app.task(name=DELETE_OBJECTS_TASK)
def delete_stored_objects(keys: list[str]) -> None:
    """Deletes stored objects (originals and converted markdown) nothing refers to any more:
    a deleted Document's, or a replaced edition's. Deleting a missing object is not an error."""
    asyncio.run(_delete_objects(keys))


async def enqueue_object_deletion(keys: list[str]) -> None:
    """Schedules deletion of the objects; sent from a thread, as ``enqueue_ingestion`` is."""
    await asyncio.to_thread(delete_stored_objects.delay, keys)
