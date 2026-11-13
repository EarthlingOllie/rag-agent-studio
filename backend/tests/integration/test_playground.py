"""API seam: an Editor chats with an Agent's Draft in the Playground.

The Default Model is set through the API (fake credential verifier); the gateway's chat model
is a Pydantic AI ``FunctionModel``. The answer is observed as the Studio sees it: the Server-Sent
Events stream, then the saved Conversation read back through the API."""

import json
import re
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo

from app.agents.config import DEFAULT_FALLBACK_TEXT
from app.conversations.models import Message
from app.credentials.registry import Provider
from app.gateway.fakes import FakeModelAdapters
from app.gateway.ports import Reranker
from app.runtime.prompt import preamble
from tests.agents import (
    AUTOMATIC,
    answer_text,
    answer_with,
    ask,
    create_agent,
    create_automatic_agent,
    parse_sse,
    playground_path,
    save_draft,
    start_conversation,
    trace_path,
    use_default_model,
)
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project, project_path, upload
from tests.integration.test_provider_credentials import ANTHROPIC_KEY, VOYAGE_KEY, added
from tests.knowledge_base import (
    FILES,
    PRODUCT,
    PRODUCT_QUESTION,
    UNRELATED_QUESTION,
    knowledge_base,
)

LEAVE = "Everyone gets 25 days of annual leave a year."


ANSWER = "Everyone gets twenty-five days of annual leave a year, see [C1]."


