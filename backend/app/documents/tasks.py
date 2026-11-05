"""The ingestion Celery task. The API enqueues it when an upload is confirmed."""

import asyncio
import uuid

from app.core.db import create_engine, create_sessionmaker
from app.core.settings import load_settings
from app.documents import pipeline
from app.documents.ports import current_ports
from app.worker.celery_app import celery_app

INGEST_TASK = "documents.ingest"


async def _ingest(document_id: uuid.UUID) -> None:
    settings = load_settings()
    engine = create_engine(settings)
    try:
        await pipeline.ingest(
            create_sessionmaker(engine),
            current_ports(),
            document_id,
            chunk_max_tokens=settings.chunk_max_tokens,
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
