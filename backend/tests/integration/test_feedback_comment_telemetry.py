"""Telemetry seam: a Visitor's Message Feedback comment is free text they typed, like a Message,
so exported spans must never carry it (spans outlive the Conversation and its deletion).

Spans are captured with an in-memory exporter added next to the configured one."""

from collections.abc import AsyncIterator

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.main import create_app
from tests.conftest import BASE_URL, SignedUpMember
from tests.integration.test_embed import conversation_token
from tests.integration.test_message_feedback import give, live, reply

COMMENT = "My account number is 4471-0098, please call me back"


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
async def app(
    settings_env: pytest.MonkeyPatch, database_schema: None, exporter: InMemorySpanExporter
) -> AsyncIterator[FastAPI]:
    """The conftest app, with every scrubbed span also sent to ``exporter``."""
    application = create_app(extra_span_processors=[SimpleSpanProcessor(exporter)])
    async with LifespanManager(application):
        redis = application.state.redis
        for pattern in ("sign-in-failures:*", "widget-rate:*", "widget-budget:*"):
            async for key in redis.scan_iter(match=pattern):
                await redis.delete(key)
        yield application


async def test_a_visitors_feedback_comment_is_never_exported_in_spans(
    app: FastAPI,
    owner: SignedUpMember,
    exporter: InMemorySpanExporter,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as visitor:
        agent = await live(app, owner)
        public_id = agent["public_id"]
        token = await conversation_token(visitor, public_id)
        message_id = await reply(visitor, public_id, token, "How much leave?")

        given = await give(visitor, public_id, token, message_id, rating="down", comment=COMMENT)

    assert given.status_code == 200, given.text
    assert given.json() == {"rating": "down", "comment": COMMENT}
    spans = exporter.get_finished_spans()
    request = next(
        span
        for span in spans
        if span.name == "PUT /api/widget/agents/{public_id}/messages/{message_id}/feedback"
    )
    # The request's arguments were captured, and the comment in them was redacted.
    arguments = str(dict(request.attributes or {})["fastapi.arguments.values"])
    assert "[Scrubbed due to 'comment']" in arguments
    assert '"rating":"down"' in arguments.replace(" ", "")
    assert COMMENT not in "\n".join(span.to_json() for span in spans)
