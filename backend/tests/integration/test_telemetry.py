"""API, worker and database activity is traced, and nothing exported carries Message text or
secrets. Spans are captured with an in-memory exporter added next to the configured one."""

import gzip
import json
import threading
from collections.abc import AsyncIterator, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import httpx
import logfire
import pytest
import redis
from asgi_lifespan import LifespanManager
from celery.contrib.testing.worker import start_worker
from fastapi import FastAPI, Response
from opentelemetry import trace
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel, Field

from app.main import create_app
from app.worker.celery_app import celery_app
from tests.conftest import TEST_REDIS_URL, new_member_details


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def empty_broker() -> Iterator[None]:
    yield
    with redis.Redis.from_url(TEST_REDIS_URL) as connection:
        connection.flushdb()


@pytest.fixture
async def traced_client(
    settings_env: pytest.MonkeyPatch, exporter: InMemorySpanExporter
) -> AsyncIterator[httpx.AsyncClient]:
    application = create_app(extra_span_processors=[SimpleSpanProcessor(exporter)])
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


class _OkHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def upstream() -> Iterator[str]:
    """A local HTTP server standing in for an external provider."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _scopes(spans: tuple[ReadableSpan, ...]) -> set[str]:
    return {span.instrumentation_scope.name for span in spans if span.instrumentation_scope}


async def test_an_api_request_is_traced_through_fastapi_and_the_database(
    traced_client: httpx.AsyncClient, exporter: InMemorySpanExporter
) -> None:
    response = await traced_client.get("/api/health")

    assert response.status_code == 200
    spans = exporter.get_finished_spans()
    server = [s for s in spans if s.name == "GET /api/health"]
    assert server, [s.name for s in spans]
    queries = [s for s in spans if s.attributes and s.attributes.get("db.statement") == "SELECT 1"]
    assert queries
    assert queries[0].context.trace_id == server[0].context.trace_id
    assert {
        "opentelemetry.instrumentation.fastapi",
        "opentelemetry.instrumentation.sqlalchemy",
    } <= _scopes(spans)


async def test_a_task_is_traced_from_the_api_through_the_worker(
    settings_env: pytest.MonkeyPatch,
    empty_broker: None,
    exporter: InMemorySpanExporter,
) -> None:
    settings_env.setenv("CELERY_TASK_ALWAYS_EAGER", "false")
    application = create_app(extra_span_processors=[SimpleSpanProcessor(exporter)])
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            with start_worker(celery_app, pool="solo", perform_ping_check=False):
                response = await client.get("/api/health/worker")

    assert response.status_code == 200
    spans = exporter.get_finished_spans()
    by_name = {span.name: span for span in spans}
    request = by_name["GET /api/health/worker"]
    enqueue = by_name["apply_async/worker.health_check"]
    run = by_name["run/worker.health_check"]
    assert enqueue.context.trace_id == request.context.trace_id
    assert run.context.trace_id == request.context.trace_id
    assert "opentelemetry.instrumentation.celery" in _scopes(spans)


async def test_outbound_http_calls_are_traced(
    traced_client: httpx.AsyncClient, exporter: InMemorySpanExporter, upstream: str
) -> None:
    async with httpx.AsyncClient() as outbound:
        response = await outbound.get(f"{upstream}/v1/models")

    assert response.status_code == 200
    calls = [
        span
        for span in exporter.get_finished_spans()
        if span.instrumentation_scope
        and span.instrumentation_scope.name == "opentelemetry.instrumentation.httpx"
    ]
    assert [span.name for span in calls] == ["GET"]
    assert calls[0].attributes
    assert calls[0].attributes["http.status_code"] == 200


MESSAGE_TEXT = "my account number is 4471 and I want a refund"
COOKIE_VALUE = "cookie-value-7f3a"
BEARER_TOKEN = "bearer-token-91c2"
API_KEY = "api-key-55d0"
SESSION_ID = "session-id-c4e8"
PASSWORD = "hunter2-b61f"  # gitleaks:allow (fake test value)
RESET_TOKEN = "made-up-reset-token-6f2d8c"
SENSITIVE = (MESSAGE_TEXT, COOKIE_VALUE, BEARER_TOKEN, API_KEY, SESSION_ID, PASSWORD)


class _ChatTurn(BaseModel):
    content: str = Field(max_length=100)


def _add_chat_route(application: FastAPI) -> None:
    """A stand-in for the widget's chat endpoint, which carries Message text in its body."""

    @application.post("/test/messages")
    async def receive_message(turn: _ChatTurn, response: Response) -> dict[str, str]:
        span = trace.get_current_span()
        span.set_attribute("provider_api_key", API_KEY)
        span.set_attribute("note", "Visitor sent a message")
        span.set_attribute("login.detail", f"password={PASSWORD}")
        logfire.info("Visitor sent {content}", content=turn.content, password=PASSWORD)
        logfire.info("Message has {length} characters", length=len(turn.content))
        logfire.info("Visitor turn {turn}", turn=turn)
        response.set_cookie("session", SESSION_ID)
        return {"status": "received"}


