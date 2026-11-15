"""The Evaluation Run Celery task, which the start endpoint enqueues once the Run is committed."""

import asyncio
import uuid

import httpx2

from app.core.db import create_engine, create_sessionmaker
from app.core.settings import load_settings
from app.evaluation.job import run_evaluation
from app.evaluation.ports import current_evaluation_ports
from app.worker.celery_app import celery_app

EVALUATION_RUN_TASK = "evaluation.run"


async def _run(run_id: uuid.UUID) -> None:
    settings = load_settings()
    engine = create_engine(settings)
    ports = current_evaluation_ports()
    try:
        async with httpx2.AsyncClient(timeout=settings.model_timeout_seconds) as client:
            gateway = ports.open_gateway(client)
            await run_evaluation(create_sessionmaker(engine), ports, gateway, run_id, ports.clock())
    finally:
        await engine.dispose()


@celery_app.task(name=EVALUATION_RUN_TASK)
def run_evaluation_task(run_id: str) -> None:
    """Answers and judges every case of a queued Run, then completes it."""
    asyncio.run(_run(uuid.UUID(run_id)))


async def enqueue_run(run_id: uuid.UUID) -> None:
    """Sends the task from a thread, as ``enqueue_ingestion`` does."""
    await asyncio.to_thread(run_evaluation_task.delay, str(run_id))
