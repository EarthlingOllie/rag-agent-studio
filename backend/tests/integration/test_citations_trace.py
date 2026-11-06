"""API seam: citations and the Trace of a Playground answer.

The model is a Pydantic AI ``FunctionModel``. With structured output it streams the JSON of a
cited answer; without it, it streams text and cites Chunks by their labels ([C1], [C2] …). The
citations are observed as the Studio sees them: ``citation`` events in the stream, then the
Trace read back through the API."""

import json
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo

from app.conversations.models import Message
from tests.agents import (
    answer_with,
    ask,
    create_agent,
    parse_sse,
    playground_path,
    save_draft,
    start_conversation,
    trace_path,
    use_default_model,
)
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project, upload
from tests.knowledge_base import FILES, PRODUCT, PRODUCT_QUESTION, knowledge_base

LEAVE = "Everyone gets 25 days of annual leave a year."
EXPENSES = "Claim expenses within 30 days of spending."


async def cites_first_twice_and_a_missing_label(
    messages: list[ModelMessage], info: AgentInfo
) -> AsyncIterator[str]:
    for token in ["Leave is 25 days [C", "1]. See [C9] and [C1]", " again."]:
        yield token


async def two_document_agent(
    app: FastAPI, member: SignedUpMember, owner: SignedUpMember | None = None
) -> tuple[str, str]:
    """A Project with the leave and expenses policies, each one Chunk, and an Agent."""
    await use_default_model(owner or member)
    project_id = await create_project(member)
    await upload(app, member, project_id, "leave.txt", LEAVE.encode())
    await upload(app, member, project_id, "expenses.txt", EXPENSES.encode())
    agent = await create_agent(member, project_id)
    return project_id, agent["id"]


def by_name(events: list[tuple[str, Any]], name: str) -> list[Any]:
    return [data for event, data in events if event == name]


async def test_labels_in_a_text_answer_are_streamed_as_citations(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, cites_first_twice_and_a_missing_label)
    project_id, agent_id = await two_document_agent(app, owner)
    conversation = await start_conversation(owner, project_id, agent_id)

    response = await ask(owner, project_id, agent_id, conversation["id"], LEAVE)

    events = parse_sse(response.text)
    # Tokens first, then the citations, then done.
    names = [event for event, _ in events]
    assert set(names[:-2]) == {"token"}
    assert names[-2:] == ["citation", "done"]
    (citation,) = by_name(events, "citation")
    (done,) = by_name(events, "done")
    first = next(c for c in done["chunks"] if c["rank"] == 1)
    # [C1] resolves to the first Chunk the model was given; [C9] matches no Chunk.
    assert citation == {
        "label": "C1",
        "chunk_id": first["chunk_id"],
        "document_id": citation["document_id"],
        "document_name": "leave.txt",
        "rank": 1,
    }
    uuid.UUID(citation["document_id"])


