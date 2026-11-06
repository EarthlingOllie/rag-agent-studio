"""API seam: when the provider fails, the Playground stream ends with a typed ``error`` event
whose message says why, and the Editor can reset the Playground to a fresh Conversation.

Provider failures are raised by the chat model (a Pydantic AI ``FunctionModel`` raising the
errors Pydantic AI's provider models raise), by the gateway, or by the fake chat model the
``docker compose`` stack uses, asked to simulate one."""

import json
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelHTTPError,
    ModelNotFoundError,
    ModelOverloadedError,
    ModelQuotaExceededError,
    ModelRateLimitError,
    UnexpectedModelBehavior,
)
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo

from app.credentials.registry import Provider
from app.gateway.fakes import FakeModelAdapters
from app.gateway.gateway import UnsupportedCredentialError
from app.gateway.ports import Reranker
from tests.agents import (
    StreamFunction,
    answer_text,
    answer_with,
    ask,
    parse_sse,
    playground_path,
    save_draft,
    start_conversation,
)
from tests.conftest import SignedUpMember
from tests.integration.test_playground import ready_agent, settings_seen
from tests.integration.test_provider_credentials import VOYAGE_KEY, added

INVALID_KEY = (
    "The provider rejected the API key. An Owner can check or rotate the Provider Credential "
    "in Settings, Provider Credentials."
)


def failing(error: Exception, *, after: list[str] | None = None) -> StreamFunction:
    """A stream function that streams ``after`` (if any), then raises ``error``."""

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        for text in after or []:
            yield text
        raise error

    return stream


async def test_an_invalid_key_ends_the_stream_with_a_typed_error_event(
    app: FastAPI, owner: SignedUpMember
) -> None:
    error = ModelHTTPError.for_category(
        ModelAuthenticationError, status_code=401, model_name="gpt-4.1-mini"
    )
    answer_with(app, failing(error))
    member, project_id, agent_id = await ready_agent(app, owner)
    conversation = await start_conversation(member, project_id, agent_id)

    response = await ask(member, project_id, agent_id, conversation["id"], "How much leave?")

    assert response.status_code == 200, response.text
    assert parse_sse(response.text) == [
        ("error", {"code": "invalid_key", "message": INVALID_KEY}),
    ]


RATE_LIMITED = (
    "The provider says this key is over its rate limit or quota. Wait a moment and try again, "
    "or check the provider account's limits and billing."
)
PROVIDER_ERROR = "The provider couldn't answer just now. Try again in a moment."


def unavailable(model: str) -> str:
    return (
        f"The model {model} isn't available from the provider right now. Try again later, or "
        "choose another model for the Draft or the Default Model."
    )


@pytest.mark.parametrize(
    ("error", "code", "message"),
    [
        (
            ModelHTTPError.for_category(ModelRateLimitError, status_code=429, model_name="m"),
            "rate_limited",
            RATE_LIMITED,
        ),
        (
            ModelHTTPError.for_category(ModelQuotaExceededError, status_code=402, model_name="m"),
            "rate_limited",
            RATE_LIMITED,
        ),
        (
            ModelHTTPError.for_category(ModelNotFoundError, status_code=404, model_name="gpt-9"),
            "model_unavailable",
            unavailable("gpt-9"),
        ),
        (
            ModelHTTPError.for_category(ModelOverloadedError, status_code=529, model_name="gpt-9"),
            "model_unavailable",
            unavailable("gpt-9"),
        ),
        # Plain HTTP errors (a provider Pydantic AI doesn't categorise) go by their status.
        (ModelHTTPError(403, "m"), "invalid_key", INVALID_KEY),
        (ModelHTTPError(429, "m"), "rate_limited", RATE_LIMITED),
        (ModelHTTPError(404, "gpt-9"), "model_unavailable", unavailable("gpt-9")),
        (ModelHTTPError(500, "m"), "provider_error", PROVIDER_ERROR),
        (ModelHTTPError(400, "m"), "provider_error", PROVIDER_ERROR),
        (ModelAPIError("m", "Connection reset"), "provider_error", PROVIDER_ERROR),
        (UnexpectedModelBehavior("Invalid JSON"), "provider_error", PROVIDER_ERROR),
    ],
)
async def test_each_provider_failure_has_its_own_code_and_message(
    app: FastAPI, owner: SignedUpMember, error: Exception, code: str, message: str
) -> None:
    answer_with(app, failing(error))
    member, project_id, agent_id = await ready_agent(app, owner)
    conversation = await start_conversation(member, project_id, agent_id)

    response = await ask(member, project_id, agent_id, conversation["id"], "How much leave?")

    assert parse_sse(response.text) == [("error", {"code": code, "message": message})]


