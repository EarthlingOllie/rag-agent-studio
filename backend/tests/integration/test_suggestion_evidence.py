"""API seam: a Suggestion run's evidence of every kind, retrieval changes, Knowledge Base gaps and
outcomes (spec 16, ticket 16-03).

Besides failed Live Verdicts, the evidence is the Live Version's Visitor replies with a
thumbs-down or in a Conversation rated 1 or 2, and the Evaluation Cases that failed on it in the
latest finished Evaluation Run with a side running it. A reply that qualifies several ways counts
once with all its reasons. Each reply's evidence carries its Remembered turns, its Live Verdict
reasons or Feedback, and a compact Trace. Evidence points and never copies, so after the Purge it
reads "Text purged" and a deleted case reads "Case deleted".

Visitor replies and Run answers come from a scripted ``FunctionModel``; judging and proposing are
the fake chat model's, unless a test scripts its own Proposal (as in ``test_suggestions``).
"""

import re
from datetime import timedelta
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents.config import TOP_K_MAX
from app.credentials.registry import Provider
from app.gateway.fakes import FakeModelAdapters, fake_chat
from app.suggestions.fake_proposer import GAP_TOPIC, is_proposing
from tests.agents import AUTOMATIC, parse_sse, save_draft
from tests.conftest import ClientFactory, SignedUpMember
from tests.documents import documents
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_versions import published
from tests.integration.test_agentic_retrieval import agentic_agent
from tests.integration.test_conversation_rating import rate
from tests.integration.test_conversations import conversations_path
from tests.integration.test_embed import conversation_token, send
from tests.integration.test_evaluation import add_case, evaluation_path
from tests.integration.test_evaluation_settings import set_repeats
from tests.integration.test_evaluation_sides import evaluated
from tests.integration.test_live_verdicts import sampling, served
from tests.integration.test_message_feedback import give
from tests.integration.test_playground import LEAVE, three_tokens
from tests.integration.test_retention import purge, set_window
from tests.integration.test_suggestions import (
    BASE_PROMPT,
    QUESTION,
    live_agent,
    prompts,
    proposal,
    replied,
    scripted,
    started,
    suggestions_path,
)
from tests.integration.test_version_metrics import roll_up


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


class Chat:
    """One Visitor Conversation with the Agent."""

    def __init__(self, visitor: httpx.AsyncClient, agent: dict[str, Any], token: str) -> None:
        self.visitor, self.agent, self.token = visitor, agent, token

    @classmethod
    async def opened(cls, visitor: httpx.AsyncClient, agent: dict[str, Any]) -> "Chat":
        return cls(visitor, agent, await conversation_token(visitor, agent["public_id"]))

    async def ask(self, question: str) -> str:
        """The reply's Message ID."""
        response = await send(self.visitor, self.agent["public_id"], self.token, question)
        assert response.status_code == 200, response.text
        event, data = parse_sse(response.text)[-1]
        assert event == "done", response.text
        found: str = data["message_id"]
        return found

    async def thumbs(self, message_id: str, rating: str, comment: str | None = None) -> None:
        body: dict[str, Any] = {"rating": rating}
        if comment is not None:
            body["comment"] = comment
        given = await give(self.visitor, self.agent["public_id"], self.token, message_id, **body)
        assert given.status_code == 200, given.text

    async def rate(self, score: int) -> None:
        rated = await rate(self.visitor, self.agent["public_id"], self.token, score)
        assert rated.status_code == 200, rated.text


def block(request: str, label: str) -> str:
    found = re.search(rf"<<<EVIDENCE {label}>>>\n(.*?)<<<END_EVIDENCE>>>", request, re.S)
    assert found is not None, label
    return found.group(1)


def kinds(suggestion: dict[str, Any]) -> list[tuple[str | None, list[str]]]:
    return [(e["message_id"], e["kinds"]) for e in suggestion["evidence"]]


# Every kind of evidence


