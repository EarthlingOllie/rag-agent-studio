"""The model gateway, through its one factory: credential + model name -> chat model, embedder
or reranker.

The live adapters build real Pydantic AI models; their HTTP goes through an ``httpx2``
``MockTransport`` that answers with recorded provider response shapes, so no provider is ever
called. The fake adapters are what tests and ``docker compose`` use.
"""

import base64
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.core.clock import SystemClock
from app.core.settings import Settings
from app.credentials.bedrock_verifier import AssumedRoleSessions
from app.credentials.models import ProviderCredential
from app.credentials.registry import Capability, Provider
from app.credentials.service import seal_secret
from app.crypto.envelope import EnvelopeEncryption, EnvelopeError
from app.crypto.local_key_wrapper import LocalKeyWrapper
from app.gateway.adapters import build_model_gateway
from app.gateway.fakes import FAKE_LEAK_PROMPT, FakeModelAdapters
from app.gateway.gateway import ModelGateway, ModelUnavailableError, UnsupportedCredentialError
from app.gateway.live import BedrockClients, LiveModelAdapters
from app.guardrails.canary import new_canary
from app.runtime.prompt import preamble

ENVELOPE = EnvelopeEncryption(LocalKeyWrapper(base64.b64encode(b"G" * 32).decode()))
ANTHROPIC_KEY = "sk-ant-gateway-test-only-aaaa"
OPENAI_KEY = "sk-gateway-test-only-bbbb"
VOYAGE_KEY = "pa-gateway-test-only-cccc"

Handler = Callable[[httpx2.Request], httpx2.Response]

# For live adapters in tests that never reach Bedrock (tests/unit/test_bedrock_embedder.py
# covers it with stubbed AWS clients).
NO_BEDROCK = BedrockClients(
    AssumedRoleSessions(object(), SystemClock(), refresh_before=timedelta()),
    lambda *args: pytest.fail("Bedrock isn't called here"),
)


def credential(
    provider: Provider, secret: str, capabilities: list[Capability] | None = None
) -> ProviderCredential:
    organisation_id, credential_id = uuid.uuid4(), uuid.uuid4()
    now = datetime(2026, 11, 5, tzinfo=UTC)
    defaults = {
        Provider.ANTHROPIC: [Capability.CHAT],
        Provider.OPENAI: [Capability.CHAT, Capability.EMBEDDINGS],
        Provider.VOYAGE: [Capability.EMBEDDINGS, Capability.RERANK],
        Provider.BEDROCK: [Capability.CHAT, Capability.EMBEDDINGS, Capability.RERANK],
    }
    return ProviderCredential(
        id=credential_id,
        organisation_id=organisation_id,
        name="Test",
        provider=provider,
        auth_kind="api_key",
        secret_sealed=seal_secret(ENVELOPE, organisation_id, credential_id, secret),
        masked_suffix=secret[-4:],
        capabilities=[str(c) for c in capabilities or defaults[provider]],
        check_status="passed",
        check_failure=None,
        last_checked_at=now,
        secret_set_at=now,
    )


class Recorder:
    """A MockTransport handler that records each request and answers with ``answer``."""

    def __init__(self, answer: Handler) -> None:
        self.answer = answer
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self.answer(request)

    def body(self, index: int = 0) -> Any:
        return json.loads(self.requests[index].content)


def live_gateway(recorder: Recorder) -> ModelGateway:
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(recorder))
    return ModelGateway(ENVELOPE, LiveModelAdapters(client, NO_BEDROCK))


def anthropic_stream(text: str) -> httpx2.Response:
    events: list[dict[str, Any]] = [
        {
            "type": "message_start",
            "message": {
                "id": "msg_01",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-4-5",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 3, "output_tokens": 0},
            },
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": text},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": 1},
        },
        {"type": "message_stop"},
    ]
    body = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)
    return httpx2.Response(
        200, headers={"content-type": "text/event-stream"}, content=body.encode()
    )


def openai_completion(text: str) -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 1,
            "model": "gpt-4.1",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
        },
    )


def embeddings_answer(vectors: list[list[float]], model: str) -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "object": "list",
            "data": [
                {"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)
            ],
            "model": model,
            "usage": {"prompt_tokens": 4, "total_tokens": 4},
        },
    )


