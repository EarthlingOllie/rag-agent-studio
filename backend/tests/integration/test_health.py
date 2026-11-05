import httpx
import pytest
from asgi_lifespan import LifespanManager

from app.main import create_app


async def test_health_reports_ok_when_database_and_redis_are_reachable(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "redis": "ok"},
    }


async def _get_health_with(settings_env: pytest.MonkeyPatch, name: str, url: str) -> httpx.Response:
    settings_env.setenv(name, url)
    application = create_app()
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.get("/api/health")


async def test_health_is_unavailable_when_the_database_is_unreachable(
    settings_env: pytest.MonkeyPatch,
) -> None:
    response = await _get_health_with(
        settings_env, "DATABASE_URL", "postgresql+asyncpg://studio:studio@127.0.0.1:1/studio"
    )

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "checks": {"database": "error", "redis": "ok"},
    }


async def test_health_is_unavailable_when_redis_is_unreachable(
    settings_env: pytest.MonkeyPatch,
) -> None:
    response = await _get_health_with(settings_env, "REDIS_URL", "redis://127.0.0.1:1/0")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "checks": {"database": "ok", "redis": "error"},
    }
