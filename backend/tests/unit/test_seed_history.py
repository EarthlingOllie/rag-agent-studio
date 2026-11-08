"""The seeded history's clock and its wait for ingestion (ticket 10-02)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.seed.client import SeedError
from app.seed.history import ShiftedClock, history_start, wait_for_documents


def test_the_shifted_clock_runs_from_the_past_and_only_goes_forward() -> None:
    past = datetime.now(UTC) - timedelta(days=10)
    clock = ShiftedClock(past)

    assert timedelta(0) <= clock.now() - past < timedelta(seconds=5)
    clock.travel_to(past + timedelta(days=2))
    assert timedelta(0) <= clock.now() - (past + timedelta(days=2)) < timedelta(seconds=5)
    clock.travel_to(past)  # already passed: stays put
    assert clock.now() >= past + timedelta(days=2)


def test_the_history_starts_early_four_weeks_ago() -> None:
    now = datetime(2026, 11, 8, 15, 30, tzinfo=UTC)

    assert history_start(now) == datetime(2026, 10, 11, 6, 0, tzinfo=UTC)


class ScriptedApi:
    """Answers the Documents list with each status set in turn, the last one forever."""

    def __init__(self, *statuses: set[str]) -> None:
        self.statuses = list(statuses)
        self.organisation = "org"

    def path(self, *parts: str) -> str:
        return "/".join(parts)

    async def call(self, method: str, path: str) -> Any:
        found = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return [{"status": status} for status in found]


async def test_the_history_waits_for_the_documents_to_be_ready() -> None:
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    api: Any = ScriptedApi({"queued", "ready"}, {"processing"}, {"ready"})
    await wait_for_documents(api, "p", sleep=sleep, interval=0.5)

    assert slept == [0.5, 0.5]


async def test_a_failed_document_stops_the_history() -> None:
    api: Any = ScriptedApi({"processing", "failed"})

    with pytest.raises(SeedError, match="failed ingestion"):
        await wait_for_documents(api, "p")


async def test_documents_that_never_get_ready_stop_the_history() -> None:
    async def sleep(seconds: float) -> None:
        pass

    api: Any = ScriptedApi({"processing"})

    with pytest.raises(SeedError, match=r"weren't ready in time\. Is the worker running"):
        await wait_for_documents(api, "p", attempts=3, sleep=sleep)