async def test_structured_output_gives_the_citations_where_the_model_supports_it(
    app: FastAPI, owner: SignedUpMember
) -> None:
    async def cited_json(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        # The answer mentions [C1] but cites only C2: the structured citations win.
        body = json.dumps({"answer": "Claims within 30 days, not [C1].", "citations": ["C2"]})
        for start in range(0, len(body), 8):
            yield body[start : start + 8]

    answer_with(app, cited_json, structured=True)
    project_id, agent_id = await two_document_agent(app, owner)
    conversation = await start_conversation(owner, project_id, agent_id)

    response = await ask(owner, project_id, agent_id, conversation["id"], LEAVE)

    events = parse_sse(response.text)
    # The answer streams in pieces, not as JSON.
    tokens = by_name(events, "token")
    assert len(tokens) > 1
    assert "".join(t["text"] for t in tokens) == "Claims within 30 days, not [C1]."
    (done,) = by_name(events, "done")
    (citation,) = by_name(events, "citation")
    assert (citation["label"], citation["rank"]) == ("C2", 2)
    assert citation["chunk_id"] == next(c["chunk_id"] for c in done["chunks"] if c["rank"] == 2)
    saved = await owner.client.get(playground_path(owner, project_id, agent_id, conversation["id"]))
    assert saved.json()["messages"][1]["content"] == "Claims within 30 days, not [C1]."


async def cites_the_first_chunk(
    messages: list[ModelMessage], info: AgentInfo
) -> AsyncIterator[str]:
    for token in ["Two years ", "[C1]."]:
        yield token


async def test_the_trace_shows_the_model_usage_and_every_chunk_retrieved(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    answer_with(app, cites_the_first_chunk)
    await use_default_model(owner)
    editor = await member_factory(owner, "editor")
    project_id = await knowledge_base(app, editor)
    agent_id = (await create_agent(editor, project_id))["id"]
    await save_draft(editor, project_id, agent_id, {"retrieval": {"min_score": 0.3}})
    conversation = await start_conversation(editor, project_id, agent_id)
    response = await ask(editor, project_id, agent_id, conversation["id"], PRODUCT_QUESTION)
    (done,) = by_name(parse_sse(response.text), "done")

    trace = await editor.client.get(
        trace_path(editor, project_id, agent_id, conversation["id"], done["message_id"])
    )

    assert trace.status_code == 200, trace.text
    body = trace.json()
    assert body["message_id"] == done["message_id"]
    assert (body["model_provider"], body["model_name"]) == ("openai", "gpt-4.1-mini")
    assert (body["input_tokens"], body["output_tokens"]) == (
        done["input_tokens"],
        done["output_tokens"],
    )
    assert (body["first_token_ms"], body["latency_ms"]) == (
        done["first_token_ms"],
        done["latency_ms"],
    )
    assert Decimal(body["cost_usd"]) > 0
    assert body["fallback"] is False
    # Every Chunk of the Knowledge Base was found: the product Chunk was given to the model
    # and cited; the rest were left out below the minimum score.
    chunks = body["chunks"]
    assert len(chunks) == len(FILES)
    cited, *excluded = chunks
    assert cited == {
        "chunk_id": done["chunks"][0]["chunk_id"],
        "document_id": cited["document_id"],
        "document_name": "product.txt",
        "text": PRODUCT,
        "score": done["chunks"][0]["score"],
        "relevance": done["chunks"][0]["relevance"],
        "rank": 1,
        "cited": True,
        "excluded_reason": None,
    }
    assert {e["excluded_reason"] for e in excluded} == {"below_min_score"}
    assert {e["rank"] for e in excluded} == {None}
    assert {e["cited"] for e in excluded} == {False}
    assert {e["chunk_id"] for e in excluded} == {e["chunk_id"] for e in done["excluded"]}
    assert all(e["relevance"] < 0.3 for e in excluded)
    # Best first, as retrieval ranked them.
    assert [e["score"] for e in excluded] == sorted((e["score"] for e in excluded), reverse=True)


async def test_chunks_given_but_not_cited_and_chunks_outside_top_k_are_traced(
    app: FastAPI, owner: SignedUpMember
) -> None:
    async def cites_nothing(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        yield "No idea."

    answer_with(app, cites_nothing)
    await use_default_model(owner)
    project_id = await knowledge_base(app, owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await save_draft(owner, project_id, agent_id, {"retrieval": {"top_k": 2}})
    conversation = await start_conversation(owner, project_id, agent_id)
    response = await ask(owner, project_id, agent_id, conversation["id"], PRODUCT_QUESTION)
    events = parse_sse(response.text)
    assert by_name(events, "citation") == []
    (done,) = by_name(events, "done")

    trace = await owner.client.get(
        trace_path(owner, project_id, agent_id, conversation["id"], done["message_id"])
    )

    chunks = trace.json()["chunks"]
    given = [c for c in chunks if c["excluded_reason"] is None]
    assert [(c["rank"], c["cited"]) for c in given] == [(1, False), (2, False)]
    assert {c["excluded_reason"] for c in chunks[2:]} == {"outside_top_k"}
    assert len(chunks) == len(FILES)


async def test_a_fallback_reply_is_traced_with_the_chunks_it_left_out(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, cites_the_first_chunk)
    await use_default_model(owner)
    project_id = await knowledge_base(app, owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await save_draft(owner, project_id, agent_id, {"retrieval": {"min_score": 0.9}})
    conversation = await start_conversation(owner, project_id, agent_id)
    response = await ask(owner, project_id, agent_id, conversation["id"], PRODUCT_QUESTION)
    (done,) = by_name(parse_sse(response.text), "done")

    trace = await owner.client.get(
        trace_path(owner, project_id, agent_id, conversation["id"], done["message_id"])
    )

    body = trace.json()
    assert body["fallback"] is True
    assert (body["input_tokens"], body["output_tokens"]) == (0, 0)
    # A plain decimal, not "0E-9": the Studio shows it as it comes.
    assert body["cost_usd"] == "0.000000000"
    # No model was asked, so the Trace names none.
    assert (body["model_provider"], body["model_name"]) == (None, None)
    assert len(body["chunks"]) == len(FILES)
    assert {c["excluded_reason"] for c in body["chunks"]} == {"below_min_score"}


async def test_an_answer_saved_without_retrievals_is_not_traced_as_a_fallback(
    app: FastAPI, owner: SignedUpMember
) -> None:
    # An answer from before Message retrievals were saved: it has no retrieval rows.
    project_id, agent_id = await two_document_agent(app, owner)
    conversation = await start_conversation(owner, project_id, agent_id)
    async with app.state.sessionmaker() as session:
        message = Message(
            organisation_id=uuid.UUID(owner.organisation_id),
            conversation_id=uuid.UUID(conversation["id"]),
            role="assistant",
            content="Leave is 25 days.",
            model_provider="openai",
            model_name="gpt-4.1-mini",
        )
        session.add(message)
        await session.commit()
        message_id = str(message.id)

    trace = await owner.client.get(
        trace_path(owner, project_id, agent_id, conversation["id"], message_id)
    )

    assert trace.status_code == 200, trace.text
    body = trace.json()
    assert body["fallback"] is False
    assert body["chunks"] == []


async def test_the_cost_is_worked_out_with_the_credentials_prices(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, cites_first_twice_and_a_missing_label)
    project_id, agent_id = await two_document_agent(app, owner)
    credential_id = (
        await owner.client.get(f"/api/organisations/{owner.organisation_id}/default-model")
    ).json()["credential_id"]
    # A negotiated rate: $1 per million input tokens and $3 per million output tokens.
    overridden = await owner.client.put(
        f"/api/organisations/{owner.organisation_id}/credentials/{credential_id}/prices",
        json={"model": "gpt-4.1-mini", "input": "1", "output": "3"},
    )
    assert overridden.status_code == 200, overridden.text
    conversation = await start_conversation(owner, project_id, agent_id)
    response = await ask(owner, project_id, agent_id, conversation["id"], LEAVE)
    (done,) = by_name(parse_sse(response.text), "done")

    trace = await owner.client.get(
        trace_path(owner, project_id, agent_id, conversation["id"], done["message_id"])
    )

    body = trace.json()
    expected = (Decimal(body["input_tokens"]) * 1 + Decimal(body["output_tokens"]) * 3) / 10**6
    assert Decimal(body["cost_usd"]) == expected
    assert body["input_tokens"] > 0
    assert body["output_tokens"] > 0
    saved = await owner.client.get(playground_path(owner, project_id, agent_id, conversation["id"]))
    assert Decimal(saved.json()["messages"][1]["cost_usd"]) == expected
    # The cited Chunk is the leave policy's; the expenses policy was given but not cited.
    assert [(c["document_name"], c["cited"]) for c in body["chunks"]] == [
        ("leave.txt", True),
        ("expenses.txt", False),
    ]


async def test_traces_are_only_for_answers_in_the_conversation(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    answer_with(app, cites_first_twice_and_a_missing_label)
    project_id, agent_id = await two_document_agent(app, owner)
    conversation = await start_conversation(owner, project_id, agent_id)
    other = await start_conversation(owner, project_id, agent_id)
    await ask(owner, project_id, agent_id, conversation["id"], LEAVE)
    saved = await owner.client.get(playground_path(owner, project_id, agent_id, conversation["id"]))
    question, answer = saved.json()["messages"]
    stranger = await tenant_factory()
    missing = str(uuid.uuid4())

    def path(conversation_id: str, message_id: str, agent: str = agent_id) -> str:
        return trace_path(owner, project_id, agent, conversation_id, message_id)

    not_found = [
        await owner.client.get(path(conversation["id"], question["id"])),
        await owner.client.get(path(other["id"], answer["id"])),
        await owner.client.get(path(conversation["id"], missing)),
        await owner.client.get(path(missing, answer["id"])),
        await owner.client.get(path(conversation["id"], answer["id"], agent=missing)),
        await stranger.client.get(path(conversation["id"], answer["id"])),
    ]

    assert [r.status_code for r in not_found] == [404] * len(not_found)
    assert (await owner.client.get(path(conversation["id"], answer["id"]))).status_code == 200
