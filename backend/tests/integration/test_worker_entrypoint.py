"""The worker and Beat entrypoint validates settings before connecting to the broker."""

import importlib
import sys
from types import ModuleType

import pytest

from app.core.settings import SettingsError
from tests.conftest import TEST_REDIS_URL


def _import_worker_entrypoint() -> ModuleType:
    sys.modules.pop("app.worker.main", None)
    return importlib.import_module("app.worker.main")


def test_worker_entrypoint_points_celery_at_the_configured_broker(
    settings_env: pytest.MonkeyPatch,
) -> None:
    entrypoint = _import_worker_entrypoint()

    assert entrypoint.app.conf.broker_url == TEST_REDIS_URL
    assert "worker.health_check" in entrypoint.app.tasks
    assert "documents.ingest" in entrypoint.app.tasks


def test_beat_schedules_the_worker_health_check(settings_env: pytest.MonkeyPatch) -> None:
    entrypoint = _import_worker_entrypoint()

    schedule = entrypoint.app.conf.beat_schedule
    assert [entry["task"] for entry in schedule.values()] == ["worker.health_check"]


def test_worker_entrypoint_fails_fast_naming_a_missing_setting(
    settings_env: pytest.MonkeyPatch,
) -> None:
    settings_env.delenv("REDIS_URL")

    with pytest.raises(SettingsError, match=r"REDIS_URL: Field required"):
        _import_worker_entrypoint()