async def test_a_failure_mid_answer_ends_the_stream_with_the_error_and_saves_no_answer(
    app: FastAPI, owner: SignedUpMember
) -> None:
    error = ModelHTTPError.for_category(ModelRateLimitError, status_code=429, model_name="m")
    answer_with(app, failing(error, after=["Everyone gets ", "twenty-five days of annual leave "]))
    member, project_id, agent_id = await ready_agent(app, owner)
    conversation = await start_conversation(member, project_id, agent_id)

    response = await ask(member, project_id, agent_id, conversation["id"], "How much leave?")

    events = parse_sse(response.text)
    assert {event for event, _ in events[:-1]} == {"token"}
    assert events[-1] == ("error", {"code": "rate_limited", "message": RATE_LIMITED})
    saved = await member.client.get(
        playground_path(member, project_id, agent_id, conversation["id"])
    )
    # The question is kept; no answer was saved for it.
    assert [(m["role"], m["content"]) for m in saved.json()["messages"]] == [
        ("user", "How much leave?")
    ]


async def test_a_question_the_provider_failed_on_is_not_remembered(
    app: FastAPI, owner: SignedUpMember
) -> None:
    calls = 0

    async def fails_the_second_time(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ModelHTTPError(429, "m")
        async for text in settings_seen(messages, info):
            yield text

    answer_with(app, fails_the_second_time)
    member, project_id, agent_id = await ready_agent(app, owner)
    conversation = await start_conversation(member, project_id, agent_id)
    await ask(member, project_id, agent_id, conversation["id"], "One?")
    failed = await ask(member, project_id, agent_id, conversation["id"], "Two?")
    assert parse_sse(failed.text)[-1][0] == "error"

    response = await ask(member, project_id, agent_id, conversation["id"], "Three?")

    assert json.loads(answer_text(response))["remembered"] == ["One?"]


async def test_a_chat_model_the_gateway_cant_build_is_unavailable(
    app: FastAPI, owner: SignedUpMember
) -> None:
    def cant_build(provider: Provider, secret: str, model: str) -> Model:
        raise UnsupportedCredentialError("No client for this provider's chat models.")

    app.state.model_gateway.adapters = FakeModelAdapters(chat=cant_build)
    member, project_id, agent_id = await ready_agent(app, owner)
    conversation = await start_conversation(member, project_id, agent_id)

    response = await ask(member, project_id, agent_id, conversation["id"], "How much leave?")

    assert parse_sse(response.text) == [
        ("error", {"code": "model_unavailable", "message": unavailable("gpt-4.1-mini")})
    ]


@pytest.mark.parametrize(
    ("question", "code"),
    [
        ("Please simulate an invalid key.", "invalid_key"),
        ("Simulate a rate limit", "rate_limited"),
        ("simulate an unavailable model now", "model_unavailable"),
    ],
)
async def test_the_fake_chat_model_simulates_each_provider_failure_on_request(
    app: FastAPI, owner: SignedUpMember, question: str, code: str
) -> None:
    # The fake adapters as the docker compose stack runs them: end-to-end tests ask for failures.
    app.state.model_gateway.adapters = FakeModelAdapters()
    member, project_id, agent_id = await ready_agent(app, owner)
    conversation = await start_conversation(member, project_id, agent_id)

    response = await ask(member, project_id, agent_id, conversation["id"], question)

    ((event, data),) = parse_sse(response.text)
    assert (event, data["code"]) == ("error", code)


# Reset: the Studio starts a new Playground Conversation.


async def test_a_reset_playground_starts_a_new_conversation_that_remembers_nothing(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, settings_seen)
    member, project_id, agent_id = await ready_agent(app, owner)
    first = await start_conversation(member, project_id, agent_id)
    for question in ["One?", "Two?"]:
        await ask(member, project_id, agent_id, first["id"], question)

    reset = await start_conversation(member, project_id, agent_id)
    response = await ask(member, project_id, agent_id, reset["id"], "Fresh?")

    assert reset["id"] != first["id"]
    assert (reset["is_playground"], reset["messages"]) == (True, [])
    assert json.loads(answer_text(response))["remembered"] == []
    # The earlier Conversation is kept as it was, and goes on where it left off.
    earlier = await member.client.get(playground_path(member, project_id, agent_id, first["id"]))
    assert [m["content"] for m in earlier.json()["messages"] if m["role"] == "user"] == [
        "One?",
        "Two?",
    ]
    again = await ask(member, project_id, agent_id, first["id"], "Three?")
    assert json.loads(answer_text(again))["remembered"] == ["One?", "Two?"]


# Truncation to the remembered turns.


async def test_the_remembered_turns_are_the_most_recent_ones_as_the_conversation_grows(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, settings_seen)
    member, project_id, agent_id = await ready_agent(app, owner)
    await save_draft(member, project_id, agent_id, {"behaviour": {"remembered_turns": 3}})
    conversation = await start_conversation(member, project_id, agent_id)

    seen = []
    for question in ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]:
        response = await ask(member, project_id, agent_id, conversation["id"], question)
        seen.append(json.loads(answer_text(response))["remembered"])

    assert seen == [
        [],
        ["Q1"],
        ["Q1", "Q2"],
        ["Q1", "Q2", "Q3"],
        ["Q2", "Q3", "Q4"],
        ["Q3", "Q4", "Q5"],
    ]