async def three_tokens(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    for token in ["Everyone gets twenty-five days ", "of annual leave a year, ", "see [C1]."]:
        yield token


def without_canary(text: str) -> str:
    """The text with the request's Canary token written as ``{canary}``: an echo that repeated
    the token itself would have its answer replaced."""
    return re.sub(r"\b[0-9a-f]{20}\b", "{canary}", text)


async def echo(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    """Answers with every part the model was given, as JSON: (message kind, part kind, text)."""
    yield json.dumps(
        [
            [
                type(message).__name__,
                part.part_kind,
                without_canary(str(getattr(part, "content", ""))),
            ]
            for message in messages
            for part in message.parts
        ]
    )


async def ready_agent(
    app: FastAPI, owner: SignedUpMember, editor: SignedUpMember | None = None
) -> tuple[SignedUpMember, str, str]:
    """An Organisation with a Default Model, and a Project with the leave policy and an
    Automatic Agent."""
    member = editor or owner
    await use_default_model(owner)
    project_id = await create_project(member)
    await upload(app, member, project_id, "leave.txt", LEAVE.encode())
    agent = await create_automatic_agent(member, project_id)
    return member, project_id, agent["id"]


async def test_an_editor_asks_the_draft_and_the_answer_streams_back(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    built = answer_with(app, three_tokens)
    editor, project_id, agent_id = await ready_agent(
        app, owner, await member_factory(owner, "editor")
    )
    conversation = await start_conversation(editor, project_id, agent_id)
    assert conversation["is_playground"] is True
    assert conversation["messages"] == []

    response = await ask(editor, project_id, agent_id, conversation["id"], "How much leave?")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    *tokens, (cited, _), (kind, done) = events
    # The answer streams in pieces (the canary filter holds back only its last few characters).
    assert len(tokens) > 1
    assert {event for event, _ in tokens} == {"token"}
    assert "".join(data["text"] for _, data in tokens) == ANSWER
    # The answer cites [C1], then the stream ends.
    assert cited == "citation"
    assert kind == "done"
    # The Organisation's Default Model, through the gateway.
    assert built == ["openai:gpt-4.1-mini"]
    # The answer was grounded in the Project's one Chunk.
    (chunk,) = done["chunks"]
    assert chunk["rank"] == 1

    saved = await editor.client.get(
        playground_path(editor, project_id, agent_id, conversation["id"])
    )
    assert saved.status_code == 200, saved.text
    question, answer = saved.json()["messages"]
    assert (question["role"], question["content"]) == ("user", "How much leave?")
    assert question["model_name"] is None
    assert question["input_tokens"] is None
    assert answer["id"] == done["message_id"]
    assert (answer["role"], answer["content"]) == ("assistant", ANSWER)
    assert answer["config_source"] == "draft"
    assert (answer["model_provider"], answer["model_name"]) == ("openai", "gpt-4.1-mini")
    assert (answer["input_tokens"], answer["output_tokens"]) == (
        done["input_tokens"],
        done["output_tokens"],
    )
    assert answer["input_tokens"] > 0
    assert answer["output_tokens"] == 13  # FunctionModel counts the answer's words
    assert 0 <= answer["first_token_ms"] <= answer["latency_ms"]
    assert (answer["first_token_ms"], answer["latency_ms"]) == (
        done["first_token_ms"],
        done["latency_ms"],
    )
    # Priced with the platform price table: GPT-4.1 mini costs money per token.
    assert Decimal(answer["cost_usd"]) > 0


async def test_the_model_receives_the_draft_the_chunks_and_the_history_in_order(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, echo)
    member, project_id, agent_id = await ready_agent(app, owner)
    saved = await save_draft(
        member,
        project_id,
        agent_id,
        {"behaviour": {"system_prompt": "Be brief."}, "retrieval": AUTOMATIC},
    )
    assert saved.status_code == 200
    conversation = await start_conversation(member, project_id, agent_id)
    first = await ask(member, project_id, agent_id, conversation["id"], "How much leave?")
    first_answer = answer_text(first)

    second = await ask(member, project_id, agent_id, conversation["id"], LEAVE)

    parts = json.loads(answer_text(second))
    assert [part[:2] for part in parts] == [
        ["ModelRequest", "system-prompt"],
        ["ModelRequest", "system-prompt"],
        ["ModelRequest", "user-prompt"],
        ["ModelResponse", "text"],
        ["ModelRequest", "user-prompt"],
    ]
    assert parts[0][2] == preamble("{canary}")
    assert parts[1][2] == "Be brief."
    # A remembered question is spotlighted as Visitor input, like the latest one.
    assert parts[2][2] == "<<<VISITOR_INPUT>>>\nHow much leave?\n<<<END_VISITOR_INPUT>>>"
    # The remembered answer (here an echo of the first prompt) has its delimiters escaped.
    assert parts[3][2] == first_answer.replace("<<<", "<\u200b<<")
    assert parts[4][2] == (
        "<<<RETRIEVED_CHUNKS>>>\n[C1] leave.txt\n" + LEAVE + "\n<<<END_RETRIEVED_CHUNKS>>>\n\n"
        "<<<VISITOR_INPUT>>>\n" + LEAVE + "\n<<<END_VISITOR_INPUT>>>"
    )


async def test_the_project_instructions_reach_the_model_before_the_system_prompt(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, echo)
    member, project_id, agent_id = await ready_agent(app, owner)
    instructions = "# House rules\n\n- Answer in **British English**.\n"
    saved = await member.client.put(
        f"{project_path(member, project_id)}/instructions", json={"markdown": instructions}
    )
    assert saved.status_code == 200, saved.text
    await save_draft(
        member,
        project_id,
        agent_id,
        {"behaviour": {"system_prompt": "Be brief."}, "retrieval": AUTOMATIC},
    )
    conversation = await start_conversation(member, project_id, agent_id)

    response = await ask(member, project_id, agent_id, conversation["id"], "How much leave?")

    parts = json.loads(answer_text(response))
    assert [part[2] for part in parts[:3]] == [preamble("{canary}"), instructions, "Be brief."]


async def test_an_unanswered_question_is_not_remembered(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, echo)
    member, project_id, agent_id = await ready_agent(app, owner)
    conversation = await start_conversation(member, project_id, agent_id)
    await ask(member, project_id, agent_id, conversation["id"], "First")
    # A question whose answer never arrived (the stream was cut off). Provider errors become
    # error events in ticket 04-08; until then the only way to get one is to write it.
    async with app.state.sessionmaker() as session:
        session.add(
            Message(
                organisation_id=uuid.UUID(member.organisation_id),
                conversation_id=uuid.UUID(conversation["id"]),
                role="user",
                content="Lost question",
            )
        )
        await session.commit()

    response = await ask(member, project_id, agent_id, conversation["id"], "Second")

    parts = json.loads(answer_text(response))
    assert not any("Lost question" in part[2] for part in parts)
    assert "<<<VISITOR_INPUT>>>\nFirst\n<<<END_VISITOR_INPUT>>>" in [part[2] for part in parts]


async def test_the_question_needs_a_default_model(app: FastAPI, owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)
    conversation = await start_conversation(owner, project_id, agent["id"])

    response = await ask(owner, project_id, agent["id"], conversation["id"], "Hello?")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "This Organisation has no Default Model. "
        "An Owner can choose one in Settings, Models."
    }
    saved = await owner.client.get(
        playground_path(owner, project_id, agent["id"], conversation["id"])
    )
    assert saved.json()["messages"] == []


async def test_a_project_without_documents_replies_with_the_fallback_text(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, never_called)
    await use_default_model(owner)
    project_id = await create_project(owner)
    agent = await create_automatic_agent(owner, project_id)
    conversation = await start_conversation(owner, project_id, agent["id"])

    response = await ask(owner, project_id, agent["id"], conversation["id"], "Hello?")

    events = parse_sse(response.text)
    assert events[0] == ("token", {"text": DEFAULT_FALLBACK_TEXT})
    assert events[1][1]["fallback"] is True
    assert (events[1][1]["chunks"], events[1][1]["excluded"]) == ([], [])


async def never_called(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    raise AssertionError("the model was asked")
    yield ""  # pragma: no cover


async def test_with_nothing_relevant_the_agent_replies_with_its_fallback_text(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, never_called)
    await use_default_model(owner)
    project_id = await knowledge_base(app, owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    saved = await save_draft(
        owner,
        project_id,
        agent_id,
        {
            "behaviour": {"fallback_text": "Ask HR, please."},
            "retrieval": {**AUTOMATIC, "min_score": 0.3},
        },
    )
    assert saved.status_code == 200, saved.text
    conversation = await start_conversation(owner, project_id, agent_id)

    response = await ask(owner, project_id, agent_id, conversation["id"], UNRELATED_QUESTION)

    assert response.status_code == 200, response.text
    (token, (kind, done)) = parse_sse(response.text)
    assert token == ("token", {"text": "Ask HR, please."})
    assert kind == "done"
    assert done["fallback"] is True
    assert done["chunks"] == []
    # Every Chunk found was left out, and the stream says why.
    assert len(done["excluded"]) == len(FILES)
    assert {e["reason"] for e in done["excluded"]} == {"below_min_score"}
    assert all(e["relevance"] < 0.3 for e in done["excluded"])
    assert (done["input_tokens"], done["output_tokens"]) == (0, 0)
    saved_conversation = await owner.client.get(
        playground_path(owner, project_id, agent_id, conversation["id"])
    )
    _, answer = saved_conversation.json()["messages"]
    assert answer["id"] == done["message_id"]
    assert answer["content"] == "Ask HR, please."
    assert (answer["input_tokens"], answer["output_tokens"]) == (0, 0)
    assert Decimal(answer["cost_usd"]) == 0


async def test_a_relevant_chunk_above_the_minimum_score_reaches_the_model(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, echo)
    await use_default_model(owner)
    project_id = await knowledge_base(app, owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await save_draft(owner, project_id, agent_id, {"retrieval": {**AUTOMATIC, "min_score": 0.3}})
    conversation = await start_conversation(owner, project_id, agent_id)

    response = await ask(owner, project_id, agent_id, conversation["id"], PRODUCT_QUESTION)

    *_, (_, done) = parse_sse(response.text)
    question = json.loads(answer_text(response))[-1][2]
    # Found by keyword search alone, it is the one Chunk given to the model.
    assert f"[C1] product.txt\n{PRODUCT}" in question
    assert "[C2]" not in question
    assert done["fallback"] is False
    (chunk,) = done["chunks"]
    assert chunk["rank"] == 1
    assert chunk["relevance"] == pytest.approx(3 / 6)
    assert {e["reason"] for e in done["excluded"]} == {"below_min_score"}
    assert chunk["chunk_id"] not in {e["chunk_id"] for e in done["excluded"]}


async def test_the_drafts_reranker_chooses_the_chunks_the_model_is_given(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, echo)
    rerankers: list[str] = []
    adapters: FakeModelAdapters = app.state.model_gateway.adapters
    build_reranker = adapters.reranker

    def recording_reranker(provider: Provider, secret: str, model: str) -> Reranker:
        rerankers.append(f"{provider}:{model}:{secret}")
        return build_reranker(provider, secret, model)

    adapters.reranker = recording_reranker  # type: ignore[method-assign]
    await use_default_model(owner)
    voyage = await added(owner, provider="voyage", api_key=VOYAGE_KEY)
    project_id = await knowledge_base(app, owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    # Semantic search alone, keeping one Chunk: without the reranker that isn't PRODUCT.
    retrieval = {**AUTOMATIC, "hybrid_weight": 1, "top_k": 1, "min_score": 0}
    await save_draft(owner, project_id, agent_id, {"retrieval": retrieval})
    conversation = await start_conversation(owner, project_id, agent_id)
    plain = await ask(owner, project_id, agent_id, conversation["id"], PRODUCT_QUESTION)
    *_, (_, plain_done) = parse_sse(plain.text)
    reranker = {"credential_id": voyage["id"], "model": "rerank-2.5"}
    saved = await save_draft(
        owner, project_id, agent_id, {"retrieval": {**retrieval, "reranker": reranker}}
    )
    assert saved.status_code == 200, saved.text

    response = await ask(owner, project_id, agent_id, conversation["id"], PRODUCT_QUESTION)

    assert response.status_code == 200, response.text
    *_, (_, done) = parse_sse(response.text)
    question = json.loads(answer_text(response))[-1][2]
    # The Draft's reranker, built by the gateway from the Voyage credential's secret.
    assert rerankers == [f"voyage:rerank-2.5:{VOYAGE_KEY}"]
    # The reranker lifted PRODUCT above the rest before top-k kept one Chunk.
    assert f"[C1] product.txt\n{PRODUCT}" in question
    assert "[C2]" not in question
    (chunk,) = done["chunks"]
    (plain_chunk,) = plain_done["chunks"]
    assert chunk["chunk_id"] != plain_chunk["chunk_id"]
    assert chunk["relevance"] == pytest.approx(2 / 5)
    assert {e["reason"] for e in done["excluded"]} == {"outside_top_k"}
    assert len(done["excluded"]) == len(FILES) - 1
    # The Trace keeps the reranker's relevance.
    trace = await owner.client.get(
        trace_path(owner, project_id, agent_id, conversation["id"], done["message_id"])
    )
    assert trace.status_code == 200, trace.text
    traced, *left_out = trace.json()["chunks"]
    assert (traced["chunk_id"], traced["text"], traced["rank"]) == (chunk["chunk_id"], PRODUCT, 1)
    assert traced["relevance"] == pytest.approx(2 / 5)
    assert {e["relevance"] for e in left_out} == {0.0}


async def test_questions_must_not_be_empty(app: FastAPI, owner: SignedUpMember) -> None:
    member, project_id, agent_id = await ready_agent(app, owner)
    conversation = await start_conversation(member, project_id, agent_id)

    for content in ["", "   ", "x" * 4001]:
        response = await ask(member, project_id, agent_id, conversation["id"], content)
        assert response.status_code == 422


async def test_conversations_are_not_found_outside_their_agent_and_organisation(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    member, project_id, agent_id = await ready_agent(app, owner)
    other_agent = await create_agent(member, project_id, "Other")
    conversation = await start_conversation(member, project_id, agent_id)
    stranger = await tenant_factory()
    missing = str(uuid.uuid4())

    not_found = [
        await member.client.get(
            playground_path(member, project_id, other_agent["id"], conversation["id"])
        ),
        await member.client.get(playground_path(member, project_id, agent_id, missing)),
        await member.client.get(playground_path(member, project_id, missing, conversation["id"])),
        await member.client.post(playground_path(member, project_id, missing)),
        await member.client.post(playground_path(member, missing, agent_id)),
        await ask(member, project_id, agent_id, missing, "Hi"),
        await stranger.client.get(
            playground_path(member, project_id, agent_id, conversation["id"])
        ),
    ]

    assert [r.status_code for r in not_found] == [404] * len(not_found)


async def test_an_archived_projects_playground_is_closed(
    app: FastAPI, owner: SignedUpMember
) -> None:
    member, project_id, agent_id = await ready_agent(app, owner)
    conversation = await start_conversation(member, project_id, agent_id)
    archived = await member.client.post(f"{project_path(member, project_id)}/archive")
    assert archived.status_code == 200

    started = await member.client.post(playground_path(member, project_id, agent_id))
    asked = await ask(member, project_id, agent_id, conversation["id"], "Hi")

    assert (started.status_code, asked.status_code) == (409, 409)


async def settings_seen(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    """Answers with the model settings it was called with and the questions it remembers."""
    remembered = [
        str(part.content)
        for message in messages[:-1]
        for part in message.parts
        if part.part_kind == "user-prompt"
    ]
    yield json.dumps({"settings": info.model_settings, "remembered": remembered})


async def test_the_draft_chooses_the_model_and_its_settings(
    app: FastAPI, owner: SignedUpMember
) -> None:
    built = answer_with(app, settings_seen)
    member, project_id, agent_id = await ready_agent(app, owner)
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY)
    behaviour = {
        "model": {"credential_id": claude["id"], "model": "claude-haiku-4-5"},
        "temperature": 0.1,
        "max_output_tokens": 300,
    }
    saved = await save_draft(member, project_id, agent_id, {"behaviour": behaviour})
    assert saved.status_code == 200, saved.text
    conversation = await start_conversation(member, project_id, agent_id)

    response = await ask(member, project_id, agent_id, conversation["id"], "How much leave?")

    seen = json.loads(answer_text(response))
    assert seen["settings"] == {"temperature": 0.1, "max_tokens": 300}
    # The Model override, not the Default Model (GPT-4.1 mini).
    assert built == ["anthropic:claude-haiku-4-5"]
    saved_conversation = await member.client.get(
        playground_path(member, project_id, agent_id, conversation["id"])
    )
    answer = saved_conversation.json()["messages"][-1]
    assert (answer["model_provider"], answer["model_name"]) == ("anthropic", "claude-haiku-4-5")


async def test_a_model_override_needs_no_default_model(app: FastAPI, owner: SignedUpMember) -> None:
    built = answer_with(app, three_tokens)
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY)
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "leave.txt", LEAVE.encode())
    agent = await create_agent(owner, project_id)
    model = {"credential_id": claude["id"], "model": "claude-sonnet-4-5"}
    await save_draft(owner, project_id, agent["id"], {"behaviour": {"model": model}})
    conversation = await start_conversation(owner, project_id, agent["id"])

    response = await ask(owner, project_id, agent["id"], conversation["id"], "Hello?")

    assert response.status_code == 200, response.text
    assert built == ["anthropic:claude-sonnet-4-5"]


async def test_only_the_remembered_turns_reach_the_model(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, settings_seen)
    member, project_id, agent_id = await ready_agent(app, owner)
    await save_draft(member, project_id, agent_id, {"behaviour": {"remembered_turns": 2}})
    conversation = await start_conversation(member, project_id, agent_id)
    for question in ["One?", "Two?", "Three?"]:
        await ask(member, project_id, agent_id, conversation["id"], question)

    response = await ask(member, project_id, agent_id, conversation["id"], "Four?")

    assert json.loads(answer_text(response))["remembered"] == [
        "<<<VISITOR_INPUT>>>\nTwo?\n<<<END_VISITOR_INPUT>>>",
        "<<<VISITOR_INPUT>>>\nThree?\n<<<END_VISITOR_INPUT>>>",
    ]
    await save_draft(member, project_id, agent_id, {"behaviour": {"remembered_turns": 0}})
    forgetful = await ask(member, project_id, agent_id, conversation["id"], "Five?")
    assert json.loads(answer_text(forgetful))["remembered"] == []
