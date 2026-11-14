"""Worker and Beat entrypoint: `celery -A app.worker.main worker|beat`.

Settings are validated on import, so a misconfigured worker exits before it connects. Logging
and telemetry are configured here too, under the service name of the command being run.
"""

import sys
from typing import Any

from celery.signals import setup_logging, worker_process_init

from app.core.clock import SystemClock
from app.core.logs import configure_logging
from app.core.settings import load_settings
from app.core.telemetry import configure_telemetry
from app.crypto.adapters import build_envelope
from app.documents.ports import build_ports, current_ports, install_ports, warm_up
from app.evaluation.ports import EvaluationPorts, install_evaluation_ports
from app.gateway.adapters import build_model_gateway
from app.guardrails.pipeline import build_pipeline
from app.worker.celery_app import configure_celery

SERVICE_NAME = "beat" if "beat" in sys.argv else "worker"

configure_logging(SERVICE_NAME)
settings = load_settings()
configure_telemetry(settings, SERVICE_NAME)
app = configure_celery(settings)
# The adapters ingestion runs through, chosen by the settings.
envelope = build_envelope(settings)
install_ports(build_ports(settings, envelope))
# What Evaluation Runs answer and judge through: the gateway, Guardrails and local embedders.
install_evaluation_ports(
    EvaluationPorts(
        open_gateway=lambda client: build_model_gateway(settings, envelope, client),
        guardrails=build_pipeline(settings),
        embedders=current_ports().embedders,
        judge_timeout_s=settings.evaluation_judge_timeout_s,
        clock=SystemClock,
    )
)


@setup_logging.connect(weak=False, dispatch_uid="app.worker.main.setup_logging")
def _keep_json_logging(**_: Any) -> None:
    """Connecting this receiver stops Celery installing its own text log handlers."""


@worker_process_init.connect(weak=False, dispatch_uid="app.worker.main.warm_up")
def _warm_up(**_: Any) -> None:
    """Each worker process loads the ingestion scan's local model as it starts (after the fork:
    an ONNX Runtime session isn't fork-safe), not in the middle of its first ingestion."""
    warm_up(current_ports())
