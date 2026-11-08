"""The usage rollup Beat task: hourly, it recomputes the current UTC day's ``usage_daily``
rollups, finalises the days before it, and checks each Agent's block rate for a spike
(``app.analytics.rollup``)."""

import asyncio
from datetime import datetime

from app.analytics.rollup import roll_up
from app.core.clock import SystemClock
from app.core.db import create_engine, create_sessionmaker
from app.core.settings import load_settings
from app.mail.factory import build_mailer
from app.worker.celery_app import ROLL_UP_TASK, celery_app


async def _roll_up(at: datetime) -> None:
    settings = load_settings()
    engine = create_engine(settings)
    try:
        await roll_up(
            create_sessionmaker(engine),
            at,
            mailer=build_mailer(settings),
            studio_url=str(settings.studio_url),
        )
    finally:
        await engine.dispose()


@celery_app.task(name=ROLL_UP_TASK)
def roll_up_usage(at: str | None = None) -> None:
    """Rolls usage up as of now, or as of ``at`` (an ISO 8601 time with its offset), to redo a
    run by hand."""
    asyncio.run(_roll_up(SystemClock().now() if at is None else datetime.fromisoformat(at)))
