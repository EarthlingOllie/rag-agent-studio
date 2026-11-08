"""The Token Budget's midnight job, a Celery Beat task: a new UTC date starts a new budget (its
counter is keyed by date), so the alert flags raised for the day before are cleared."""

import asyncio
from datetime import UTC, datetime

from app.core.db import create_engine, create_sessionmaker
from app.core.settings import load_settings
from app.embed import service
from app.worker.celery_app import CLEAR_BUDGET_ALERTS_TASK, celery_app


async def _clear(now: datetime) -> int:
    engine = create_engine(load_settings())
    try:
        async with create_sessionmaker(engine)() as session:
            return await service.clear_budget_alerts(session, now=now)
    finally:
        await engine.dispose()


@celery_app.task(name=CLEAR_BUDGET_ALERTS_TASK)
def clear_budget_alerts(now: str | None = None) -> int:
    """Clears every Agent's budget alert raised before today (UTC); Beat runs it at midnight
    UTC. ``now`` (ISO 8601) stands in for the system clock. Returns how many it cleared."""
    moment = datetime.now(UTC) if now is None else datetime.fromisoformat(now)
    return asyncio.run(_clear(moment))
