"""API seam: Live Verdicts (spec 15). An Editor sets an Agent's Live sample rate in its Operational
Settings; a Visitor reply in the widget is then chosen at random under that rate and judged in the
background by the Evaluation Model, and its Live Verdict (grounded, answers the question, with
reasons) shows in the reply's Trace in the Conversations viewer.

Replies come from a scripted ``FunctionModel`` through the real Guardrails and retrieval, and the
judge is the same model's structured-output path: the fake chat model's judge by rule
(``app.evaluation.fake_judge``) unless a test scripts its own Judgement. The judging task runs
eagerly after the widget reply, so a Live Verdict is final by the time the reply's stream ends. The
random draw is seeded by the test settings, so a sampled subset is stable from run to run.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents.config import DEFAULT_FALLBACK_TEXT
from app.credentials.registry import Provider
from app.evaluation import live
from app.gateway.fakes import FakeModelAdapters, fake_chat
from app.pricing.table import PriceEntry
from tests.agents import (
    AUTOMATIC,
    StreamFunction,
    agents_path,
    create_automatic_agent,
    parse_sse,
    save_draft,
)
from tests.conftest import ClientFactory, MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project, upload
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_archive import archive
from tests.integration.test_agent_versions import published
from tests.integration.test_bedrock_credentials import audit_events
from tests.integration.test_conversations import conversations_path, listed, playground_chat
from tests.integration.test_embed import conversation_token, send, settings_path
from tests.integration.test_evaluation_cost import PriceTable
from tests.integration.test_evaluation_cost import price_table as price_table
from tests.integration.test_evaluation_settings import set_evaluation_model
from tests.integration.test_input_guardrail import ATTACK, REFUSAL
from tests.integration.test_input_guardrail import RULE as GUARDRAIL_RULE
from tests.integration.test_playground import ANSWER, LEAVE, ready_agent, three_tokens
from tests.integration.test_provider_credentials import ANTHROPIC_KEY, OPENAI_KEY, added

RATE_CHANGED = "agent.live_sample_rate_changed"
SETTINGS_CHANGED = "agent.operational_settings_changed"
QUESTION = "How much annual leave do I get?"
PASSED = {"passed": True, "reason": "Fine."}


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


Judgement = Callable[[list[ModelMessage], AgentInfo], ModelResponse]
# A judge that awaits before it answers, as a slow one does.
AsyncJudgement = Callable[[list[ModelMessage], AgentInfo], Awaitable[ModelResponse]]


def scripted(
    app: FastAPI,
    stream: StreamFunction = three_tokens,
    judgement: Judgement | AsyncJudgement | None = None,
) -> list[tuple[Provider, str]]:
    """Every chat model answers by streaming ``stream`` and judges with ``judgement`` (by
    default, as the fake chat model judges). Returns every chat model built."""
    built: list[tuple[Provider, str]] = []

    def chat(provider: Provider, secret: str, model: str) -> FunctionModel:
        built.append((provider, model))
        fake = fake_chat(provider, secret, model)
        assert isinstance(fake, FunctionModel)
        assert fake.function is not None
        return FunctionModel(
            judgement or fake.function,
            stream_function=stream,
            model_name=model,
            profile={"supports_json_schema_output": False},
        )

    app.state.model_gateway.adapters = FakeModelAdapters(chat=chat)
    return built


def judged(grounding: dict[str, Any], answers_question: dict[str, Any]) -> Judgement:
    """A judge that gives these two Verdicts."""

    def judgement(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        verdicts = {"grounding": grounding, "answers_question": answers_question}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, verdicts)])

    return judgement


async def served(owner: SignedUpMember, project_id: str, agent_id: str) -> dict[str, Any]:
    """Publishes the Agent's Draft; the Agent, with its Project and the new Version."""
    version = await published(owner, project_id, agent_id)
    response = await owner.client.get(agents_path(owner, project_id, agent_id))
    assert response.status_code == 200, response.text
    return {**response.json(), "project_id": project_id, "version": version}


