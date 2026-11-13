"""API seam: an Agent in Agentic Retrieval Mode (ADR-0015) answers in the Playground.

The Retrieval Mode is set through the Draft API. The chat model is a scripted Pydantic AI
``FunctionModel`` that calls Knowledge Search with the queries it is given, one per model call,
then answers; or the default fake chat model, as ``docker compose`` and end-to-end runs use it.
Everything is observed as the Studio sees it: the Server-Sent Events stream, then the Trace and
the Conversation read back through the API."""

import json
from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, DeltaToolCalls
from sqlalchemy import text

from app.gateway.fakes import FakeModelAdapters
from tests.agents import (
    answer_with,
    ask,
    create_agent,
    create_automatic_agent,
    parse_sse,
    save_draft,
    start_conversation,
    trace_path,
    use_default_model,
)
from tests.conftest import ClientFactory, MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project, project_path, upload
from tests.integration.test_agent_versions import knowledgeable_project, published
from tests.integration.test_embed import conversation_token, send
from tests.integration.test_playground import LEAVE
from tests.integration.test_tag_scoping import tag
from tests.integration.test_token_budget import usage
from tests.knowledge_base import (
    EXPENSES,
    PRODUCT,
    PRODUCT_QUESTION,
    UNRELATED_QUESTION,
    knowledge_base,
)

Script = Callable[[list[ModelMessage], AgentInfo], AsyncIterator[str | DeltaToolCalls]]

SECRET = "The launch code for Project Falcon is 7781."
RIVAL = "Rival Inc offers a ten-year warranty on SKU-4471."


def _searches_made(messages: list[ModelMessage]) -> int:
    return sum(
        isinstance(part, ToolReturnPart)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
    )


