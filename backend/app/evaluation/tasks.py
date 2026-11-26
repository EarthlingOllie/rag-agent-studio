"""The Evaluation Run Celery task, which the start endpoint enqueues once the Run is committed, and
the Live Verdict task, which the widget enqueues once a chosen reply's Live Verdict is committed."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable

import httpx2

from app.core.db import create_engine, create_sessionmaker
from app.core.settings import load_settings
from app.evaluation.job import run_evaluation
from app.evaluation.live import judge_live_verdict
from app.evaluation.ports import current_evaluation_ports
from app.worker.celery_app import EVALUATION_RUN_TASK, LIVE_VERDICT_TASK, celery_app
from app.worker.publisher import current_publisher


async def _run(job: Callable[..., Awaitable[None]], row_id: uuid.UUID) -> None:
    settings = load_settings()
    engine = create_engine(settings)
    ports = current_evaluation_ports()
    try:
        async with httpx2.AsyncClient(timeout=settings.model_timeout_seconds) as client:
            gateway = ports.open_gateway(client)
            await job(create_sessionmaker(engine), ports, gateway, row_id, ports.clock())
    finally:
        await engine.dispose()


@celery_app.task(name=EVALUATION_RUN_TASK, ignore_result=True)
def run_evaluation_task(run_id: str) -> None:
    """Answers and judges every case of a queued Run, then completes it."""
    asyncio.run(_run(run_evaluation, uuid.UUID(run_id)))


async def enqueue_run(run_id: uuid.UUID) -> None:
    """Sends the Evaluation Run job through the Job publisher."""
    await current_publisher().run_evaluation(run_id)


@celery_app.task(name=LIVE_VERDICT_TASK, ignore_result=True)
def judge_live_verdict_task(verdict_id: str) -> None:
    """Judges a chosen Visitor reply's pending Live Verdict."""
    asyncio.run(_run(judge_live_verdict, uuid.UUID(verdict_id)))


async def enqueue_live_verdict(verdict_id: uuid.UUID) -> None:
    """Sends the Live Verdict job through the Job publisher."""
    await current_publisher().judge_live_verdict(verdict_id)