async def test_the_remembered_turns_reach_the_model_as_whole_question_and_answer_pairs(
    app: FastAPI, owner: SignedUpMember
) -> None:
    async def history_kinds(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        """Answers with the kind of each message before the question, and its text."""
        yield json.dumps(
            [
                [part.part_kind, str(getattr(part, "content", ""))[:12]]
                for message in messages[:-1]
                for part in message.parts
                if part.part_kind in {"user-prompt", "text"}
            ]
        )

    answer_with(app, history_kinds)
    member, project_id, agent_id = await ready_agent(app, owner)
    await save_draft(member, project_id, agent_id, {"behaviour": {"remembered_turns": 1}})
    conversation = await start_conversation(member, project_id, agent_id)
    await ask(member, project_id, agent_id, conversation["id"], "First?")
    second = await ask(member, project_id, agent_id, conversation["id"], "Second?")

    response = await ask(member, project_id, agent_id, conversation["id"], "Third?")

    # Only the last turn: its question, then the answer the model gave to it.
    assert json.loads(answer_text(response)) == [
        ["user-prompt", "Second?"],
        ["text", answer_text(second)[:12]],
    ]


async def test_remembered_turns_are_capped_at_twenty(app: FastAPI, owner: SignedUpMember) -> None:
    member, project_id, agent_id = await ready_agent(app, owner)

    refused = await save_draft(
        member, project_id, agent_id, {"behaviour": {"remembered_turns": 21}}
    )
    most = await save_draft(member, project_id, agent_id, {"behaviour": {"remembered_turns": 20}})

    assert (refused.status_code, most.status_code) == (422, 200)


async def test_a_reranker_the_gateway_cant_build_is_unavailable(
    app: FastAPI, owner: SignedUpMember
) -> None:
    def cant_build(provider: Provider, secret: str, model: str) -> Reranker:
        raise UnsupportedCredentialError("No client for this provider's rerank models.")

    adapters: FakeModelAdapters = app.state.model_gateway.adapters
    adapters.reranker = cant_build  # type: ignore[method-assign]
    member, project_id, agent_id = await ready_agent(app, owner)
    voyage = await added(owner, provider="voyage", api_key=VOYAGE_KEY)
    reranker = {"credential_id": voyage["id"], "model": "rerank-2.5"}
    saved = await save_draft(owner, project_id, agent_id, {"retrieval": {"reranker": reranker}})
    assert saved.status_code == 200, saved.text
    conversation = await start_conversation(member, project_id, agent_id)

    response = await ask(member, project_id, agent_id, conversation["id"], "How much leave?")

    # The Draft's reranker can't be built: the turn ends naming the rerank model, unanswered.
    assert parse_sse(response.text) == [
        ("error", {"code": "model_unavailable", "message": unavailable("rerank-2.5")})
    ]
