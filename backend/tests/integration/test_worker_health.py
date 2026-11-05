"""Task seam: the API enqueues the Celery health task and waits for the worker's reply."""

from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import redis
from asgi_lifespan import LifespanManager
from celery.contrib.testing.worker import start_worker

from app.main import create_app
from app.worker.celery_app import HEALTH_CHECK_TASK, celery_app
from tests.conftest import TEST_REDIS_URL


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
