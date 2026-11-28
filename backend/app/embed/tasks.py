"""The embed's Beat tasks.

- Hourly: a new UTC date starts a new Token Budget and a new Call minutes counter (both are
  keyed by date), so the alert flags raised before it are cleared. Keyed on the UTC date, the
  first run after midnight resets the day that ended, even when Beat missed midnight itself.
- Every 15 seconds: Calls that reached their Maximum Call length or have had no turn for a
  minute are ended (``app.embed.call_limits``).
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import create_engine, create_sessionmaker
from app.core.settings import load_settings
from app.embed import call_limits, service
from app.worker.celery_app import CLEAR_BUDGET_ALERTS_TASK, END_IDLE_CALLS_TASK, celery_app


async def _run(job: Callable[[AsyncSession], Awaitable[int]]) -> int:
    engine = create_engine(load_settings())
    try:
        async with create_sessionmaker(engine)() as session:
            return await job(session)
    finally:
        await engine.dispose()


def _moment(now: str | None) -> datetime:
    return datetime.now(UTC) if now is None else datetime.fromisoformat(now)


@celery_app.task(name=CLEAR_BUDGET_ALERTS_TASK)
def clear_budget_alerts(now: str | None = None) -> int:
    """Clears every Agent's budget alerts raised before today (UTC); Beat runs it hourly, on the
    hour. ``now`` (ISO 8601) stands in for the system clock. Returns how many it cleared."""
    moment = _moment(now)
    return asyncio.run(_run(lambda session: service.clear_budget_alerts(session, now=moment)))


@celery_app.task(name=END_IDLE_CALLS_TASK)
def end_idle_calls(now: str | None = None) -> int:
    """Ends the Calls past their Maximum Call length or silent for a minute; Beat runs it every
    15 seconds. ``now`` (ISO 8601) stands in for the system clock. Returns how many it ended."""
    moment = _moment(now)
    return asyncio.run(_run(lambda session: call_limits.end_idle_calls(session, now=moment)))