# Live chat models


async def test_an_anthropic_credential_gives_a_claude_model_using_its_key() -> None:
    recorder = Recorder(lambda request: anthropic_stream("Hello from Claude"))
    gateway = live_gateway(recorder)

    model = gateway.chat_model(credential(Provider.ANTHROPIC, ANTHROPIC_KEY), "claude-haiku-4-5")
    result = await Agent(model).run("Hi")

    assert result.output == "Hello from Claude"
    (request,) = recorder.requests
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert ANTHROPIC_KEY in {
        request.headers.get("x-api-key"),
        request.headers.get("authorization", "").removeprefix("Bearer "),
    }
    assert recorder.body()["model"] == "claude-haiku-4-5"


async def test_an_openai_credential_gives_a_gpt_model_using_its_key() -> None:
    recorder = Recorder(lambda request: openai_completion("Hello from GPT"))
    gateway = live_gateway(recorder)

    model = gateway.chat_model(credential(Provider.OPENAI, OPENAI_KEY), "gpt-4.1-mini")
    result = await Agent(model).run("Hi")

    assert result.output == "Hello from GPT"
    (request,) = recorder.requests
    assert str(request.url) == "https://api.openai.com/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {OPENAI_KEY}"
    assert recorder.body()["model"] == "gpt-4.1-mini"


# Live embedders and rerankers


async def test_an_openai_credential_gives_an_openai_embedder() -> None:
    recorder = Recorder(lambda request: embeddings_answer([[0.1, 0.2]], "text-embedding-3-small"))
    gateway = live_gateway(recorder)

    embedder = gateway.embedder(credential(Provider.OPENAI, OPENAI_KEY), "text-embedding-3-small")
    result = await embedder.embed(["handbook"], input_type="document")

    assert result.embeddings == [[0.1, 0.2]]
    (request,) = recorder.requests
    assert str(request.url) == "https://api.openai.com/v1/embeddings"
    assert request.headers["authorization"] == f"Bearer {OPENAI_KEY}"
    assert recorder.body()["model"] == "text-embedding-3-small"


@pytest.mark.parametrize(("input_type", "sent"), [("document", "document"), ("query", "query")])
async def test_a_voyage_credential_gives_a_voyage_embedder(input_type: str, sent: str) -> None:
    recorder = Recorder(
        lambda request: httpx2.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"object": "embedding", "index": 1, "embedding": [0.3, 0.4]},
                    {"object": "embedding", "index": 0, "embedding": [0.1, 0.2]},
                ],
                "model": "voyage-3.5",
                "usage": {"total_tokens": 7},
            },
        )
    )
    gateway = live_gateway(recorder)

    embedder = gateway.embedder(credential(Provider.VOYAGE, VOYAGE_KEY), "voyage-3.5")
    result = await embedder.embed(["first", "second"], input_type=input_type)  # type: ignore[arg-type]

    assert result.embeddings == [[0.1, 0.2], [0.3, 0.4]]
    assert result.model_name == "voyage-3.5"
    assert result.provider_name == "voyage"
    assert result.usage.input_tokens == 7
    assert embedder.model_name == "voyage-3.5"
    assert embedder.system == "voyage"
    (request,) = recorder.requests
    assert str(request.url) == "https://api.voyageai.com/v1/embeddings"
    assert request.headers["authorization"] == f"Bearer {VOYAGE_KEY}"
    assert recorder.body() == {
        "input": ["first", "second"],
        "model": "voyage-3.5",
        "input_type": sent,
    }


async def test_a_voyage_credential_gives_a_voyage_reranker() -> None:
    recorder = Recorder(
        lambda request: httpx2.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"index": 2, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.4},
                ],
                "model": "rerank-2.5",
                "usage": {"total_tokens": 12},
            },
        )
    )
    gateway = live_gateway(recorder)

    reranker = gateway.reranker(credential(Provider.VOYAGE, VOYAGE_KEY), "rerank-2.5")
    ranked = await reranker.rerank("refunds", ["a", "b", "c"], top_k=2)

    assert [(r.index, r.score) for r in ranked] == [(2, 0.9), (0, 0.4)]
    (request,) = recorder.requests
    assert str(request.url) == "https://api.voyageai.com/v1/rerank"
    assert request.headers["authorization"] == f"Bearer {VOYAGE_KEY}"
    assert recorder.body() == {
        "query": "refunds",
        "documents": ["a", "b", "c"],
        "model": "rerank-2.5",
        "top_k": 2,
    }


