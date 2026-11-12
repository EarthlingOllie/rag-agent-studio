"""A misconfigured service fails at startup with a message naming the bad setting."""

import pytest
from asgi_lifespan import LifespanManager

from app.core.settings import SettingsError, load_settings
from app.main import create_app


async def test_startup_fails_fast_naming_a_missing_required_setting(
    settings_env: pytest.MonkeyPatch,
) -> None:
    settings_env.delenv("DATABASE_URL")

    with pytest.raises(SettingsError, match=r"DATABASE_URL: Field required"):
        async with LifespanManager(create_app()):
            pass  # startup must not complete


async def test_startup_fails_fast_naming_an_invalid_setting(
    settings_env: pytest.MonkeyPatch,
) -> None:
    settings_env.setenv("REDIS_URL", "not-a-url")
    settings_env.setenv("WORKER_HEALTH_TIMEOUT_SECONDS", "0")

    with pytest.raises(SettingsError) as raised:
        async with LifespanManager(create_app()):
            pass  # startup must not complete

    message = str(raised.value)
    assert message.startswith("Invalid service settings.")
    assert "REDIS_URL" in message
    assert "WORKER_HEALTH_TIMEOUT_SECONDS: Input should be greater than 0" in message


@pytest.mark.parametrize("key", ["not base64!", "c2hvcnQ="])
async def test_startup_fails_fast_on_a_local_key_wrapper_key_that_is_not_32_bytes(
    settings_env: pytest.MonkeyPatch, key: str
) -> None:
    settings_env.setenv("LOCAL_KEY_WRAPPER_KEY", key)

    with pytest.raises(
        SettingsError, match=r"LOCAL_KEY_WRAPPER_KEY: Value error, must be 32 bytes"
    ):
        async with LifespanManager(create_app()):
            pass  # startup must not complete


async def test_startup_fails_fast_on_a_trusted_proxy_that_is_not_an_address(
    settings_env: pytest.MonkeyPatch,
) -> None:
    settings_env.setenv("TRUSTED_PROXIES", "10.0.0.0/16, the-load-balancer")

    with pytest.raises(
        SettingsError,
        match=r"TRUSTED_PROXIES: Value error, 'the-load-balancer' isn't an IP address or network",
    ):
        async with LifespanManager(create_app()):
            pass  # startup must not complete


# The LOCAL_KEY_WRAPPER_KEY that docker-compose.yml falls back to: it is public, so anyone could
# forge widget tokens and unwrap secrets with it (WID-R2-F1).
COMMITTED_DEFAULT_KEY = "bG9jYWwtZGV2LW9ubHkta2V5LW5vdC1hLXNlY3JldCE="


@pytest.mark.parametrize("environment", ["demo", "production"])
async def test_startup_refuses_the_committed_default_key_outside_local_and_test(
    settings_env: pytest.MonkeyPatch, environment: str
) -> None:
    settings_env.setenv("ENVIRONMENT", environment)
    settings_env.setenv("LOCAL_KEY_WRAPPER_KEY", COMMITTED_DEFAULT_KEY)

    with pytest.raises(
        SettingsError, match=r"LOCAL_KEY_WRAPPER_KEY is the public development default"
    ):
        async with LifespanManager(create_app()):
            pass  # startup must not complete


@pytest.mark.parametrize("environment", ["local", "test"])
def test_the_committed_default_key_is_allowed_locally(
    settings_env: pytest.MonkeyPatch, environment: str
) -> None:
    settings_env.setenv("ENVIRONMENT", environment)
    settings_env.setenv("LOCAL_KEY_WRAPPER_KEY", COMMITTED_DEFAULT_KEY)

    assert load_settings().environment == environment
