"""Shared fixtures for the API seam.

Tests talk to the FastAPI app through an in-process async HTTP client, against real
Postgres and Redis (``docker compose up postgres redis`` locally, service containers in CI).
"""

import base64
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, replace
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from app.core.clock import Clock
from app.mail.outbox import OutboxMailer
from app.main import create_app
from tests.fakes.clock import ControllableClock

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://studio:studio@localhost:5432/studio_test"
)
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
# 32 bytes, base64: the local static-key wrapper's key for the test run.
TEST_LOCAL_KEY_WRAPPER_KEY = base64.b64encode(b"test-only-local-key-wrapper-key!").decode()
BACKEND_ROOT = Path(__file__).resolve().parents[1]
# HTTPS, so the client's cookie jar sends the Secure session cookie back.
BASE_URL = "https://testserver"
# Where links in emails point.
STUDIO_URL = "https://studio.example.test"


def _set_test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("REDIS_URL", TEST_REDIS_URL)
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "true")
    monkeypatch.setenv("LOCAL_KEY_WRAPPER_KEY", TEST_LOCAL_KEY_WRAPPER_KEY)
    monkeypatch.setenv("MAILER", "outbox")
    monkeypatch.setenv("STUDIO_URL", STUDIO_URL)


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
        # Sign-in failure counters live in the shared test Redis; each test starts without any.
        redis = application.state.redis
        async for key in redis.scan_iter(match="sign-in-failures:*"):
            await redis.delete(key)
        yield application


@pytest.fixture
def clock(app: FastAPI) -> ControllableClock:
    """Replaces the app's system clock with one the test moves forward by hand."""
    controllable = ControllableClock()
    app.state.clock = controllable
    return controllable


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


@pytest.fixture
def outbox(app: FastAPI) -> OutboxMailer:
    """The in-memory mailer the app sends through in tests; read sent emails from it."""
    mailer = app.state.mailer
    assert isinstance(mailer, OutboxMailer)
    return mailer


def _clock_is_a_clock(clock: ControllableClock) -> Clock:
    return clock  # mypy checks the fake satisfies the port


MemberFactory = Callable[[SignedUpMember, str], Awaitable[SignedUpMember]]


@pytest.fixture
def member_factory(tenant_factory: TenantFactory) -> MemberFactory:
    """Adds a new signed-in Member to the Owner's Organisation with a role, through an invite.

    The new Member also owns the Organisation they signed up with; the returned
    ``organisation_id`` and ``organisation_name`` are the Owner's.
    """

    async def join(owner: SignedUpMember, role: str) -> SignedUpMember:
        joiner = await tenant_factory()
        await join_organisation(owner, joiner, role)
        return replace(
            joiner,
            organisation_id=owner.organisation_id,
            organisation_name=owner.organisation_name,
        )

    return join


async def join_organisation(owner: SignedUpMember, member: SignedUpMember, role: str) -> None:
    """Brings an existing Member into the Owner's Organisation through an accepted invite link."""
    invited = await owner.client.post(
        f"/api/organisations/{owner.organisation_id}/invites",
        json={"email": member.email, "role": role, "send_email": False},
    )
    assert invited.status_code == 201, invited.text
    token = invited.json()["link"].split("token=", 1)[1]
    accepted = await member.client.post("/api/invites/accept", json={"token": token})
    assert accepted.status_code == 200, accepted.text