async def test_exported_spans_never_contain_message_text_cookies_auth_headers_or_secrets(
    settings_env: pytest.MonkeyPatch, exporter: InMemorySpanExporter
) -> None:
    application = create_app(extra_span_processors=[SimpleSpanProcessor(exporter)])
    _add_chat_route(application)
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/test/messages",
                json={"content": MESSAGE_TEXT},
                headers={
                    "Cookie": f"studio_session={COOKIE_VALUE}",
                    "Authorization": f"Bearer {BEARER_TOKEN}",
                    "X-Api-Key": API_KEY,
                },
            )
            # Validation errors echo the rejected input back.
            rejected = await client.post("/test/messages", json={"content": MESSAGE_TEXT * 3})

    assert response.status_code == 200
    assert rejected.status_code == 422
    spans = exporter.get_finished_spans()
    exported = "\n".join(span.to_json() for span in spans)
    leaked = [value for value in SENSITIVE if value in exported]
    assert leaked == []

    # The sensitive attributes were captured and then redacted, not merely never recorded.
    request = next(span for span in spans if span.name == "POST /test/messages")
    attributes = dict(request.attributes or {})
    assert attributes["http.request.header.cookie"] == ("[Scrubbed due to 'cookie']",)
    assert attributes["http.request.header.authorization"] == ("[Scrubbed due to 'auth']",)
    assert attributes["http.request.header.x_api_key"] == ("[Scrubbed due to 'api_key']",)
    assert attributes["provider_api_key"] == "[Scrubbed due to 'api_key']"
    assert attributes["http.response.header.set_cookie"] == ("[Scrubbed due to 'cookie']",)
    assert str(attributes["fastapi.arguments.values"]).count("[Scrubbed") == 1
    # Ordinary attributes survive, including text that merely mentions a message.
    assert attributes["http.route"] == "/test/messages"
    assert attributes["note"] == "Visitor sent a message"
    assert attributes["login.detail"] == "[Scrubbed due to 'password']"
    log = next(span for span in spans if span.name == "Visitor sent {content}")
    assert log.attributes
    assert log.attributes["content"] == "[Scrubbed due to 'content']"
    assert log.attributes["logfire.msg"] == "Visitor sent {content}"
    nested = next(span for span in spans if span.name == "Visitor turn {turn}")
    assert nested.attributes
    assert nested.attributes["logfire.msg"] == "Visitor turn {turn}"
    harmless = next(span for span in spans if span.name == "Message has {length} characters")
    assert harmless.attributes
    assert harmless.attributes["logfire.msg"] == f"Message has {len(MESSAGE_TEXT)} characters"


async def _post_a_message(application: FastAPI) -> None:
    _add_chat_route(application)
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/test/messages",
                json={"content": MESSAGE_TEXT},
                headers={"Authorization": f"Bearer {BEARER_TOKEN}"},
            )
        assert response.status_code == 200
        logfire.force_flush()


