"""In AWS the connection URLs arrive in parts (spec 09, ticket 09-06).

ECS injects the database password and Redis AUTH token from Secrets Manager as their own
variables, next to the plain host, port and name, so the settings put the URLs together.
"""

import base64

import pytest

from app.core.settings import SettingsError, load_settings

KEY = base64.b64encode(b"unit-test-local-key-wrapper-key!").decode()
PARTS = (
    "DATABASE_URL",
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_NAME",
    "DATABASE_USER",
    "DATABASE_PASSWORD",
    "DATABASE_TLS",
    "REDIS_URL",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_TLS",
    "REDIS_AUTH_TOKEN",
)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in PARTS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LOCAL_KEY_WRAPPER_KEY", KEY)
    monkeypatch.setenv("DATABASE_HOST", "db.internal.example")
    monkeypatch.setenv("DATABASE_PORT", "5432")
    monkeypatch.setenv("DATABASE_NAME", "studio")
    monkeypatch.setenv("DATABASE_USER", "studio")
    monkeypatch.setenv("REDIS_HOST", "cache.internal.example")
    monkeypatch.setenv("REDIS_PORT", "6379")
    return monkeypatch


def test_the_database_url_is_built_from_its_parts_with_the_password_escaped(
    env: pytest.MonkeyPatch,
) -> None:
    env.setenv("DATABASE_PASSWORD", "p@ss/w:rd?#")
    env.setenv("DATABASE_TLS", "true")

    settings = load_settings()

    assert str(settings.database_url) == (
        "postgresql+asyncpg://studio:p%40ss%2Fw%3Ard%3F%23@db.internal.example:5432/studio"
        "?ssl=require"
    )


def test_the_database_url_without_a_password_or_tls(env: pytest.MonkeyPatch) -> None:
    assert str(load_settings().database_url) == (
        "postgresql+asyncpg://studio@db.internal.example:5432/studio"
    )


def test_the_redis_url_is_built_from_its_parts_over_tls_with_the_auth_token(
    env: pytest.MonkeyPatch,
) -> None:
    env.setenv("REDIS_TLS", "true")
    env.setenv("REDIS_AUTH_TOKEN", "tok/en+1")

    assert str(load_settings().redis_url) == (
        "rediss://:tok%2Fen%2B1@cache.internal.example:6379/0?ssl_cert_reqs=required"
    )


def test_the_redis_url_without_a_token_or_tls(env: pytest.MonkeyPatch) -> None:
    env.setenv("REDIS_TLS", "false")

    assert str(load_settings().redis_url) == "redis://cache.internal.example:6379/0"


def test_a_whole_url_wins_over_parts(env: pytest.MonkeyPatch) -> None:
    env.setenv("DATABASE_URL", "postgresql+asyncpg://a:b@elsewhere:5433/other")
    env.setenv("REDIS_URL", "redis://elsewhere:6380/1")

    settings = load_settings()

    assert str(settings.database_url) == "postgresql+asyncpg://a:b@elsewhere:5433/other"
    assert str(settings.redis_url) == "redis://elsewhere:6380/1"


def test_without_a_url_or_a_host_the_url_is_still_required(env: pytest.MonkeyPatch) -> None:
    env.delenv("DATABASE_HOST")
    env.delenv("REDIS_HOST")

    with pytest.raises(SettingsError) as raised:
        load_settings()

    assert "DATABASE_URL: Field required" in str(raised.value)
    assert "REDIS_URL: Field required" in str(raised.value)


def test_a_host_without_a_name_or_user_is_reported(env: pytest.MonkeyPatch) -> None:
    env.delenv("DATABASE_NAME")
    env.delenv("DATABASE_USER")

    with pytest.raises(
        SettingsError, match="DATABASE_HOST is set, so DATABASE_NAME and DATABASE_USER"
    ):
        load_settings()
