"""The job sweeper task (ADR-0020): Beat runs it every minute, and each worker sends it once as
it starts. It sweeps every job type's rows (``app.jobs.reliability.sweep``), then sends the alert
emails raised and not yet sent (``app.alert_emails``)."""

import asyncio
from datetime import datetime

from app.alert_emails.delivery import send_alert_emails
from app.core.clock import SystemClock
from app.core.db import create_engine, create_sessionmaker
from app.core.settings import load_settings
from app.documents.jobs import INGESTION
from app.jobs.reliability import JobPolicy, Timings, sweep
from app.mail.factory import build_mailer
from app.worker.celery_app import SWEEP_TASK, celery_app

# Every job type the sweeper looks after.
POLICIES: tuple[JobPolicy, ...] = (INGESTION,)


async def _sweep(at: datetime) -> int | None:
    settings = load_settings()
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    try:
        recoveries = await sweep(
            sessionmaker,
            POLICIES,
            now=at,
            timings=Timings.from_settings(settings),
        )
        async with sessionmaker() as session:
            await send_alert_emails(session, build_mailer(settings), now=at)
    finally:
        await engine.dispose()
    return None if recoveries is None else len(recoveries)


@celery_app.task(name=SWEEP_TASK, ignore_result=True)
def sweep_jobs(at: str | None = None) -> int | None:
    """Sweeps as of now, or as of ``at`` (an ISO 8601 time with its offset). Returns how many
    jobs it recovered, or ``None`` when another sweep was already running."""
    return asyncio.run(_sweep(SystemClock().now() if at is None else datetime.fromisoformat(at)))
