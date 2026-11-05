"""The worker and Beat entrypoint validates settings before connecting to the broker."""

import importlib
import subprocess
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


def test_the_worker_knows_every_table_its_tasks_write_to() -> None:
    """The worker imports only its tasks, not the API's routers, so the models those tasks use
    must bring in every table their foreign keys point at."""
    check = (
        "import app.documents.tasks\n"
        "from app.core.db import Base\n"
        "for table in Base.metadata.tables.values():\n"
        "    for key in table.foreign_keys:\n"
        "        key.column\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", check], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
