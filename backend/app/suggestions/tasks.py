"""The Suggestion run Celery task, which the start endpoint enqueues once the run is committed.
It runs through the evaluation ports: the model gateway, the proposing timeout and the clock."""

import asyncio
import uuid

import httpx2

from app.core.db import create_engine, create_sessionmaker
from app.core.settings import load_settings
from app.evaluation.ports import current_evaluation_ports
from app.suggestions.service import run_suggestion
from app.worker.celery_app import SUGGESTION_RUN_TASK, celery_app
from app.worker.publisher import current_publisher


async def _run(suggestion_id: uuid.UUID) -> None:
    settings = load_settings()
    engine = create_engine(settings)
    ports = current_evaluation_ports()
    try:
        async with httpx2.AsyncClient(timeout=settings.model_timeout_seconds) as client:
            gateway = ports.open_gateway(client)
            await run_suggestion(
                create_sessionmaker(engine), ports, gateway, suggestion_id, ports.clock()
            )
    finally:
        await engine.dispose()


@celery_app.task(name=SUGGESTION_RUN_TASK, ignore_result=True)
def run_suggestion_task(suggestion_id: str) -> None:
    """Gathers a queued Suggestion run's evidence and proposes its Suggestion."""
    asyncio.run(_run(uuid.UUID(suggestion_id)))


async def enqueue_suggestion(suggestion_id: uuid.UUID) -> None:
    """Sends the Suggestion run job through the Job publisher."""
    await current_publisher().run_suggestion(suggestion_id)
