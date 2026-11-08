"""The retention purge Beat task: daily, after the usage rollup has finalised the previous day,
it purges Message text and feedback comments older than each Organisation's Retention Window
(``app.retention.service``)."""

import asyncio
from datetime import datetime

from app.core.clock import SystemClock
from app.core.db import create_engine, create_sessionmaker
from app.core.settings import load_settings
from app.retention.service import purge_expired as purge
from app.worker.celery_app import PURGE_TASK, celery_app


async def _purge(at: datetime) -> int:
    engine = create_engine(load_settings())
    try:
        return await purge(create_sessionmaker(engine), at)
    finally:
        await engine.dispose()


def _as_of(at: str) -> datetime:
    parsed = datetime.fromisoformat(at)
    if parsed.tzinfo is None:
        raise ValueError(f"The purge time {at!r} needs its UTC offset")
    return parsed


@celery_app.task(name=PURGE_TASK)
def purge_expired(at: str | None = None) -> int:
    """Purges as of now, or as of ``at`` (an ISO 8601 time with its offset; one without is
    refused), to redo a run by hand. Returns how many Messages were purged."""
    return asyncio.run(_purge(SystemClock().now() if at is None else _as_of(at)))
