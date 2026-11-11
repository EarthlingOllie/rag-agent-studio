"""Structured logging: every service writes one JSON object per line to stdout.

Each entry carries the service name and, inside a traced operation, the trace and span IDs, so
logs can be joined to traces. Extra fields with sensitive names are redacted, using the same
Message-field names as telemetry scrubbing plus common secret names, and so are the task
arguments and results that Celery logs.
"""

import json
import logging
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, TextIO

import onnxruntime
from opentelemetry import trace

from app.core.telemetry import MESSAGE_FIELD_PATTERN

REDACTED = "[Redacted]"

_SENSITIVE_FIELD = re.compile(
    r"password|passwd|secret|auth(?!ors?\b)|credential|private[._ -]?key|api[._ -]?key"
    rf"|session|cookie|token|{MESSAGE_FIELD_PATTERN}",
    re.IGNORECASE,
)
# Celery logs each task's arguments and return value, which may carry Message text.
_TASK_PAYLOAD_FIELDS = frozenset({"args", "kwargs", "argsrepr", "kwargsrepr", "return_value"})
# Attributes every LogRecord has; anything else on a record came from ``extra``. Uvicorn's
# ``color_message`` repeats the message with terminal colour codes, so it is dropped too.
_RECORD_ATTRIBUTES = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "color_message"}
# Servers that install their own handlers; their records go through the root handler instead.
_SERVER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "celery")


def _redact(key: str, value: Any) -> Any:
    if key in _TASK_PAYLOAD_FIELDS or _SENSITIVE_FIELD.search(key):
        return REDACTED
    if isinstance(value, Mapping):
        return {k: _redact(str(k), v) for k, v in value.items()}
    return value


def _message(record: logging.LogRecord) -> str:
    """The formatted message, with sensitive values left out of mapping-style arguments."""
    if isinstance(record.args, Mapping):
        return str(record.msg) % dict(_redact("", record.args))
    return record.getMessage()


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _message(record),
            "service": self.service,
        }
        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            entry["trace_id"] = format(span_context.trace_id, "032x")
            entry["span_id"] = format(span_context.span_id, "016x")
        for key, value in vars(record).items():
            if key not in _RECORD_ATTRIBUTES and not key.startswith("_"):
                entry[key] = _redact(key, value)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class _StdoutHandler(logging.StreamHandler[TextIO]):
    """Writes to whatever ``sys.stdout`` is at the time, so a swapped stream is followed."""

    @property
    def stream(self) -> TextIO:
        return sys.stdout

    @stream.setter
    def stream(self, _: TextIO) -> None:
        """StreamHandler assigns its stream on construction; the property ignores it."""


def configure_logging(service: str, level: int = logging.INFO) -> None:
    """Send all logging, including server and warnings output, to stdout as JSON lines."""
    root = logging.getLogger()
    for handler in [h for h in root.handlers if isinstance(h, _StdoutHandler)]:
        root.removeHandler(handler)
    handler = _StdoutHandler()
    handler.setFormatter(JsonFormatter(service))
    root.addHandler(handler)
    root.setLevel(level)
    for name in _SERVER_LOGGERS:
        server_logger = logging.getLogger(name)
        server_logger.handlers.clear()
        server_logger.propagate = True
    logging.captureWarnings(True)
    # ONNX Runtime (the local classifier, Embedding Model and OCR) logs from C++ straight to
    # stderr, so its warnings would not be JSON; keep it to errors (3: ERROR).
    onnxruntime.set_default_logger_severity(3)
