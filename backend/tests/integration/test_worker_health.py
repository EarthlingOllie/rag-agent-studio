"""Task seam: the API enqueues the Celery health task and waits for the worker's reply."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta

import httpx
import pytest
import redis
from asgi_lifespan import LifespanManager
from celery.contrib.testing.worker import start_worker
from fastapi import FastAPI

from app.main import create_app
from app.worker.celery_app import HEALTH_CHECK_TASK, celery_app
from tests.conftest import TEST_REDIS_URL
from tests.fakes.clock import ControllableClock


@pytest.fixture(autouse=True)
def empty_broker() -> Iterator[None]:
    """Unanswered health tasks must not leak into the next test's queue."""
    yield
    with redis.Redis.from_url(TEST_REDIS_URL) as connection:
        connection.flushdb()


@pytest.fixture
async def broker_client(settings_env: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    """An API client whose health task goes through the Redis broker instead of running eagerly."""
    settings_env.setenv("CELERY_TASK_ALWAYS_EAGER", "false")
    settings_env.setenv("WORKER_HEALTH_TIMEOUT_SECONDS", "0.5")
    application = create_app()
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


async def test_worker_health_completes_a_round_trip_when_tasks_run_eagerly(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/health/worker")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "reply": "pong"}


async def test_worker_health_completes_a_round_trip_through_a_running_worker(
    broker_client: httpx.AsyncClient,
) -> None:
    with start_worker(celery_app, pool="solo", perform_ping_check=False, shutdown_timeout=10):
        response = await broker_client.get("/api/health/worker")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "reply": "pong"}


async def test_worker_health_is_unavailable_when_no_worker_replies(
    broker_client: httpx.AsyncClient,
) -> None:
    response = await broker_client.get("/api/health/worker")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "reply": None}


async def test_worker_health_is_unavailable_when_the_health_task_fails(
    broker_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_health_check() -> str:
        raise RuntimeError("worker is broken")

    monkeypatch.setattr(celery_app.tasks[HEALTH_CHECK_TASK], "run", failing_health_check)
    with start_worker(celery_app, pool="solo", perform_ping_check=False, shutdown_timeout=10):
        response = await broker_client.get("/api/health/worker")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "reply": None}


def queued_health_tasks() -> int:
    """How many health tasks wait in the broker's default queue for a worker."""
    with redis.Redis.from_url(TEST_REDIS_URL) as connection:
        return int(connection.llen("celery"))


async def test_concurrent_anonymous_calls_share_one_health_task(
    broker_client: httpx.AsyncClient,
) -> None:
    """The route is unauthenticated: callers must not be able to flood the queue (AUTH-F2)."""
    responses = await asyncio.gather(*(broker_client.get("/api/health/worker") for _ in range(5)))

    assert [response.status_code for response in responses] == [503] * 5
    assert queued_health_tasks() == 1


async def test_a_recent_answer_is_reused_until_it_is_stale(
    app: FastAPI, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = ControllableClock()
    app.state.clock = clock
    runs: list[None] = []

    def counting_health_check() -> str:
        runs.append(None)
        return "pong"

    monkeypatch.setattr(celery_app.tasks[HEALTH_CHECK_TASK], "run", counting_health_check)
    for _ in range(3):
        assert (await client.get("/api/health/worker")).json() == {"status": "ok", "reply": "pong"}
    assert len(runs) == 1

    clock.advance(timedelta(seconds=4))
    await client.get("/api/health/worker")
    assert len(runs) == 1
    clock.advance(timedelta(seconds=1))
    await client.get("/api/health/worker")
    assert len(runs) == 2