async def live_agent(app: FastAPI, owner: SignedUpMember) -> dict[str, Any]:
    """A published Automatic Agent over the leave policy, answered by the Default Model."""
    _, project_id, agent_id = await ready_agent(app, owner)
    return await served(owner, project_id, agent_id)


async def set_rate(member: SignedUpMember, agent: dict[str, Any], rate: Any) -> httpx.Response:
    return await member.client.patch(
        settings_path(member, agent["project_id"], agent["id"]), json={"live_sample_rate": rate}
    )


async def budgeted(owner: SignedUpMember, budget: str | None = "100") -> httpx.Response:
    """Sets the Organisation's monthly Evaluation budget, in US dollars (Owners only)."""
    return await owner.client.put(
        f"/api/organisations/{owner.organisation_id}/evaluation-budget",
        json={"evaluation_budget_usd": budget},
    )


async def sampling(owner: SignedUpMember, agent: dict[str, Any], rate: int) -> None:
    """Gives the Organisation an Evaluation budget, so replies can be sampled, and sets the
    Agent's Live sample rate."""
    assert (await budgeted(owner)).status_code == 200
    response = await set_rate(owner, agent, rate)
    assert response.status_code == 200, response.text


async def reply(
    visitor: httpx.AsyncClient, agent: dict[str, Any], question: str = QUESTION
) -> list[tuple[str, Any]]:
    """Asks the Agent in a new Visitor Conversation; the reply's events."""
    token = await conversation_token(visitor, agent["public_id"])
    response = await send(visitor, agent["public_id"], token, question)
    assert response.status_code == 200, response.text
    return parse_sse(response.text)


def message_id(events: list[tuple[str, Any]]) -> str:
    (done,) = [data for event, data in events if event == "done"]
    found: str = done["message_id"]
    return found


async def trace(member: SignedUpMember, agent: dict[str, Any], replied: str) -> dict[str, Any]:
    """The Trace of the reply, as the Conversations viewer reads it."""
    for conversation in (await listed(member, agent["project_id"], agent_id=agent["id"]))["items"]:
        response = await member.client.get(
            conversations_path(
                member, agent["project_id"], conversation["id"], "messages", replied, "trace"
            )
        )
        if response.status_code == 200:
            found: dict[str, Any] = response.json()
            return found
    raise AssertionError(f"No Trace for {replied}")


async def live_verdict(
    member: SignedUpMember, agent: dict[str, Any], events: list[tuple[str, Any]]
) -> dict[str, Any] | None:
    verdict: dict[str, Any] | None = (await trace(member, agent, message_id(events)))[
        "live_verdict"
    ]
    return verdict


# The Live sample rate


