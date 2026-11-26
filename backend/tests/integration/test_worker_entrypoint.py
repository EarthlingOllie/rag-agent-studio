"""The worker and Beat entrypoint validates settings before connecting to the broker."""

import importlib
import subprocess
import sys
from types import ModuleType

import pytest
from celery.signals import worker_process_init, worker_ready

from app.core.settings import SettingsError
from app.documents.ports import current_ports
from app.guardrails.fake import RuleDrivenClassifier
from app.guardrails.local import LoadedModel, LocalClassifier
from app.worker.publisher import CeleryJobPublisher, Job, install_publisher
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


def test_beat_schedules_the_health_check_budget_alert_reset_usage_rollup_purge_and_sweeper(
    settings_env: pytest.MonkeyPatch,
) -> None:
    entrypoint = _import_worker_entrypoint()

    schedule = entrypoint.app.conf.beat_schedule
    assert [entry["task"] for entry in schedule.values()] == [
        "worker.health_check",
        "embed.clear_budget_alerts",
        "analytics.roll_up_usage",
        "retention.purge_expired",
        "jobs.sweep",
    ]
    assert schedule["job-sweeper"]["schedule"] == 60.0
    # The tasks register when the worker loads its includes (not on import, in this process).
    assert {
        "app.embed.tasks",
        "app.analytics.tasks",
        "app.retention.tasks",
        "app.jobs.tasks",
    } <= set(entrypoint.app.conf.include)


def test_celery_takes_one_message_at_a_time_acknowledges_late_and_never_requeues_a_lost_one(
    settings_env: pytest.MonkeyPatch,
) -> None:
    """The sweeper, not the broker, restarts a job whose worker was lost (ADR-0020)."""
    conf = _import_worker_entrypoint().app.conf

    assert conf.worker_prefetch_multiplier == 1
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is False


def test_a_worker_that_starts_sends_the_job_sweeper_once(
    settings_env: pytest.MonkeyPatch,
) -> None:
    _import_worker_entrypoint()
    sent: list[Job] = []

    class Recording(CeleryJobPublisher):
        def send(self, job: Job) -> None:
            sent.append(job)

    install_publisher(Recording())
    try:
        worker_ready.send(sender=None)
    finally:
        install_publisher(CeleryJobPublisher())

    assert [(job.task, job.identifier) for job in sent] == [("jobs.sweep", "")]


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