async def test_without_a_logfire_token_spans_are_written_to_the_console_as_json(
    settings_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings_env.setenv("LOGFIRE_TOKEN", "")  # how compose passes an unset token

    await _post_a_message(create_app())

    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    spans = [json.loads(line) for line in lines]
    exported_spans = [span for span in spans if "context" in span]
    assert "POST /test/messages" in {span["name"] for span in exported_spans}
    assert {span["resource"]["attributes"]["service.name"] for span in exported_spans} == {"api"}
    assert not [value for value in SENSITIVE if value in "\n".join(lines)]


class _FakeLogfire(BaseHTTPRequestHandler):
    """Records OTLP trace exports the way Logfire's ingest endpoint would receive them."""

    received: list[tuple[str, str | None, bytes]]

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if self.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        self.received.append((self.path, self.headers.get("Authorization"), body))
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def fake_logfire() -> Iterator[tuple[str, list[tuple[str, str | None, bytes]]]]:
    received: list[tuple[str, str | None, bytes]] = []
    handler = type("Handler", (_FakeLogfire,), {"received": received})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", received
    server.shutdown()
    server.server_close()


async def test_with_a_logfire_token_scrubbed_spans_are_sent_to_logfire_instead_of_the_console(
    settings_env: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_logfire: tuple[str, list[tuple[str, str | None, bytes]]],
) -> None:
    base_url, received = fake_logfire
    settings_env.setenv("LOGFIRE_TOKEN", "pylf_v1_us_test-token")
    settings_env.setenv("LOGFIRE_BASE_URL", base_url)

    await _post_a_message(create_app())

    assert received
    assert {(path, token) for path, token, _ in received} == {
        ("/v1/traces", "pylf_v1_us_test-token")
    }
    names: set[str] = set()
    for _, _, body in received:
        request = ExportTraceServiceRequest.FromString(body)
        for resource_spans in request.resource_spans:
            for scope_spans in resource_spans.scope_spans:
                names.update(span.name for span in scope_spans.spans)
        assert not [value for value in SENSITIVE if value.encode() in body]
    assert "POST /test/messages" in names
    assert not [line for line in capsys.readouterr().out.splitlines() if '"context"' in line]


@celery_app.task(name="test.reply")
def _reply(content: str) -> str:
    """A stand-in for a task that carries Message text in and out."""
    return f"You said: {content}"


async def test_task_spans_never_contain_the_message_text_a_task_carries(
    settings_env: pytest.MonkeyPatch, empty_broker: None, exporter: InMemorySpanExporter
) -> None:
    settings_env.setenv("CELERY_TASK_ALWAYS_EAGER", "false")
    application = create_app(extra_span_processors=[SimpleSpanProcessor(exporter)])
    async with LifespanManager(application):
        with start_worker(celery_app, pool="solo", perform_ping_check=False):
            assert MESSAGE_TEXT in _reply.delay(MESSAGE_TEXT).get(timeout=10)

    spans = exporter.get_finished_spans()
    assert {"apply_async/test.reply", "run/test.reply"} <= {span.name for span in spans}
    assert MESSAGE_TEXT not in "\n".join(span.to_json() for span in spans)


async def test_link_tokens_in_request_bodies_are_never_exported(
    settings_env: pytest.MonkeyPatch, database_schema: None, exporter: InMemorySpanExporter
) -> None:
    """Invite and reset links carry their token in the request body; spans must not."""
    application = create_app(extra_span_processors=[SimpleSpanProcessor(exporter)])
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
            owner = await client.post("/api/auth/sign-up", json=new_member_details())
            organisation_id = owner.json()["organisations"][0]["id"]
            created = await client.post(
                f"/api/organisations/{organisation_id}/invites",
                json={"email": new_member_details()["email"], "role": "editor"},
            )
            invite_token = parse_qs(urlparse(created.json()["link"]).query)["token"][0]
            client.cookies.clear()
            looked_up = await client.post("/api/invites/lookup", json={"token": invite_token})
            joined = await client.post(
                "/api/invites/sign-up",
                json={"token": invite_token, "name": "Invited", "password": PASSWORD},
            )
            reset = await client.post(
                "/api/auth/password-reset/complete",
                json={"token": RESET_TOKEN, "password": PASSWORD},
            )
        logfire.info(
            "Agent settings",
            settings={"token_budget": 5000, "max_tokens": 800, "invite_token": RESET_TOKEN},
            note="Copy the token",
        )

    assert (looked_up.status_code, joined.status_code, reset.status_code) == (200, 201, 400)
    exported = "\n".join(span.to_json() for span in exporter.get_finished_spans())
    assert invite_token not in exported
    assert RESET_TOKEN not in exported
    # Only keys ending in "token" are redacted: settings that merely mention tokens are kept.
    settings = next(span for span in exporter.get_finished_spans() if span.name == "Agent settings")
    attributes = dict(settings.attributes or {})
    assert json.loads(str(attributes["settings"])) == {
        "token_budget": 5000,
        "max_tokens": 800,
        "invite_token": "[Scrubbed due to '_token']",
    }
    assert attributes["note"] == "Copy the token"
