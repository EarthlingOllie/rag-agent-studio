"""The worker and Beat entrypoint validates settings before connecting to the broker."""

import importlib
import subprocess
import sys
from types import ModuleType

import pytest
from celery.signals import worker_process_init

from app.core.settings import SettingsError
from app.documents.ports import current_ports
from app.guardrails.fake import RuleDrivenClassifier
from app.guardrails.local import LoadedModel, LocalClassifier
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


def test_beat_schedules_the_worker_health_check_and_the_budget_alert_reset(
    settings_env: pytest.MonkeyPatch,
) -> None:
    entrypoint = _import_worker_entrypoint()

    schedule = entrypoint.app.conf.beat_schedule
    assert [entry["task"] for entry in schedule.values()] == [
        "worker.health_check",
        "embed.clear_budget_alerts",
    ]
    assert "embed.clear_budget_alerts" in entrypoint.app.tasks


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


def test_each_worker_process_loads_the_scans_local_model_when_it_starts(
    settings_env: pytest.MonkeyPatch,
) -> None:
    """So the first Document a worker process ingests doesn't wait for the model, and the load
    happens when the worker starts rather than mid-ingestion."""
    _import_worker_entrypoint()
    loads: list[int] = []

    def load() -> LoadedModel:
        loads.append(1)
        return LoadedModel(
            session=None,  # type: ignore[arg-type]
            tokenize=lambda text: [],
            cls_id=0,
            sep_id=1,
            injection_index=1,
            max_tokens=8,
        )

    settings_env.setattr(current_ports(), "classifier", LocalClassifier(load, 0.5))

    worker_process_init.send(sender=None)

    assert loads == [1]


def test_a_worker_with_another_scan_classifier_has_nothing_to_load(
    settings_env: pytest.MonkeyPatch,
) -> None:
    _import_worker_entrypoint()
    # The tests' rule-driven fake: nothing to load, and starting a process still works.
    assert isinstance(current_ports().classifier, RuleDrivenClassifier)

    worker_process_init.send(sender=None)
