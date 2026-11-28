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


# --- The job queues (ticket 22-03) --------------------------------------------------------------


@pytest.mark.parametrize("setting", ["GENERAL_QUEUE_NAME", "RUNS_QUEUE_URL"])
async def test_startup_fails_fast_without_a_queue_setting_and_never_falls_back_to_redis(
    settings_env: pytest.MonkeyPatch, setting: str
) -> None:
    # Redis is configured, but it is not a broker: without both queues the service won't start.
    settings_env.delenv(setting)

    with pytest.raises(SettingsError, match=rf"{setting}: Field required"):
        async with LifespanManager(create_app()):
            pass  # startup must not complete


async def test_startup_fails_fast_on_a_queue_name_sqs_would_refuse(
    settings_env: pytest.MonkeyPatch,
) -> None:
    settings_env.setenv("RUNS_QUEUE_NAME", "runs queue!")

    with pytest.raises(SettingsError, match=r"RUNS_QUEUE_NAME: String should match pattern"):
        async with LifespanManager(create_app()):
            pass  # startup must not complete


async def test_startup_fails_fast_when_a_queue_url_is_not_its_queues(
    settings_env: pytest.MonkeyPatch,
) -> None:
    settings_env.setenv("GENERAL_QUEUE_URL", "http://localhost:4566/000000000000/another-queue")

    with pytest.raises(
        SettingsError, match=r"GENERAL_QUEUE_URL must be the URL of GENERAL_QUEUE_NAME"
    ):
        async with LifespanManager(create_app()):
            pass  # startup must not complete


async def test_startup_fails_fast_when_both_queue_settings_name_one_queue(
    settings_env: pytest.MonkeyPatch,
) -> None:
    settings_env.setenv("RUNS_QUEUE_NAME", "studio-jobs")
    settings_env.setenv("RUNS_QUEUE_URL", "http://localhost:4566/000000000000/studio-jobs")
    settings_env.setenv("GENERAL_QUEUE_NAME", "studio-jobs")
    settings_env.setenv("GENERAL_QUEUE_URL", "http://localhost:4566/000000000000/studio-jobs")

    with pytest.raises(SettingsError, match=r"must name two queues"):
        async with LifespanManager(create_app()):
            pass  # startup must not complete


async def test_startup_fails_fast_on_a_retry_backoff_longer_than_five_minutes(
    settings_env: pytest.MonkeyPatch,
) -> None:
    settings_env.setenv("INGESTION_RETRY_MAX_SECONDS", "301")

    with pytest.raises(
        SettingsError, match=r"INGESTION_RETRY_MAX_SECONDS: Input should be less than or equal"
    ):
        async with LifespanManager(create_app()):
            pass  # startup must not complete