def _search_results(messages: list[ModelMessage]) -> list[str]:
    """What each Knowledge Search returned to the model, in order."""
    return [
        str(part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]


def recorded(script: Script, calls: list[list[ModelMessage]]) -> Script:
    """``script``, appending the messages of each model call to ``calls``."""

    def record(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | DeltaToolCalls]:
        calls.append(list(messages))
        return script(messages, info)

    return record


def searching(*queries: str, answer: str) -> Script:
    """A model that calls Knowledge Search once per call with each query in turn, then streams
    ``answer``."""

    async def script(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | DeltaToolCalls]:
        made = _searches_made(messages)
        if made < len(queries):
            (tool,) = info.function_tools
            args = json.dumps({"query": queries[made]})
            yield {0: DeltaToolCall(name=tool.name, json_args=args, tool_call_id=f"call-{made}")}
            return
        yield answer

    return script


async def agentic(member: SignedUpMember, project_id: str, agent_id: str, **retrieval: Any) -> None:
    """Sets the Agent's Retrieval Mode to Agentic through the Draft API."""
    saved = await save_draft(
        member, project_id, agent_id, {"retrieval": {"mode": "agentic", **retrieval}}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["draft"]["retrieval"]["mode"] == "agentic"


async def agentic_agent(app: FastAPI, owner: SignedUpMember) -> tuple[str, str]:
    """An Organisation with a Default Model, and a Project with the leave policy and an Agentic
    Agent; returns the Project and Agent IDs."""
    await use_default_model(owner)
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "leave.txt", LEAVE.encode())
    agent_id = (await create_agent(owner, project_id))["id"]
    await agentic(owner, project_id, agent_id)
    return project_id, agent_id


async def asked(
    member: SignedUpMember, project_id: str, agent_id: str, question: str
) -> tuple[list[tuple[str, Any]], dict[str, Any]]:
    """Asks ``question`` in a new Playground Conversation; returns the stream's events and the
    answer's Trace."""
    conversation = await start_conversation(member, project_id, agent_id)
    response = await ask(member, project_id, agent_id, conversation["id"], question)
    assert response.status_code == 200, response.text
    events = parse_sse(response.text)
    kind, done = events[-1]
    assert kind == "done", events
    trace = await member.client.get(
        trace_path(member, project_id, agent_id, conversation["id"], done["message_id"])
    )
    assert trace.status_code == 200, trace.text
    return events, trace.json()


async def test_the_model_searches_the_search_streams_and_the_answer_cites_what_it_found(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    answer_with(app, searching("annual leave policy", answer="You get 25 days [C1]."))
    editor = await member_factory(owner, "editor")
    await use_default_model(owner)
    project_id = await create_project(editor)
    await upload(app, editor, project_id, "leave.txt", LEAVE.encode())
    agent_id = (await create_agent(editor, project_id))["id"]
    await agentic(editor, project_id, agent_id)

    events, trace = await asked(editor, project_id, agent_id, "How much leave do I get?")

    # The Search is streamed as it starts, with the query the model wrote, before the answer.
    assert events[0] == ("search", {"query": "annual leave policy", "order": 1})
    assert [event for event, _ in events[1:]] == ["token", "citation", "done"]
    assert events[1][1] == {"text": "You get 25 days [C1]."}
    citation = events[2][1]
    assert (citation["label"], citation["document_name"]) == ("C1", "leave.txt")
    done = events[3][1]
    assert done["search_count"] == 1
    assert [(c["rank"], c["chunk_id"]) for c in done["chunks"]] == [(1, citation["chunk_id"])]
    # The Trace lists the Search, with the Chunk it found nested under it.
    assert trace["search_count"] == 1
    assert trace["chunks"] == []
    (search,) = trace["searches"]
    assert (search["order"], search["query"], search["limit_refused"]) == (
        1,
        "annual leave policy",
        False,
    )
    assert search["latency_ms"] >= 0
    (chunk,) = search["chunks"]
    assert (chunk["text"], chunk["document_name"], chunk["rank"]) == (LEAVE, "leave.txt", 1)
    assert (chunk["cited"], chunk["excluded_reason"]) == (True, None)
    assert trace["fallback"] is False


async def test_token_use_and_cost_are_summed_over_every_model_call(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, searching("annual leave", answer="Twenty-five days [C1]."))
    project_id, agent_id = await agentic_agent(app, owner)

    events, trace = await asked(owner, project_id, agent_id, "Leave?")

    # Two model calls: the one that searched, then the one that answered. The FunctionModel
    # counts 50 input tokens per streamed call, and as output the pieces (words and
    # punctuation) of what it sends: the search call's arguments, {"query": "annual leave"}
    # (5), and the answer (4).
    assert (trace["input_tokens"], trace["output_tokens"]) == (100, 9)
    done = events[-1][1]
    assert (done["input_tokens"], done["output_tokens"]) == (100, 9)
    # Priced from the sums with the platform price table: GPT-4.1 mini is $0.40 per million
    # input tokens and $1.60 per million output tokens.
    assert Decimal(trace["cost_usd"]) == Decimal("0.0000544")


async def test_a_greeting_needs_no_search(app: FastAPI, owner: SignedUpMember) -> None:
    answer_with(app, searching(answer="Hello! How can I help?"))
    project_id, agent_id = await agentic_agent(app, owner)

    events, trace = await asked(owner, project_id, agent_id, "Hi there")

    assert [event for event, _ in events] == ["token", "done"]
    assert events[-1][1]["search_count"] == 0
    assert (trace["search_count"], trace["searches"], trace["chunks"]) == (0, [], [])
    assert trace["fallback"] is False
    assert trace["model_name"] == "gpt-4.1-mini"


async def test_model_written_queries_stay_inside_the_agents_tags_and_project(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    tenant_factory: TenantFactory,
) -> None:
    editor = await member_factory(owner, "editor")
    await use_default_model(owner)
    project_id = await knowledge_base(app, editor)
    hr = await tag(editor, project_id, "HR", ["leave.txt", "expenses.txt"])
    # Material the Agent must never reach: another Project of the Organisation, and another
    # Organisation's Project.
    other_project = await create_project(editor, "Launches")
    await upload(app, editor, other_project, "secret.txt", SECRET.encode())
    rival = await tenant_factory()
    rival_project = await create_project(rival, "Rival")
    await upload(app, rival, rival_project, "rival.txt", RIVAL.encode())
    agent_id = (await create_agent(editor, project_id))["id"]
    await agentic(editor, project_id, agent_id, tag_ids=[hr], top_k=3)
    # The model asks for the product (another Tag), the other Project's secret and the rival's
    # text, word for word.
    answer_with(app, searching(PRODUCT_QUESTION, SECRET, RIVAL, answer="I can't say."))

    events, trace = await asked(editor, project_id, agent_id, "Tell me everything.")

    assert [data["query"] for event, data in events if event == "search"] == [
        PRODUCT_QUESTION,
        SECRET,
        RIVAL,
    ]
    searches = trace["searches"]
    assert [s["query"] for s in searches] == [PRODUCT_QUESTION, SECRET, RIVAL]
    found = [chunk for search in searches for chunk in search["chunks"]]
    given = {c["text"] for c in found if c["excluded_reason"] is None}
    # Only the Agent's own Tags' material is given to the model, whatever the query.
    assert given <= {LEAVE, EXPENSES}
    assert given
    # The product matched the first query best: Tag scoping left it out, as the Trace says.
    outside = [c["text"] for c in searches[0]["chunks"] if c["excluded_reason"] == "outside_tags"]
    assert outside[0] == PRODUCT
    # Nothing from another Project or another Organisation is found at all.
    names = {c["document_name"] for c in found}
    assert names.isdisjoint({"secret.txt", "rival.txt"})
    assert {c["text"] for c in found}.isdisjoint({SECRET, RIVAL})


async def test_the_default_fake_chat_model_searches_once_with_the_visitors_question(
    app: FastAPI, owner: SignedUpMember
) -> None:
    # No scripted model: the fake adapters, as docker compose and end-to-end runs use them.
    app.state.model_gateway.adapters = FakeModelAdapters()
    project_id, agent_id = await agentic_agent(app, owner)

    events, trace = await asked(owner, project_id, agent_id, LEAVE)

    assert events[0] == ("search", {"query": LEAVE, "order": 1})
    answer = "".join(data["text"] for event, data in events if event == "token")
    assert answer == "Fake reply from openai:gpt-4.1-mini. [C1]"
    assert [data["label"] for event, data in events if event == "citation"] == ["C1"]
    (search,) = trace["searches"]
    assert search["query"] == LEAVE
    assert [(c["text"], c["cited"]) for c in search["chunks"]] == [(LEAVE, True)]


async def test_the_default_fake_chat_model_answers_without_searching_in_automatic_mode(
    app: FastAPI, owner: SignedUpMember
) -> None:
    app.state.model_gateway.adapters = FakeModelAdapters()
    await use_default_model(owner)
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "leave.txt", LEAVE.encode())
    agent_id = (await create_automatic_agent(owner, project_id))["id"]

    events, trace = await asked(owner, project_id, agent_id, LEAVE)

    assert "search" not in {event for event, _ in events}
    assert (trace["search_count"], trace["searches"]) == (0, [])
    assert [(c["text"], c["rank"], c["cited"]) for c in trace["chunks"]] == [(LEAVE, 1, True)]


async def test_a_provider_error_after_a_search_ends_with_a_typed_error_event(
    app: FastAPI, owner: SignedUpMember
) -> None:
    async def fails_after_searching(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | DeltaToolCalls]:
        if not _searches_made(messages):
            args = json.dumps({"query": "leave"})
            yield {0: DeltaToolCall(name="knowledge_search", json_args=args, tool_call_id="1")}
            return
        raise ModelHTTPError(status_code=503, model_name="gpt-4.1-mini")

    answer_with(app, fails_after_searching)
    project_id, agent_id = await agentic_agent(app, owner)
    conversation = await start_conversation(owner, project_id, agent_id)

    response = await ask(owner, project_id, agent_id, conversation["id"], "Leave?")

    events = parse_sse(response.text)
    assert [event for event, _ in events] == ["search", "error"]
    assert events[-1][1]["code"] == "provider_error"
    saved = await owner.client.get(
        f"{project_path(owner, project_id)}/agents/{agent_id}/playground/conversations/"
        f"{conversation['id']}"
    )
    # No answer is saved.
    assert [m["role"] for m in saved.json()["messages"]] == ["user"]


async def test_a_visitor_of_an_agentic_live_version_gets_an_answer_and_its_search_is_traced(
    app: FastAPI, owner: SignedUpMember, new_client: ClientFactory
) -> None:
    project_id = await knowledgeable_project(app, owner)
    answer_with(app, searching("annual leave", answer="Leave is 25 days [C1]."))
    created = await create_agent(owner, project_id)
    await agentic(owner, project_id, created["id"])
    await published(owner, project_id, created["id"])
    visitor: httpx.AsyncClient = await new_client()
    token = await conversation_token(visitor, created["public_id"])

    response = await send(visitor, created["public_id"], token, "How much leave?")

    events = parse_sse(response.text)
    answer = "".join(data["text"] for event, data in events if event == "token")
    assert answer == "Leave is 25 days [C1]."
    assert [data["label"] for event, data in events if event == "citation"] == ["C1"]
    assert events[-1][0] == "done"
    message_id = events[-1][1]["message_id"]
    async with app.state.sessionmaker() as session:
        conversation_id = await session.scalar(
            text("SELECT conversation_id::text FROM messages WHERE id = :id"), {"id": message_id}
        )
    # The Studio's Trace of the Visitor's answer lists the Search.
    trace = await owner.client.get(
        f"{project_path(owner, project_id)}/conversations/{conversation_id}/messages/"
        f"{message_id}/trace"
    )
    assert trace.status_code == 200, trace.text
    (search,) = trace.json()["searches"]
    assert search["query"] == "annual leave"
    assert [(c["document_name"], c["cited"]) for c in search["chunks"]] == [("leave.txt", True)]


async def test_searches_the_model_makes_at_once_each_run_and_are_traced(
    app: FastAPI, owner: SignedUpMember
) -> None:
    async def searches_twice_at_once(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | DeltaToolCalls]:
        if _searches_made(messages):
            yield "Leave is 25 days [C1]; claim expenses within 30 days [C2]."
            return
        # Both Knowledge Searches in one model response.
        yield {
            0: DeltaToolCall(name="knowledge_search", json_args='{"query": "' + LEAVE + '"}'),
            1: DeltaToolCall(name="knowledge_search", json_args='{"query": "' + EXPENSES + '"}'),
        }

    answer_with(app, searches_twice_at_once)
    await use_default_model(owner)
    project_id = await knowledge_base(app, owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await agentic(owner, project_id, agent_id, top_k=1)

    events, trace = await asked(owner, project_id, agent_id, "Leave and expenses?")

    assert sorted(data["query"] for event, data in events if event == "search") == sorted(
        [LEAVE, EXPENSES]
    )
    cited = [(d["label"], d["document_name"]) for event, d in events if event == "citation"]
    assert cited == [("C1", "leave.txt"), ("C2", "expenses.txt")]
    assert trace["search_count"] == 2
    found = {
        search["query"]: [c["text"] for c in search["chunks"] if c["excluded_reason"] is None]
        for search in trace["searches"]
    }
    assert found == {LEAVE: [LEAVE], EXPENSES: [EXPENSES]}


async def test_text_the_model_writes_before_searching_is_retracted_and_kept_out_of_the_answer(
    app: FastAPI, owner: SignedUpMember
) -> None:
    async def says_it_will_search(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | DeltaToolCalls]:
        if _searches_made(messages):
            yield "You get 25 days [C1]."
            return
        yield "Let me search the knowledge base."
        args = json.dumps({"query": "annual leave"})
        yield {1: DeltaToolCall(name="knowledge_search", json_args=args, tool_call_id="1")}

    answer_with(app, says_it_will_search)
    project_id, agent_id = await agentic_agent(app, owner)

    events, trace = await asked(owner, project_id, agent_id, "How much leave do I get?")

    # The model searches although it wrote text first. That text streamed, so it is retracted
    # before the Search (ticket 13-10), and only the answer that follows is kept.
    names = [event for event, _ in events]
    retract = names.index("retract")
    assert events[retract + 1] == ("search", {"query": "annual leave", "order": 1})
    assert set(names[:retract]) == {"token"}
    answer = "".join(data["text"] for event, data in events[retract:] if event == "token")
    assert answer == "You get 25 days [C1]."
    assert [data["label"] for event, data in events if event == "citation"] == ["C1"]
    assert trace["search_count"] == 1


async def test_a_structured_output_model_searches_then_answers_with_citations_alone(
    app: FastAPI, owner: SignedUpMember
) -> None:
    async def searches_then_cites(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | DeltaToolCalls]:
        if _searches_made(messages):
            yield '{"answer": "You get 25 days.", '
            yield '"citations": ["C1"]}'
            return
        yield "I'll look that up."
        args = json.dumps({"query": "annual leave"})
        yield {1: DeltaToolCall(name="knowledge_search", json_args=args, tool_call_id="1")}

    answer_with(app, searches_then_cites, structured=True)
    project_id, agent_id = await agentic_agent(app, owner)

    events, _ = await asked(owner, project_id, agent_id, "How much leave do I get?")

    assert events[0] == ("search", {"query": "annual leave", "order": 1})
    answer = "".join(data["text"] for event, data in events if event == "token")
    assert answer == "You get 25 days."
    assert [data["label"] for event, data in events if event == "citation"] == ["C1"]


async def test_a_chunk_one_search_left_out_and_another_gave_is_not_listed_as_left_out(
    app: FastAPI, owner: SignedUpMember
) -> None:
    # Top-k 1: the first Search gives LEAVE and leaves EXPENSES out; the second gives EXPENSES.
    answer_with(app, searching(LEAVE, EXPENSES, answer="See [C1] and [C2]."))
    await use_default_model(owner)
    project_id = await knowledge_base(app, owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await agentic(owner, project_id, agent_id, top_k=1)

    events, trace = await asked(owner, project_id, agent_id, "Leave and expenses?")

    done = events[-1][1]
    given = [c["chunk_id"] for c in done["chunks"]]
    left_out = [e["chunk_id"] for e in done["excluded"]]
    assert len(given) == 2
    assert set(given).isdisjoint(left_out)
    assert len(left_out) == len(set(left_out))
    # Each Search's own Trace still says what it left out.
    first = trace["searches"][0]
    assert EXPENSES in [c["text"] for c in first["chunks"] if c["excluded_reason"] is not None]


async def test_a_search_beyond_the_search_limit_is_refused_and_the_reply_still_answers(
    app: FastAPI, owner: SignedUpMember
) -> None:
    calls: list[list[ModelMessage]] = []
    answer_with(
        app,
        recorded(searching("leave", "annual leave", "holidays", answer="25 days [C1]."), calls),
    )
    project_id, agent_id = await agentic_agent(app, owner)
    await agentic(owner, project_id, agent_id, search_limit=2)

    events, trace = await asked(owner, project_id, agent_id, "How much leave?")

    # Only the Searches within the limit run, so only they stream.
    assert [data for event, data in events if event == "search"] == [
        {"query": "leave", "order": 1},
        {"query": "annual leave", "order": 2},
    ]
    # The third call is refused, and the model told to answer from what it has.
    *_, refused = _search_results(calls[-1])
    assert refused == "search limit reached; answer from what you have"
    # The reply still answers, citing what the first Searches found.
    answer = "".join(data["text"] for event, data in events if event == "token")
    assert answer == "25 days [C1]."
    assert [data["label"] for event, data in events if event == "citation"] == ["C1"]
    done = events[-1][1]
    assert (done["fallback"], done["search_count"]) == (False, 2)
    # The Trace shows the limit was hit: the refused call, which searched nothing.
    assert trace["search_count"] == 2
    assert [(s["order"], s["query"], s["limit_refused"]) for s in trace["searches"]] == [
        (1, "leave", False),
        (2, "annual leave", False),
        (3, "holidays", True),
    ]
    assert trace["searches"][2]["chunks"] == []
    assert trace["fallback"] is False


async def test_searched_and_found_nothing_gives_the_fallback_text_and_no_answer_tokens(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, searching(UNRELATED_QUESTION, answer="The canteen serves soup."))
    await use_default_model(owner)
    project_id = await knowledge_base(app, owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    saved = await save_draft(
        owner,
        project_id,
        agent_id,
        {
            "behaviour": {"fallback_text": "Ask HR, please."},
            "retrieval": {"mode": "agentic", "min_score": 0.3},
        },
    )
    assert saved.status_code == 200, saved.text

    events, trace = await asked(owner, project_id, agent_id, UNRELATED_QUESTION)

    # The model's answer is never streamed: the Fallback Text is the only token.
    assert [event for event, _ in events] == ["search", "token", "done"]
    assert events[1][1] == {"text": "Ask HR, please."}
    done = events[-1][1]
    assert (done["fallback"], done["chunks"], done["search_count"]) == (True, [], 1)
    assert {e["reason"] for e in done["excluded"]} == {"below_min_score"}
    assert trace["fallback"] is True
    (search,) = trace["searches"]
    assert {c["excluded_reason"] for c in search["chunks"]} == {"below_min_score"}
    # The model was asked (it searched), so its tokens and cost are counted.
    assert trace["model_name"] == "gpt-4.1-mini"
    assert (done["input_tokens"], trace["input_tokens"]) == (100, 100)
    assert Decimal(trace["cost_usd"]) > 0


async def test_a_chunk_two_searches_find_keeps_its_first_label_and_citations_span_searches(
    app: FastAPI, owner: SignedUpMember
) -> None:
    calls: list[list[ModelMessage]] = []
    answer_with(
        app, recorded(searching(LEAVE, EXPENSES, LEAVE, answer="See [C2] and [C1]."), calls)
    )
    await use_default_model(owner)
    project_id = await knowledge_base(app, owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await agentic(owner, project_id, agent_id, top_k=1)

    events, trace = await asked(owner, project_id, agent_id, "Leave and expenses?")

    first, second, third = _search_results(calls[-1])
    assert "[C1] leave.txt" in first
    assert LEAVE in first
    assert "[C2] expenses.txt" in second
    # Found again, the Chunk keeps its first label and its text isn't sent again.
    assert "[C1] leave.txt (given above)" in third
    assert LEAVE not in third
    # Citations resolve against every Search's Chunks.
    citations = [data for event, data in events if event == "citation"]
    assert [(c["label"], c["document_name"]) for c in citations] == [
        ("C2", "expenses.txt"),
        ("C1", "leave.txt"),
    ]
    # The reply gave each Chunk once, in label order.
    expenses, leave = (c["chunk_id"] for c in citations)
    done = events[-1][1]
    assert [(c["rank"], c["chunk_id"]) for c in done["chunks"]] == [(1, leave), (2, expenses)]
    given = [
        [(c["rank"], c["document_name"], c["cited"]) for c in s["chunks"] if c["rank"]]
        for s in trace["searches"]
    ]
    assert given == [
        [(1, "leave.txt", True)],
        [(2, "expenses.txt", True)],
        [(1, "leave.txt", True)],
    ]


async def test_remembered_turns_replay_only_the_visitors_and_the_agents_text(
    app: FastAPI, owner: SignedUpMember
) -> None:
    calls: list[list[ModelMessage]] = []
    answer_with(app, recorded(searching("annual leave", answer="25 days [C1]."), calls))
    project_id, agent_id = await agentic_agent(app, owner)
    conversation = await start_conversation(owner, project_id, agent_id)
    first = await ask(owner, project_id, agent_id, conversation["id"], "How much leave?")
    assert parse_sse(first.text)[-1][0] == "done"
    calls.clear()

    second = await ask(owner, project_id, agent_id, conversation["id"], "And next year?")

    assert parse_sse(second.text)[-1][0] == "done"
    # The second reply's first model call: the system parts and the remembered turn as the
    # Visitor's and the Agent's text alone (no Searches, no Chunks), then the new question.
    *remembered, latest = calls[0]
    parts = [part for message in remembered for part in message.parts]
    assert all(isinstance(part, SystemPromptPart | UserPromptPart | TextPart) for part in parts)
    texts = [
        (type(part), part.content) for part in parts if isinstance(part, UserPromptPart | TextPart)
    ]
    assert texts == [
        (UserPromptPart, "<<<VISITOR_INPUT>>>\nHow much leave?\n<<<END_VISITOR_INPUT>>>"),
        (TextPart, "25 days [C1]."),
    ]
    assert [type(message) for message in remembered][-1] is ModelResponse
    assert isinstance(latest, ModelRequest)
    (part,) = latest.parts
    assert isinstance(part, UserPromptPart)
    assert "And next year?" in str(part.content)


# The widget: Visitors see that the Agent is searching, never what for (ticket 13-06)


async def test_a_visitor_is_told_of_each_search_but_never_sees_its_query(
    app: FastAPI, owner: SignedUpMember, new_client: ClientFactory
) -> None:
    project_id = await knowledgeable_project(app, owner)
    answer_with(
        app, searching("annual leave policy", "leave carry over", answer="Leave is 25 days [C1].")
    )
    created = await create_agent(owner, project_id)
    await agentic(owner, project_id, created["id"])
    await published(owner, project_id, created["id"])
    visitor: httpx.AsyncClient = await new_client()
    token = await conversation_token(visitor, created["public_id"])

    response = await send(visitor, created["public_id"], token, "How much leave?")

    events = parse_sse(response.text)
    # One `search` event as each Search starts, before the answer, carrying nothing.
    assert events[:2] == [("search", {}), ("search", {})]
    assert [event for event, _ in events[2:]] == ["token", "citation", "done"]
    assert "annual leave policy" not in response.text
    assert "leave carry over" not in response.text


async def test_an_agentic_reply_spends_every_token_it_used_of_the_budget_and_the_playground_none(
    app: FastAPI, owner: SignedUpMember, new_client: ClientFactory
) -> None:
    project_id = await knowledgeable_project(app, owner)
    answer_with(app, searching("annual leave", answer="Twenty-five days [C1]."))
    created = await create_agent(owner, project_id)
    await agentic(owner, project_id, created["id"])
    await published(owner, project_id, created["id"])
    conversation = await start_conversation(owner, project_id, created["id"])

    # The Playground is exempt...
    played = await ask(owner, project_id, created["id"], conversation["id"], "Leave?")
    assert parse_sse(played.text)[-1][0] == "done"
    assert (await usage(owner, created))["tokens_used"] == 0

    visitor: httpx.AsyncClient = await new_client()
    token = await conversation_token(visitor, created["public_id"])
    response = await send(visitor, created["public_id"], token, "Leave?")
    assert parse_sse(response.text)[-1][0] == "done"

    # ...and a Visitor's reply counts the tokens of both model calls: 2 x 50 input tokens, and
    # as output the search call's arguments (5) and the answer (4), as in
    # test_token_use_and_cost_are_summed_over_every_model_call.
    assert (await usage(owner, created))["tokens_used"] == 109