async def test_the_live_sample_rate_is_zero_by_default_and_editors_set_it_audited(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    agent = await live_agent(app, owner)
    path = settings_path(editor, agent["project_id"], agent["id"])
    assert (await budgeted(owner)).status_code == 200

    assert (await editor.client.get(path)).json()["live_sample_rate"] == 0
    response = await set_rate(editor, agent, 25)

    assert response.status_code == 200, response.text
    assert response.json()["live_sample_rate"] == 25
    assert (await owner.client.get(path)).json()["live_sample_rate"] == 25
    events = await audit_events(owner, RATE_CHANGED)
    assert [(e["actor"]["id"], e["before"], e["after"]) for e in events] == [
        (editor.member_id, {"live_sample_rate": 0}, {"live_sample_rate": 25})
    ]
    # It has its own Audit Event, not the general Operational Settings one.
    assert await audit_events(owner, SETTINGS_CHANGED) == []
    # Saving the rate in force records nothing more.
    assert (await set_rate(owner, agent, 25)).status_code == 200
    assert len(await audit_events(owner, RATE_CHANGED)) == 1


@pytest.mark.parametrize("rate", [-1, 101, 12.5, None, "half"])
async def test_the_live_sample_rate_is_a_whole_percentage(
    app: FastAPI, owner: SignedUpMember, rate: Any
) -> None:
    agent = await live_agent(app, owner)

    response = await set_rate(owner, agent, rate)

    assert response.status_code == 422, response.text
    path = settings_path(owner, agent["project_id"], agent["id"])
    assert (await owner.client.get(path)).json()["live_sample_rate"] == 0


# Sampling


async def test_at_zero_percent_no_reply_is_judged(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    built = scripted(app)
    agent = await live_agent(app, owner)

    events = await reply(visitor, agent)

    assert await live_verdict(owner, agent, events) is None
    # Only the reply's model was asked: nothing judged it.
    assert built == [(Provider.OPENAI, "gpt-4.1-mini")]


async def test_at_100_percent_a_visitor_reply_is_judged_and_shown_in_its_trace(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)
    editor = await member_factory(owner, "editor")

    events = await reply(visitor, agent)

    verdict = await live_verdict(editor, agent, events)
    assert verdict is not None
    assert verdict["status"] == "judged"
    # The fake judge: the reply cites [C1], and shares "annual" with the question.
    assert verdict["grounded"] == {
        "outcome": "pass",
        "reason": "Fake judge: the answer cites the knowledge base.",
        "review": None,
    }
    assert verdict["answers_question"] == {
        "outcome": "pass",
        "reason": "Fake judge: the answer shares “annual” with the question.",
        "review": None,
    }
    assert verdict["passed"] is True
    assert verdict["error_reason"] is None
    # The Default Model judges while the Organisation has no Evaluation Model.
    assert (verdict["judge_provider"], verdict["judge_model"]) == ("openai", "gpt-4.1-mini")
    # Attributed to the Version that answered, as the reply is.
    assert verdict["agent_version_id"] == agent["version"]["id"]
    assert verdict["input_tokens"] > 0
    assert verdict["output_tokens"] > 0


async def test_a_judged_reply_reaches_the_visitor_unchanged(
    app: FastAPI, owner: SignedUpMember, new_client: ClientFactory
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    unsampled = await reply(await new_client(), agent)

    await sampling(owner, agent, 100)
    sampled = await reply(await new_client(), agent)

    assert await live_verdict(owner, agent, sampled) is not None
    # Sampling and judging happen after the reply: the Visitor sees exactly the same events.
    without_ids = [(e, d) for e, d in unsampled if e != "done"]
    assert [(e, d) for e, d in sampled if e != "done"] == without_ids
    assert "".join(d["text"] for e, d in sampled if e == "token") == ANSWER


@pytest.mark.parametrize(
    ("grounding", "answers", "passed"),
    [
        ({"passed": False, "reason": "Claims a figure no excerpt gives."}, PASSED, False),
        (PASSED, {"passed": False, "reason": "Talks about pay, not leave."}, False),
        (PASSED, PASSED, True),
    ],
)
async def test_a_reply_passes_only_when_both_checks_pass_and_the_reasons_are_kept(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    grounding: dict[str, Any],
    answers: dict[str, Any],
    passed: bool,
) -> None:
    scripted(app, judgement=judged(grounding, answers))
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)

    verdict = await live_verdict(owner, agent, await reply(visitor, agent))

    assert verdict is not None
    outcome = {True: "pass", False: "fail"}
    assert verdict["grounded"] == {
        "outcome": outcome[grounding["passed"]],
        "reason": grounding["reason"],
        "review": None,
    }
    assert verdict["answers_question"] == {
        "outcome": outcome[answers["passed"]],
        "reason": answers["reason"],
        "review": None,
    }
    assert verdict["passed"] is passed


async def test_the_judge_gets_the_question_the_reply_and_the_chunks_given_with_cited_flags(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    seen: list[ModelMessage] = []
    judgement = judged(PASSED, PASSED)

    def recording(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.extend(messages)
        return judgement(messages, info)

    scripted(app, judgement=recording)
    agent = await live_agent(app, owner)
    saved = await save_draft(
        owner,
        agent["project_id"],
        agent["id"],
        {
            "retrieval": AUTOMATIC,
            "behaviour": {"system_prompt": "Secret house style: always say hello."},
        },
    )
    assert saved.status_code == 200, saved.text
    await published(owner, agent["project_id"], agent["id"])
    await sampling(owner, agent, 100)

    await reply(visitor, agent)

    asked = "\n".join(
        str(part.content) for message in seen for part in message.parts if hasattr(part, "content")
    )
    assert QUESTION in asked
    assert ANSWER in asked
    assert "Everyone gets 25 days of annual leave a year." in asked
    assert asked.rstrip().endswith("Judge: grounding, answers_question")
    # The judge never sees the Agent's system prompt.
    assert "Secret house style" not in asked


async def test_the_evaluation_model_judges_and_its_cost_is_frozen_on_the_live_verdict(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, price_table: PriceTable
) -> None:
    d = Decimal
    since = datetime(2020, 1, 1, tzinfo=UTC)
    await price_table(
        [
            PriceEntry(Provider.OPENAI, "gpt-4.1-mini", since, d(1), d(1), d(1)),
            PriceEntry(Provider.ANTHROPIC, "claude-haiku-4-5", since, d(2), d(4), d(1)),
        ]
    )
    built = scripted(app)
    agent = await live_agent(app, owner)
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY, name="Claude")
    response = await set_evaluation_model(owner, claude["id"], "claude-haiku-4-5")
    assert response.status_code == 200, response.text
    await sampling(owner, agent, 100)

    replied = await trace(owner, agent, message_id(await reply(visitor, agent)))

    verdict = replied["live_verdict"]
    assert (verdict["judge_provider"], verdict["judge_model"]) == ("anthropic", "claude-haiku-4-5")
    assert built[-1] == (Provider.ANTHROPIC, "claude-haiku-4-5")
    expected = (2 * d(verdict["input_tokens"]) + 4 * d(verdict["output_tokens"])) / 1_000_000
    assert d(verdict["cost_usd"]) == expected > 0
    # The reply's own Cost is the answering model's, untouched by judging.
    assert d(replied["cost_usd"]) == (replied["input_tokens"] + replied["output_tokens"]) / d(
        1_000_000
    )


async def test_a_judge_error_makes_the_live_verdict_an_error_and_the_reply_stands(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    def outage(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(status_code=503, model_name="gpt-4.1-mini")

    scripted(app, judgement=outage)
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)

    events = await reply(visitor, agent)

    assert "".join(d["text"] for e, d in events if e == "token") == ANSWER
    verdict = await live_verdict(owner, agent, events)
    assert verdict is not None
    assert verdict["status"] == "error"
    assert verdict["error_reason"].startswith("The Evaluation Model couldn't judge the answer")
    assert (verdict["grounded"], verdict["answers_question"], verdict["passed"]) == (
        None,
        None,
        None,
    )


async def test_without_an_evaluation_model_or_a_default_model_the_live_verdict_is_an_error(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    scripted(app)
    # The Agent answers with its own model; the Organisation has no Default Model to judge with.
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY)
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "leave.txt", LEAVE.encode())
    created = await create_automatic_agent(owner, project_id)
    saved = await save_draft(
        owner,
        project_id,
        created["id"],
        {
            "retrieval": AUTOMATIC,
            "behaviour": {"model": {"credential_id": openai["id"], "model": "gpt-4.1-mini"}},
        },
    )
    assert saved.status_code == 200, saved.text
    agent = await served(owner, project_id, created["id"])
    await sampling(owner, agent, 100)

    verdict = await live_verdict(owner, agent, await reply(visitor, agent))

    assert verdict is not None
    assert (verdict["status"], verdict["error_reason"], verdict["judge_model"]) == (
        "error",
        "The Organisation has neither an Evaluation Model nor a Default Model to judge with.",
        None,
    )


async def test_a_guardrail_block_and_the_fallback_text_are_never_sampled(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    built = scripted(app)
    app.state.guardrails.classifier.rules = [GUARDRAIL_RULE]
    _, project_id, agent_id = await ready_agent(app, owner)
    saved = await save_draft(
        owner,
        project_id,
        agent_id,
        {"retrieval": AUTOMATIC, "guardrails": {"input_mode": "block", "refusal_text": REFUSAL}},
    )
    assert saved.status_code == 200, saved.text
    guarded = await served(owner, project_id, agent_id)
    # An Agent over an empty Project replies to everything with its Fallback Text.
    empty_project = await create_project(owner)
    empty = await create_automatic_agent(owner, empty_project, "Empty helper")
    unknowing = await served(owner, empty_project, empty["id"])
    for agent in (guarded, unknowing):
        await sampling(owner, agent, 100)

    blocked = await reply(visitor, guarded, ATTACK)
    fallback = await reply(visitor, unknowing, QUESTION)

    assert ("refusal", {"text": REFUSAL}) in blocked
    assert ("token", {"text": DEFAULT_FALLBACK_TEXT}) in fallback
    assert await live_verdict(owner, guarded, blocked) is None
    assert await live_verdict(owner, unknowing, fallback) is None
    # Each reply readied its model, neither asked it, and nothing was built to judge them.
    assert built == [(Provider.OPENAI, "gpt-4.1-mini")] * 2


async def test_playground_replies_are_never_sampled(app: FastAPI, owner: SignedUpMember) -> None:
    built = scripted(app)
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)

    await playground_chat(owner, agent["project_id"], agent["id"], QUESTION)

    (conversation,) = (await listed(owner, agent["project_id"], playground=True))["items"]
    detail = await owner.client.get(
        conversations_path(owner, agent["project_id"], conversation["id"])
    )
    (answer,) = [m for m in detail.json()["messages"] if m["role"] == "assistant"]
    assert (await trace(owner, agent, answer["id"]))["live_verdict"] is None
    assert built == [(Provider.OPENAI, "gpt-4.1-mini")]


async def test_a_seeded_draw_samples_a_stable_subset(
    app: FastAPI, owner: SignedUpMember, new_client: ClientFactory
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 50)

    async def sampled() -> list[bool]:
        live.seed_draws(app.state.settings.live_sample_seed)
        found = []
        for _ in range(12):
            events = await reply(await new_client(), agent)
            found.append(await live_verdict(owner, agent, events) is not None)
        return found

    first = await sampled()

    assert 0 < sum(first) < len(first)
    assert await sampled() == first


async def test_an_archived_agents_replies_are_never_sampled(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    built = scripted(app)
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)
    token = await conversation_token(visitor, agent["public_id"])
    archived = await archive(owner, agent["project_id"], agent["id"])
    assert archived.status_code in (200, 204), archived.text

    response = await send(visitor, agent["public_id"], token, QUESTION)

    assert response.status_code == 404
    assert built == []


# Who can read them


async def test_another_organisations_live_verdicts_are_unreachable(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, tenant_factory: TenantFactory
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)
    events = await reply(visitor, agent)
    (conversation,) = (await listed(owner, agent["project_id"]))["items"]
    stranger = await tenant_factory()

    for organisation_id in (stranger.organisation_id, owner.organisation_id):
        path = (
            f"/api/organisations/{organisation_id}/projects/{agent['project_id']}/conversations/"
            f"{conversation['id']}/messages/{message_id(events)}/trace"
        )
        assert (await stranger.client.get(path)).status_code == 404
    # The stranger's own sample rate setting can't reach the Agent either.
    assert (await set_rate(stranger, agent, 100)).status_code == 404


async def test_the_live_verdict_records_when_it_was_judged(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    await sampling(owner, agent, 100)
    clock.advance(timedelta(hours=1))

    verdict = await live_verdict(owner, agent, await reply(visitor, agent))

    assert verdict is not None
    assert datetime.fromisoformat(verdict["judged_at"]) == clock.now()
