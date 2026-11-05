"""Signing up at the API seam: a new Member becomes the Owner of a new Organisation."""

from collections.abc import AsyncIterator
from http.cookies import SimpleCookie

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.conftest import TEST_DATABASE_URL, TEST_REDIS_URL, ClientFactory, new_member_details


@pytest.fixture
async def database() -> AsyncIterator[AsyncEngine]:
    """Direct database access, only for state with no API surface."""
    engine = create_async_engine(TEST_DATABASE_URL)
    yield engine
    await engine.dispose()


async def test_sign_up_makes_the_member_owner_of_a_new_organisation_and_signs_them_in(
    client: httpx.AsyncClient,
) -> None:
    details = new_member_details(name="Ada Lovelace", organisation_name="Analytical Engines")

    response = await client.post("/api/auth/sign-up", json=details)

    assert response.status_code == 201
    body = response.json()
    assert body["member"]["name"] == "Ada Lovelace"
    assert body["member"]["email"] == details["email"]
    assert [(o["name"], o["role"]) for o in body["organisations"]] == [
        ("Analytical Engines", "owner")
    ]
    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == body
    organisation_id = body["organisations"][0]["id"]
    organisation = await client.get(f"/api/organisations/{organisation_id}")
    assert organisation.json() == {
        "id": organisation_id,
        "name": "Analytical Engines",
        "role": "owner",
        "require_mfa": False,
    }


async def test_the_session_cookie_is_opaque_http_only_secure_and_same_site_lax(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/api/auth/sign-up", json=new_member_details())

    cookie = SimpleCookie(response.headers["set-cookie"])["studio_session"]
    assert cookie["httponly"] is True
    assert cookie["secure"] is True
    assert cookie["samesite"] == "lax"
    assert cookie["path"] == "/"
    assert int(cookie["max-age"]) == 14 * 24 * 60 * 60
    # Opaque: a random token that carries nothing about the Member.
    assert len(cookie.value) >= 40
    assert response.json()["member"]["id"] not in cookie.value


async def test_sessions_live_in_redis_without_the_cookie_value(
    client: httpx.AsyncClient,
) -> None:
    redis: Redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    before = set(await redis.keys("session:*"))

    response = await client.post("/api/auth/sign-up", json=new_member_details())

    token = response.cookies["studio_session"]
    (key,) = set(await redis.keys("session:*")) - before
    assert token not in key
    assert await redis.get(key) == response.json()["member"]["id"]
    assert 0 < await redis.ttl(key) <= 14 * 24 * 60 * 60
    await redis.aclose()


async def test_passwords_are_stored_only_as_argon2id_hashes(
    client: httpx.AsyncClient, database: AsyncEngine
) -> None:
    details = new_member_details()
    await client.post("/api/auth/sign-up", json=details)

    async with database.connect() as connection:
        stored = await connection.scalar(
            text("SELECT password_hash FROM members WHERE email = :email"),
            {"email": details["email"]},
        )
    assert stored.startswith("$argon2id$")
    assert details["password"] not in stored


async def test_a_taken_email_is_refused_and_nothing_from_that_attempt_is_kept(
    owner_details: dict[str, str], new_client: ClientFactory, database: AsyncEngine
) -> None:
    second = await new_client()
    retry = new_member_details(email=owner_details["email"].upper())

    response = await second.post("/api/auth/sign-up", json=retry)

    assert response.status_code == 409
    assert response.json() == {"detail": "Email already registered"}
    assert "set-cookie" not in response.headers
    # The Organisation is written before the Member, so this shows the transaction rolled back.
    async with database.connect() as connection:
        orphans = await connection.scalar(
            text("SELECT count(*) FROM organisations WHERE name = :name"),
            {"name": retry["organisation_name"]},
        )
    assert orphans == 0
    signed_in = await second.post(
        "/api/auth/sign-in",
        json={"email": owner_details["email"], "password": owner_details["password"]},
    )
    assert [o["name"] for o in signed_in.json()["organisations"]] == [
        owner_details["organisation_name"]
    ]


@pytest.fixture
async def owner_details(client: httpx.AsyncClient) -> dict[str, str]:
    details = new_member_details()
    response = await client.post("/api/auth/sign-up", json=details)
    assert response.status_code == 201
    return details


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "   "),
        ("email", "not-an-email"),
        ("email", "two@@example.test"),
        ("password", "too short"),
        ("password", "x" * 257),
        ("organisation_name", ""),
    ],
)
async def test_sign_up_rejects_invalid_details(
    client: httpx.AsyncClient, field: str, value: str
) -> None:
    response = await client.post("/api/auth/sign-up", json=new_member_details(**{field: value}))

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]
    assert "set-cookie" not in response.headers


async def test_names_and_emails_are_trimmed_and_emails_are_case_insensitive(
    client: httpx.AsyncClient,
) -> None:
    details = new_member_details()
    padded = details | {
        "name": f"  {details['name']} ",
        "email": f" {details['email'].upper()} ",
        "organisation_name": f" {details['organisation_name']}  ",
    }

    body = (await client.post("/api/auth/sign-up", json=padded)).json()

    assert body["member"]["name"] == details["name"]
    assert body["member"]["email"] == details["email"]
    assert body["organisations"][0]["name"] == details["organisation_name"]
