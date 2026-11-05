"""Every service writes one JSON object per log line, correlated with the active trace, with
sensitive extra fields redacted."""

import json
import logging
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import redis
from asgi_lifespan import LifespanManager
from celery.contrib.testing.worker import start_worker
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.main import create_app
from app.worker.celery_app import celery_app
from tests.conftest import TEST_DATABASE_URL, TEST_REDIS_URL

BACKEND_ROOT = Path(__file__).resolve().parents[2]
MESSAGE_TEXT = "please cancel my order 8812"
API_KEY = "api-key-0b7e"


# Celery writes this notice straight to the process's stdout when it receives SIGTERM,
# bypassing logging, so it is the one line that cannot be JSON.
CELERY_SIGNAL_NOTICE = "worker: Warm shutdown (MainProcess)"


def _json_lines(output: str) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in output.splitlines()
        if line.strip() and line != CELERY_SIGNAL_NOTICE
    ]


async def test_api_logs_are_json_and_carry_the_request_trace(
    settings_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings_env.setenv("DATABASE_URL", "postgresql+asyncpg://studio:studio@127.0.0.1:1/studio")
    exporter = InMemorySpanExporter()
    application = create_app(extra_span_processors=[SimpleSpanProcessor(exporter)])
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/health")

    assert response.status_code == 503
    logs = [entry for entry in _json_lines(capsys.readouterr().out) if "level" in entry]
    started = next(entry for entry in logs if entry["message"] == "API started")
    assert started["service"] == "api"
    assert started["level"] == "INFO"
    failure = next(entry for entry in logs if entry["message"] == "Database health check failed")
    assert failure["level"] == "WARNING"
    assert failure["logger"] == "app.api.health"
    assert failure["error"] == "ConnectionRefusedError"
    request = next(s for s in exporter.get_finished_spans() if s.name == "GET /api/health")
    assert failure["trace_id"] == format(request.context.trace_id, "032x")
    assert len(failure["span_id"]) == 16


async def test_sensitive_log_fields_are_redacted_and_exceptions_are_kept(
    settings_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    application = create_app()
    logger = logging.getLogger("app.test.chat")

    @application.post("/test/messages")
    async def receive_message() -> dict[str, str]:
        logger.info(
            "Visitor message received",
            extra={"content": MESSAGE_TEXT, "provider_api_key": API_KEY, "turns": 3},
        )
        try:
            raise ValueError("the model refused")
        except ValueError:
            logger.exception("Reply failed")
        return {"status": "received"}

    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            await client.post("/test/messages")

    output = capsys.readouterr().out
    assert MESSAGE_TEXT not in output
    assert API_KEY not in output
    logs = {entry.get("message"): entry for entry in _json_lines(output)}
    received = logs["Visitor message received"]
    assert received["content"] == "[Redacted]"
    assert received["provider_api_key"] == "[Redacted]"
    assert received["turns"] == 3
    failed = logs["Reply failed"]
    assert failed["level"] == "ERROR"
    assert "ValueError: the model refused" in failed["exception"]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


def _service_env() -> dict[str, str]:
    env = {
        key: value for key, value in os.environ.items() if not key.startswith(("COV_", "LOGFIRE_"))
    }
    env.update(
        ENVIRONMENT="test",
        DATABASE_URL=TEST_DATABASE_URL,
        REDIS_URL=TEST_REDIS_URL,
        PYTHONUNBUFFERED="1",
    )
    return env


class _Service:
    """A service process whose combined stdout and stderr is collected line by line."""

    def __init__(self, *command: str) -> None:
        self.process = subprocess.Popen(
            command,
            cwd=BACKEND_ROOT,
            env=_service_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.lines: list[str] = []
        self._queue: queue.Queue[str] = queue.Queue()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self._queue.put(line)

    def wait_for(self, text: str, timeout: float = 20.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            self.lines.append(line)
            if text in line:
                return
        raise AssertionError(f"{text!r} not logged; got:\n{''.join(self.lines)}")

    def stop(self) -> str:
        self.process.terminate()
        self.process.wait(timeout=20)
        self._reader.join(timeout=5)
        assert self.process.stdout is not None
        self.process.stdout.close()
        while not self._queue.empty():
            self.lines.append(self._queue.get())
        return "".join(self.lines)


@pytest.fixture
def empty_broker() -> Iterator[None]:
    yield
    with redis.Redis.from_url(TEST_REDIS_URL) as connection:
        connection.flushdb()


def _assert_every_line_is_json_from(output: str, service: str) -> list[dict[str, Any]]:
    entries = _json_lines(output)  # raises on any line that is not JSON
    logs = [entry for entry in entries if "level" in entry]
    assert logs
    assert {entry["service"] for entry in logs} == {service}
    return logs


def test_the_api_server_writes_only_json_lines() -> None:
    port = _free_port()
    service = _Service(sys.executable, "-m", "app.serve", str(port))
    try:
        service.wait_for("Application startup complete")
        response = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=10)
        service.wait_for("/api/health")
    finally:
        output = service.stop()

    assert response.status_code == 200
    logs = _assert_every_line_is_json_from(output, "api")
    access = next(entry for entry in logs if entry["logger"] == "uvicorn.access")
    assert "GET /api/health" in access["message"]
    assert "color_message" not in access
    # With no Logfire token the spans are on the console too, flushed when the server stops.
    spans = [entry for entry in _json_lines(output) if "context" in entry]
    request = next(span for span in spans if span["name"] == "GET /api/health")
    assert request["resource"]["attributes"]["service.name"] == "api"
    assert access["trace_id"] == request["context"]["trace_id"].removeprefix("0x")


def test_the_worker_writes_only_json_lines(empty_broker: None) -> None:
    service = _Service(
        sys.executable, "-m", "celery", "-A", "app.worker.main", "--quiet",
        "worker", "--pool", "solo", "--loglevel", "INFO",
    )  # fmt: skip
    try:
        service.wait_for("ready")
    finally:
        output = service.stop()

    _assert_every_line_is_json_from(output, "worker")


def test_beat_writes_only_json_lines(empty_broker: None, tmp_path: Path) -> None:
    service = _Service(
        sys.executable, "-m", "celery", "-A", "app.worker.main", "--quiet",
        "beat", "--loglevel", "INFO", "--schedule", str(tmp_path / "beat-schedule"),
    )  # fmt: skip
    try:
        service.wait_for("Starting")
    finally:
        output = service.stop()

    _assert_every_line_is_json_from(output, "beat")


def test_migrations_write_only_json_lines() -> None:
    alembic = Path(sys.executable).with_name("alembic")
    result = subprocess.run(
        [str(alembic), "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=_service_env(),
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stderr == ""
    logs = _assert_every_line_is_json_from(result.stdout, "migrations")
    assert {entry["logger"] for entry in logs} >= {"alembic.runtime.migration"}


@celery_app.task(name="test.echo")
def _echo(content: str) -> str:
    """A stand-in for a task that carries Message text in and out."""
    return content


def test_worker_task_logs_leave_out_task_arguments_and_results(
    settings_env: pytest.MonkeyPatch, empty_broker: None, capsys: pytest.CaptureFixture[str]
) -> None:
    settings_env.setenv("CELERY_TASK_ALWAYS_EAGER", "false")
    sys.modules.pop("app.worker.main", None)
    __import__("app.worker.main")  # the worker entrypoint configures logging and Celery

    with start_worker(celery_app, pool="solo", perform_ping_check=False):
        assert _echo.delay(MESSAGE_TEXT).get(timeout=10) == MESSAGE_TEXT

    output = capsys.readouterr().out
    assert MESSAGE_TEXT not in output
    logs = [entry for entry in _json_lines(output) if entry.get("logger") == "celery.app.trace"]
    succeeded = next(entry for entry in logs if "succeeded" in entry["message"])
    assert succeeded["message"].endswith(": [Redacted]")
    assert succeeded["data"]["args"] == "[Redacted]"
    assert succeeded["data"]["return_value"] == "[Redacted]"
    assert succeeded["data"]["name"] == "test.echo"
