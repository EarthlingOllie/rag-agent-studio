"""A misconfigured service fails at startup with a message naming the bad setting."""

import pytest
from asgi_lifespan import LifespanManager

from app.core.settings import SettingsError
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