async def test_thumbs_down_and_low_rated_replies_count_once_with_all_their_reasons(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    # Another Version's reply with a thumbs-down: never the Live Version's evidence.
    before = await Chat.opened(visitor, agent)
    await before.thumbs(await before.ask("How much leave?"), "down")
    newer = {"retrieval": AUTOMATIC, "behaviour": {"system_prompt": BASE_PROMPT}}
    assert (await save_draft(owner, agent["project_id"], agent["id"], newer)).status_code == 200
    await published(owner, agent["project_id"], agent["id"])
    # Fails its Live Verdict and has a thumbs-down with a comment.
    clock.advance(timedelta(minutes=1))
    both = await Chat.opened(visitor, agent)
    failed_and_down = await both.ask("How much annual leave do I get?")
    await both.thumbs(failed_and_down, "down", "That's the wrong number of days.")
    # From here on replies pass their Live Verdict.
    scripted(app, three_tokens)
    clock.advance(timedelta(minutes=1))
    down = await Chat.opened(visitor, agent)
    only_down = await down.ask("Can I carry leave over?")
    await down.thumbs(only_down, "down")
    # Both replies of a Conversation rated 1.
    clock.advance(timedelta(minutes=1))
    low = await Chat.opened(visitor, agent)
    first_low = await low.ask("How much sick leave?")
    clock.advance(timedelta(minutes=1))
    second_low = await low.ask("And annual leave for parents?")
    await low.rate(1)
    # Neither a thumbs-up nor a rating of 3 makes a reply evidence.
    clock.advance(timedelta(minutes=1))
    fine = await Chat.opened(visitor, agent)
    await fine.thumbs(await fine.ask("Where is the leave policy?"), "up")
    await fine.rate(3)
    # A reply not sampled for a Live Verdict, with a thumbs-down.
    await sampling(owner, agent, 0)
    clock.advance(timedelta(minutes=1))
    unjudged = await Chat.opened(visitor, agent)
    unjudged_id = await unjudged.ask("How much leave?")
    await unjudged.thumbs(unjudged_id, "down")
    proposing = scripted(app)

    suggestion = await started(owner, agent)

    assert kinds(suggestion)[0] == (unjudged_id, ["thumbs_down"])
    assert suggestion["evidence"][0]["live_verdict"] is None
    suggestion["evidence"] = suggestion["evidence"][1:]
    assert kinds(suggestion) == [
        (second_low, ["low_rating"]),
        (first_low, ["low_rating"]),
        (only_down, ["thumbs_down"]),
        (failed_and_down, ["live_verdict", "thumbs_down"]),
    ]
    assert [e["kind"] for e in suggestion["evidence"]] == [
        "low_rating",
        "low_rating",
        "thumbs_down",
        "live_verdict",
    ]
    assert [e["live_verdict"] for e in suggestion["evidence"]] == ["pass", "pass", "pass", "fail"]
    assert suggestion["evidence_total"] == 5
    # The model is told every reason, with the Visitor's comment as data.
    (messages,) = proposing
    request = prompts(messages, UserPromptPart)
    assert block(request, "E1").startswith("Kind: thumbs-down\nChunks cited: 1\n")
    assert block(request, "E2").startswith(
        "Kind: in a Conversation rated 1 of 5\nGrounding: pass. "
    )
    assert block(request, "E4").startswith("Kind: thumbs-down\nGrounding: pass. ")
    both_reasons = block(request, "E5")
    assert both_reasons.startswith("Kind: failed Live Verdict\nKind: thumbs-down\nGrounding: fail")
    assert (
        "<<<VISITOR_COMMENT>>>\nThat's the wrong number of days.\n<<<END_VISITOR_COMMENT>>>"
        in both_reasons
    )
    assert "<<<VISITOR_COMMENT>>>" not in block(request, "E4")


async def test_each_replys_evidence_holds_its_remembered_turns_and_a_compact_trace(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    proposing = scripted(app)
    agent = await live_agent(app, owner)
    chat = await Chat.opened(visitor, agent)
    await chat.ask("How much annual leave do I get?")
    clock.advance(timedelta(minutes=1))
    await chat.ask("And can I carry it over?")

    await started(owner, agent)

    (messages,) = proposing
    request = prompts(messages, UserPromptPart)
    follow_up = block(request, "E1")
    remembered = re.search(
        r"<<<REMEMBERED_TURNS>>>\n(.*?)\n<<<END_REMEMBERED_TURNS>>>", follow_up, re.S
    )
    assert remembered is not None
    assert remembered.group(1) == (
        "Visitor: How much annual leave do I get?\n"
        "Assistant: Everyone gets twenty-five days of annual leave a year."
    )
    assert "<<<VISITOR_QUESTION>>>\nAnd can I carry it over?\n" in follow_up
    # The run says how many Chunks the reply cited; the Trace lists each with its Relevance.
    assert "\nChunks cited: 0\n" in follow_up
    trace = re.search(r"<<<TRACE>>>\n(.*?)\n<<<END_TRACE>>>", follow_up, re.S)
    assert trace is not None
    assert re.fullmatch(r"\[C1\] not cited, relevance [\d.]+, leave\.txt: .+", trace.group(1))
    # The first reply had nothing to remember.
    assert "<<<REMEMBERED_TURNS>>>" not in block(request, "E2")


async def test_failed_cases_on_the_live_version_in_its_latest_run_are_evidence(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    proposing = scripted(app, three_tokens)
    agent = await live_agent(app, owner)
    project_id, agent_id = agent["project_id"], agent["id"]
    live_side = {"sides": [{"kind": "version", "version_id": agent["version"]["id"]}]}
    await set_repeats(owner, 1)
    await add_case(owner, project_id, agent_id, "How much leave?", 'You get "twenty-five days".')
    thirty = await add_case(owner, project_id, agent_id, "Leave?", 'You get "thirty days".')
    # An earlier Run of the Live Version: not the latest.
    await evaluated(owner, project_id, agent_id, live_side)
    # Cases with an Expected source, and Expect Fallback Text, that fail too.
    clock.advance(timedelta(minutes=1))
    (leave,) = await documents(owner, project_id)
    sourced = {
        "question": "Annual leave?",
        "reference_answer": 'It is "ten days".',
        "expected_sources": [{"document_id": leave["id"], "passage": LEAVE}],
    }
    path = evaluation_path(owner, project_id, agent_id, "cases")
    assert (await owner.client.post(path, json=sourced)).status_code == 201
    # Cases added at the same moment have no set order between them.
    clock.advance(timedelta(minutes=1))
    fallback = {"question": "Leave on the moon?", "expect_fallback": True}
    assert (await owner.client.post(path, json=fallback)).status_code == 201
    clock.advance(timedelta(hours=1))
    await add_case(owner, project_id, agent_id, "Parental leave?", 'Ask for "the form".')
    latest = await evaluated(owner, project_id, agent_id, live_side)
    # A later Run without the Live Version, and a Visitor reply that passes: neither is evidence.
    clock.advance(timedelta(hours=1))
    await evaluated(owner, project_id, agent_id, {"sides": [{"kind": "draft"}]})
    await replied(visitor, agent)

    suggestion = await started(owner, agent)

    run_cases = {c["question"]: c["id"] for c in latest["cases"]}
    failing = ["Leave?", "Annual leave?", "Leave on the moon?", "Parental leave?"]
    assert [
        (e["kind"], e["kinds"], e["evaluation_run_id"], e["run_case_id"], e["message_id"])
        for e in suggestion["evidence"]
    ] == [
        ("evaluation_case", ["evaluation_case"], latest["run"]["id"], run_cases[q], None)
        for q in failing
    ]
    assert [e["occurred_at"] for e in suggestion["evidence"]] == [latest["run"]["finished_at"]] * 4
    assert all(e["case_deleted"] is False for e in suggestion["evidence"])
    # The model gets the case's question, its expectations, the answer, its Verdicts' reasons
    # and its Trace.
    (messages,) = proposing
    case = block(prompts(messages, UserPromptPart), "E1")
    assert case.startswith("Kind: failed Evaluation Case\nRepeats passed: 0 of 1 answered\n")
    assert "Reference answer: fail. Fake judge: the answer lacks “thirty days”." in case
    assert "<<<CASE_QUESTION>>>\nLeave?\n<<<END_CASE_QUESTION>>>" in case
    assert '<<<EXPECTATIONS>>>\nReference answer: You get "thirty days".\n' in case
    assert "<<<REPLY>>>\nEveryone gets twenty-five days of annual leave a year, see [C1].\n" in case
    assert "\nChunks cited: 1\n" in case
    assert re.search(r"<<<TRACE>>>\n\[C1\] cited, relevance [\d.]+, leave\.txt: ", case)
    request = prompts(messages, UserPromptPart)
    assert (
        '<<<EXPECTATIONS>>>\nReference answer: It is "ten days".\n'
        f"Expected source, leave.txt: {LEAVE}\n<<<END_EXPECTATIONS>>>"
    ) in block(request, "E2")
    assert "<<<EXPECTATIONS>>>\nExpects the Fallback Text.\n<<<END_EXPECTATIONS>>>" in block(
        request, "E3"
    )

    # A deleted case reads "Case deleted"; the Run keeps its copy.
    path = evaluation_path(owner, project_id, agent_id, "cases", thirty["id"])
    assert (await owner.client.delete(path)).status_code == 204
    read = (await owner.client.get(suggestions_path(owner, agent, suggestion["id"]))).json()
    assert [e["case_deleted"] for e in read["evidence"]] == [True, False, False, False]
    assert read["evidence"][0]["run_case_id"] == run_cases["Leave?"]


# Retrieval changes, gaps and outcomes


async def test_retrieval_changes_within_range_that_cite_evidence_are_kept(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    proposing = scripted(
        app,
        proposer=proposal(
            [
                {"path": "retrieval.top_k", "value": 8, "explanation": "More.", "evidence": ["E1"]},
                # Out of range.
                {
                    "path": "retrieval.minimum_score",
                    "value": 1.5,
                    "explanation": "x",
                    "evidence": ["E1"],
                },
                # Citing no evidence, or none that was given.
                {"path": "retrieval.minimum_score", "value": 0.2, "explanation": "x"},
                {
                    "path": "retrieval.minimum_score",
                    "value": 0.2,
                    "explanation": "x",
                    "evidence": ["E9"],
                },
                {
                    "path": "retrieval.hybrid_weighting",
                    "value": 0.3,
                    "explanation": "Lean on keywords.",
                    "evidence": ["E1", "E9"],
                },
                {"path": "retrieval.top_k", "value": TOP_K_MAX + 1, "explanation": "x"},
            ]
        ),
    )
    agent = await live_agent(app, owner)
    await replied(visitor, agent)

    suggestion = await started(owner, agent)

    (evidence,) = suggestion["evidence"]
    assert suggestion["outcome"] == "changes"
    assert [
        (c["path"], c["base_value"], c["suggested_value"], c["explanation"], c["evidence_ids"])
        for c in suggestion["changes"]
    ] == [
        ("retrieval.top_k", 5, 8, "More.", [evidence["id"]]),
        ("retrieval.hybrid_weighting", 0.5, 0.3, "Lean on keywords.", [evidence["id"]]),
    ]
    # The model is given each retrieval setting with its valid range.
    (messages,) = proposing
    request = prompts(messages, UserPromptPart)
    assert "retrieval.top_k = 5 (Top-k, how many Chunks are given to the model: a whole " in (
        request
    )
    assert f"number from 1 to {TOP_K_MAX})" in request
    assert "retrieval.minimum_score = 0.0 (" in request
    assert "retrieval.hybrid_weighting = 0.5 (" in request


async def test_knowledge_base_gaps_alone_are_no_configuration_change(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    gaps = [
        {
            "topic": "Parental leave",
            "explanation": "Visitors asked about parental leave and no Chunk covered it.",
            "evidence": ["E1", "E7"],
        },
        {"topic": "Sabbaticals", "explanation": "Nothing on sabbaticals."},
    ]

    def with_gaps(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        output = {
            "changes": [],
            "gaps": gaps,
            "overall_explanation": "The knowledge base lacks parental leave.",
        }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    scripted(app, proposer=with_gaps)
    agent = await live_agent(app, owner)
    await replied(visitor, agent)

    suggestion = await started(owner, agent)

    (evidence,) = suggestion["evidence"]
    assert (suggestion["outcome"], suggestion["changes"]) == ("gaps_only", [])
    assert suggestion["explanation"] == "The knowledge base lacks parental leave."
    assert [(g["topic"], g["explanation"], g["evidence_ids"]) for g in suggestion["gaps"]] == [
        (
            "Parental leave",
            "Visitors asked about parental leave and no Chunk covered it.",
            [evidence["id"]],
        ),
        ("Sabbaticals", "Nothing on sabbaticals.", []),
    ]


async def test_the_fake_proposer_reports_a_gap_with_its_change(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    replied_id = await replied(visitor, agent)

    suggestion = await started(owner, agent)

    assert suggestion["outcome"] == "changes"
    (evidence,) = suggestion["evidence"]
    assert evidence["message_id"] == replied_id
    assert [(g["topic"], g["evidence_ids"]) for g in suggestion["gaps"]] == [
        (GAP_TOPIC, [evidence["id"]])
    ]


async def test_the_fake_proposer_lowers_a_minimum_score_a_chunk_just_missed(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    scripted(app)
    agent = await live_agent(app, owner)
    # The leave Chunk's Relevance for the question, from a reply of the Version before.
    await replied(visitor, agent)
    (first,) = (await started(owner, agent))["evidence"]
    path = conversations_path(
        owner, agent["project_id"], first["conversation_id"], "messages", first["message_id"]
    )
    trace = await owner.client.get(f"{path}/trace")
    assert trace.status_code == 200, trace.text
    (chunk,) = trace.json()["chunks"]
    # The Live Version's Minimum Score sits just above it, so the Chunk is excluded and the
    # reply is the Fallback Text (never judged), which the Visitor gives a thumbs-down.
    minimum = round(chunk["relevance"] + 0.03, 2)
    draft = {
        "retrieval": {**AUTOMATIC, "min_score": minimum},
        "behaviour": {"system_prompt": BASE_PROMPT},
    }
    assert (await save_draft(owner, agent["project_id"], agent["id"], draft)).status_code == 200
    await published(owner, agent["project_id"], agent["id"])
    clock.advance(timedelta(minutes=1))
    chat = await Chat.opened(visitor, agent)
    missed = await chat.ask(QUESTION)
    await chat.thumbs(missed, "down")

    suggestion = await started(owner, agent)

    (evidence,) = suggestion["evidence"]
    assert evidence["message_id"] == missed
    assert [
        (c["path"], c["base_value"], c["suggested_value"], c["evidence_ids"])
        for c in suggestion["changes"]
    ] == [("retrieval.minimum_score", minimum, round(minimum - 0.05, 2), [evidence["id"]])]


# Retention


async def test_after_the_purge_evidence_reads_text_purged_and_the_suggestion_is_intact(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    proposing = scripted(app)
    agent = await live_agent(app, owner)
    assert (await set_window(owner, 7)).status_code == 200
    chat = await Chat.opened(visitor, agent)
    old = await chat.ask("How much annual leave do I get?")
    before = await started(owner, agent)
    assert before["evidence"][0]["text_purged"] is False
    # A follow-up in the same Conversation a day later; at the Purge, a week after the first
    # reply, only the first is older than the Retention Window.
    clock.advance(timedelta(hours=23))
    follow_up = await chat.ask("Can I carry annual leave over?")
    clock.advance(timedelta(days=6, hours=2))
    await roll_up(clock.now())

    await purge(clock.now())

    read = await owner.client.get(suggestions_path(owner, agent, before["id"]))
    assert read.status_code == 200, read.text
    after = read.json()
    (evidence,) = after["evidence"]
    assert (evidence["message_id"], evidence["text_purged"], evidence["live_verdict"]) == (
        old,
        True,
        "fail",
    )
    assert evidence["occurred_at"] == before["evidence"][0]["occurred_at"]
    assert (after["changes"], after["gaps"], after["explanation"]) == (
        before["changes"],
        before["gaps"],
        before["explanation"],
    )
    # A new run over the same days leaves the Purged reply out; the follow-up's Remembered turn
    # reads as purged.
    again = await started(owner, agent, range_start=str((clock.now() - timedelta(days=13)).date()))
    assert [e["message_id"] for e in again["evidence"]] == [follow_up]
    remembered = re.search(
        r"<<<REMEMBERED_TURNS>>>\n(.*?)\n<<<END_REMEMBERED_TURNS>>>",
        prompts(proposing[-1], UserPromptPart),
        re.S,
    )
    assert remembered is not None
    assert remembered.group(1) == "Visitor: [Text purged]\nAssistant: [Text purged]"


# Agentic Retrieval Mode


def recorded_fakes(app: FastAPI) -> list[list[ModelMessage]]:
    """The fake chat model throughout, as docker compose runs it; returns the messages of every
    proposing call."""
    proposing: list[list[ModelMessage]] = []

    def chat(provider: Provider, secret: str, model: str) -> FunctionModel:
        fake = fake_chat(provider, secret, model)
        assert isinstance(fake, FunctionModel)
        assert fake.function is not None
        assert fake.stream_function is not None
        function, stream = fake.function, fake.stream_function

        def complete(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if is_proposing(info):
                proposing.append(messages)
            return cast(ModelResponse, function(messages, info))

        return FunctionModel(
            complete,
            stream_function=stream,
            model_name=model,
            profile={"supports_json_schema_output": False},
        )

    app.state.model_gateway.adapters = FakeModelAdapters(chat=chat)
    return proposing


async def test_an_agentic_replys_and_cases_searches_are_in_their_traces(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    proposing = recorded_fakes(app)
    project_id, agent_id = await agentic_agent(app, owner)
    agent = await served(owner, project_id, agent_id)
    await sampling(owner, agent, 100)
    await set_repeats(owner, 1)
    await add_case(owner, project_id, agent_id, "Leave?", 'You get "thirty days".')
    live_side = {"sides": [{"kind": "version", "version_id": agent["version"]["id"]}]}
    await evaluated(owner, project_id, agent_id, live_side)
    clock.advance(timedelta(minutes=1))
    # The fake model's reply doesn't answer the question, so its Live Verdict fails.
    await replied(visitor, agent, "How much annual leave do I get?")

    suggestion = await started(owner, agent)

    assert [e["kind"] for e in suggestion["evidence"]] == ["live_verdict", "evaluation_case"]
    (messages,) = proposing
    request = prompts(messages, UserPromptPart)
    for label, query in (("E1", "How much annual leave do I get?"), ("E2", "Leave?")):
        trace = re.search(r"<<<TRACE>>>\n(.*?)\n<<<END_TRACE>>>", block(request, label), re.S)
        assert trace is not None
        assert re.fullmatch(
            rf"Search 1: {re.escape(query)}\n\[C1\] cited, relevance [\d.]+, leave\.txt: .+",
            trace.group(1),
        )