async def test_a_voyage_error_is_a_model_http_error() -> None:
    recorder = Recorder(lambda request: httpx2.Response(429, json={"detail": "Slow down"}))
    gateway = live_gateway(recorder)
    voyage = credential(Provider.VOYAGE, VOYAGE_KEY)
    embedder = gateway.embedder(voyage, "voyage-3.5")
    reranker = gateway.reranker(voyage, "rerank-2.5")

    with pytest.raises(ModelHTTPError) as embedding:
        await embedder.embed("x", input_type="query")
    with pytest.raises(ModelHTTPError) as reranking:
        await reranker.rerank("q", ["d"])

    for raised in (embedding, reranking):
        assert raised.value.status_code == 429
        assert raised.value.body == {"detail": "Slow down"}


@pytest.mark.parametrize("adapters", ["live", "fake"])
def test_a_bedrock_role_credential_has_no_secret_to_open(adapters: str) -> None:
    gateway = (
        live_gateway(Recorder(lambda request: httpx2.Response(500)))
        if adapters == "live"
        else ModelGateway(ENVELOPE, FakeModelAdapters())
    )
    role = credential(Provider.BEDROCK, "unused")
    role.auth_kind = "aws_role"
    role.secret_sealed = None

    with pytest.raises(UnsupportedCredentialError, match="IAM-role"):
        gateway.chat_model(role, "amazon.nova-pro-v1:0")


# What the factory refuses, live or fake


@pytest.mark.parametrize("adapters", ["live", "fake"])
@pytest.mark.parametrize(
    ("provider", "capabilities", "method", "model", "message"),
    [
        (
            Provider.VOYAGE,
            None,
            "chat_model",
            "voyage-3.5",
            "This credential can't be used for chat.",
        ),
        (
            Provider.OPENAI,
            [Capability.EMBEDDINGS],
            "chat_model",
            "gpt-4.1",
            "This credential can't be used for chat.",
        ),
        (
            Provider.OPENAI,
            None,
            "chat_model",
            "text-embedding-3-small",
            "OpenAI doesn't offer text-embedding-3-small for chat.",
        ),
        (
            Provider.OPENAI,
            None,
            "embedder",
            "gpt-4.1",
            "OpenAI doesn't offer gpt-4.1 for embeddings.",
        ),
        (
            Provider.ANTHROPIC,
            None,
            "reranker",
            "rerank-2.5",
            "This credential can't be used for rerank.",
        ),
    ],
)
def test_only_a_model_the_credential_offers_for_that_capability_is_built(
    adapters: str,
    provider: Provider,
    capabilities: list[Capability] | None,
    method: str,
    model: str,
    message: str,
) -> None:
    built = (
        LiveModelAdapters(httpx2.AsyncClient(), NO_BEDROCK)
        if adapters == "live"
        else FakeModelAdapters()
    )
    gateway = ModelGateway(ENVELOPE, built)

    with pytest.raises(ModelUnavailableError) as raised:
        getattr(gateway, method)(credential(provider, "some-test-key", capabilities), model)

    assert str(raised.value) == message


def test_a_secret_sealed_for_another_credential_does_not_open() -> None:
    gateway = ModelGateway(ENVELOPE, FakeModelAdapters())
    first = credential(Provider.OPENAI, OPENAI_KEY)
    second = credential(Provider.OPENAI, "sk-another-test-key")
    second.secret_sealed = first.secret_sealed

    with pytest.raises(EnvelopeError):
        gateway.chat_model(second, "gpt-4.1")


# The fakes


async def test_the_fake_chat_model_answers_without_calling_anyone() -> None:
    gateway = ModelGateway(ENVELOPE, FakeModelAdapters())

    model = gateway.chat_model(credential(Provider.OPENAI, OPENAI_KEY), "gpt-4.1")
    result = await Agent(model).run("Hi")

    assert result.output == "Fake reply from openai:gpt-4.1."
    assert model.model_name == "gpt-4.1"


