"""Shared fixtures for the API seam.

Tests talk to the FastAPI app through an in-process async HTTP client, against real
Postgres and Redis (``docker compose up postgres redis`` locally, service containers in CI).
"""

import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from app.main import create_app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://studio:studio@localhost:5432/studio_test"
)
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
BACKEND_ROOT = Path(__file__).resolve().parents[1]
# HTTPS, so the client's cookie jar sends the Secure session cookie back.
BASE_URL = "https://testserver"


def _set_test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("REDIS_URL", TEST_REDIS_URL)
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "true")


@pytest.fixture(scope="session")
def database_schema() -> None:
    """Migrate the test database to head once per run."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        _set_test_environment(monkeypatch)
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.attributes["configure_logger"] = False
        command.upgrade(config, "head")


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """A complete, valid environment; tests tweak it through the returned monkeypatch."""
    _set_test_environment(monkeypatch)
    return monkeypatch


@pytest.fixture
async def app(settings_env: pytest.MonkeyPatch, database_schema: None) -> AsyncIterator[FastAPI]:
    application = create_app()
    async with LifespanManager(application):
        yield application


ClientFactory = Callable[[], Awaitable[httpx.AsyncClient]]


@pytest.fixture
async def new_client(app: FastAPI) -> AsyncIterator[ClientFactory]:
    """Opens another client on the same app, with its own cookie jar (another browser)."""
    async with AsyncExitStack() as stack:

        async def open_client() -> httpx.AsyncClient:
            transport = httpx.ASGITransport(app=app)
            return await stack.enter_async_context(
                httpx.AsyncClient(transport=transport, base_url=BASE_URL)
            )

        yield open_client


@pytest.fixture
async def client(new_client: ClientFactory) -> httpx.AsyncClient:
    return await new_client()


@dataclass(frozen=True)
class SignedUpMember:
    """A Member who signed up, and so owns a new Organisation, and the client signed in as them."""

    client: httpx.AsyncClient
    member_id: str
    name: str
    email: str
    password: str
    organisation_id: str
    organisation_name: str


def new_member_details(**overrides: str) -> dict[str, str]:
    """Sign-up fields for a Member nobody has registered; every call gives a unique email."""
    suffix = uuid.uuid4().hex[:12]
    details = {
        "name": f"Test Member {suffix}",
        "email": f"member-{suffix}@example.test",
        "password": f"correct horse battery {suffix}",
        "organisation_name": f"Organisation {suffix}",
    }
    return details | overrides


TenantFactory = Callable[[], Awaitable[SignedUpMember]]


@pytest.fixture
def tenant_factory(new_client: ClientFactory) -> TenantFactory:
    """Signs up a new Member in a fresh client, giving a new Organisation they own."""

    async def make_tenant() -> SignedUpMember:
        signed_in = await new_client()
        details = new_member_details()
        response = await signed_in.post("/api/auth/sign-up", json=details)
        assert response.status_code == 201, response.text
        body = response.json()
        (organisation,) = body["organisations"]
        return SignedUpMember(
            client=signed_in,
            member_id=body["member"]["id"],
            name=details["name"],
            email=details["email"],
            password=details["password"],
            organisation_id=organisation["id"],
            organisation_name=organisation["name"],
        )

    return make_tenant


@pytest.fixture
async def owner(tenant_factory: TenantFactory) -> SignedUpMember:
    """A signed-in Owner of a new Organisation."""
    return await tenant_factory()
