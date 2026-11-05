"""Worker and Beat entrypoint: `celery -A app.worker.main worker|beat`.

Settings are validated on import, so a misconfigured worker exits before it connects. Logging
and telemetry are configured here too, under the service name of the command being run.
"""

import sys
from typing import Any

from celery.signals import setup_logging

from app.core.logs import configure_logging
from app.core.settings import load_settings
from app.core.telemetry import configure_telemetry
from app.worker.celery_app import configure_celery

SERVICE_NAME = "beat" if "beat" in sys.argv else "worker"

configure_logging(SERVICE_NAME)
settings = load_settings()
configure_telemetry(settings, SERVICE_NAME)
app = configure_celery(settings)


@setup_logging.connect(weak=False, dispatch_uid="app.worker.main.setup_logging")
def _keep_json_logging(**_: Any) -> None:
    """Connecting this receiver stops Celery installing its own text log handlers."""