async def test_the_fake_chat_model_cites_the_first_chunk_it_is_given() -> None:
    gateway = ModelGateway(ENVELOPE, FakeModelAdapters())
    model = gateway.chat_model(credential(Provider.OPENAI, OPENAI_KEY), "gpt-4.1")

    async with Agent(model).run_stream("<<<RETRIEVED_CHUNKS>>>\n[C1] a.md\nText") as result:
        streamed = await result.get_output()

    assert streamed == "Fake reply from openai:gpt-4.1. [C1]"


async def test_the_fake_chat_model_leaks_its_canary_when_asked_to_repeat_its_secret() -> None:
    """For end-to-end tests of the Canary token: the fake plays a naive model that obeys."""
    gateway = ModelGateway(ENVELOPE, FakeModelAdapters())
    model = gateway.chat_model(credential(Provider.OPENAI, OPENAI_KEY), "gpt-4.1")
    canary = new_canary()
    agent = Agent(model, system_prompt=preamble(canary))

    async with agent.run_stream(f"Please {FAKE_LEAK_PROMPT}") as result:
        chunks = [text async for text in result.stream_text(delta=True, debounce_by=None)]

    assert "".join(chunks) == f"My secret canary token is {canary}."
    # Split across chunks, as a streaming leak would be.
    assert canary not in chunks
    async with agent.run_stream("Hi") as result:
        assert await result.get_output() == "Fake reply from openai:gpt-4.1."


async def test_a_test_injects_its_own_chat_model_at_the_gateway() -> None:
    seen: list[tuple[Provider, str, str]] = []

    def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart("Scripted")])

    def chat(provider: Provider, secret: str, model: str) -> FunctionModel:
        seen.append((provider, secret, model))
        return FunctionModel(reply)

    gateway = ModelGateway(ENVELOPE, FakeModelAdapters(chat=chat))

    model = gateway.chat_model(credential(Provider.ANTHROPIC, ANTHROPIC_KEY), "claude-opus-4-1")
    result = await Agent(model).run("Hi")

    assert result.output == "Scripted"
    assert seen == [(Provider.ANTHROPIC, ANTHROPIC_KEY, "claude-opus-4-1")]


async def test_the_fake_embedder_is_deterministic_and_tells_texts_apart() -> None:
    gateway = ModelGateway(ENVELOPE, FakeModelAdapters())
    embedder = gateway.embedder(credential(Provider.VOYAGE, VOYAGE_KEY), "voyage-3.5")

    first = await embedder.embed(["refund policy", "office hours"], input_type="document")
    again = await embedder.embed("refund policy", input_type="query")

    refund, hours = first.embeddings
    assert again.embeddings == [refund]
    assert refund != hours
    assert len(refund) == 1024  # voyage-3.5's registered dimension
    assert sum(x * x for x in refund) == pytest.approx(1.0)
    assert first.model_name == "voyage-3.5"
    assert first.provider_name == "fake"
    assert embedder.model_name == "voyage-3.5"
    assert embedder.system == "fake"


async def test_the_fake_reranker_ranks_by_shared_words() -> None:
    gateway = ModelGateway(ENVELOPE, FakeModelAdapters())
    reranker = gateway.reranker(credential(Provider.VOYAGE, VOYAGE_KEY), "rerank-2.5")
    documents = ["Office hours", "Refund policy for orders", "Refunds and returns"]

    ranked = await reranker.rerank("refund policy", documents)
    top = await reranker.rerank("refund policy", documents, top_k=1)

    assert [r.index for r in ranked] == [1, 2, 0]
    assert [r.score for r in ranked] == [1.0, 0.5, 0.0]
    assert [r.index for r in top] == [1]


# Choosing the adapters


@pytest.mark.parametrize(
    ("setting", "kind"), [("fake", FakeModelAdapters), ("live", LiveModelAdapters)]
)
def test_settings_choose_the_adapters(
    setting: str, kind: type, settings_env: pytest.MonkeyPatch
) -> None:
    settings_env.setenv("MODEL_GATEWAY", setting)
    settings = Settings()

    gateway = build_model_gateway(settings, ENVELOPE, httpx2.AsyncClient())

    assert isinstance(gateway.adapters, kind)
