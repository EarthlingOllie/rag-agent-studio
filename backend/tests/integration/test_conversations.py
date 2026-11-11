"""API seam: the Studio's Conversations viewer. Editors list a Project's Conversations (with
its Agents' Visitor Conversations from the widget and the Playground's, flagged), filter them by
Agent, date, Version and Playground, and open one to read its Messages and each reply's Trace.

Visitor Conversations are made the way a Visitor makes them, through the widget API; Playground
ones through the Playground API. Answers come from the echoing ``FunctionModel``."""

import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.agents import answer_with, ask, create_agent, create_automatic_agent, start_conversation
from tests.conftest import ClientFactory, MemberFactory, SignedUpMember
from tests.documents import create_project, project_path
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_versions import knowledgeable_project, published
from tests.integration.test_embed import conversation_token, send
from tests.integration.test_playground import ANSWER, LEAVE, three_tokens


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


def conversations_path(member: SignedUpMember, project_id: str, *rest: str) -> str:
    return "/".join([project_path(member, project_id), "conversations", *rest])


async def listed(member: SignedUpMember, project_id: str, **filters: Any) -> dict[str, Any]:
    response = await member.client.get(conversations_path(member, project_id), params=filters)
    assert response.status_code == 200, response.text
    page: dict[str, Any] = response.json()
    return page


async def visitor_chat(visitor: httpx.AsyncClient, public_id: str, *questions: str) -> None:
    token = await conversation_token(visitor, public_id)
    for question in questions:
        response = await send(visitor, public_id, token, question)
        assert response.status_code == 200, response.text


async def playground_chat(
    member: SignedUpMember, project_id: str, agent_id: str, *questions: str
) -> str:
    conversation = await start_conversation(member, project_id, agent_id)
    for question in questions:
        response = await ask(member, project_id, agent_id, conversation["id"], question)
        assert response.status_code == 200, response.text
    return str(conversation["id"])


async def live_agent_in(owner: SignedUpMember, project_id: str, name: str) -> dict[str, Any]:
    """An Automatic Agent, published: its Traces list the Chunks retrieved up front."""
    agent: dict[str, Any] = await create_automatic_agent(owner, project_id, name)
    agent["version"] = await published(owner, project_id, agent["id"])
    return agent


async def test_the_list_holds_visitor_and_playground_conversations_flagged(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await knowledgeable_project(app, owner)
    agent = await live_agent_in(owner, project_id, "Leave helper")
    await visitor_chat(visitor, agent["public_id"], "How much leave do I get?", "And more?")
    clock.advance(timedelta(minutes=5))
    playground_id = await playground_chat(editor, project_id, agent["id"], "Testing leave")

    page = await listed(editor, project_id)

    assert page["total"] == 2
    newest, oldest = page["items"]
    assert newest["id"] == playground_id
    assert newest["is_playground"] is True
    assert newest["agent_id"] == agent["id"]
    assert newest["agent_name"] == "Leave helper"
    assert newest["message_count"] == 2
    assert newest["preview"] == "Testing leave"
    assert newest["version_numbers"] == []
    assert oldest["is_playground"] is False
    assert oldest["message_count"] == 4
    assert oldest["preview"] == "How much leave do I get?"
    assert oldest["version_numbers"] == [1]


async def test_the_list_is_filtered_by_agent_date_version_and_playground(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient, clock: ControllableClock
) -> None:
    project_id = await knowledgeable_project(app, owner)
    leave = await live_agent_in(owner, project_id, "Leave helper")
    expenses = await live_agent_in(owner, project_id, "Expenses helper")
    # 5 November: a Visitor talks to v1 of the leave Agent, and an Editor tries the Draft.
    await visitor_chat(visitor, leave["public_id"], "Day one, v1")
    clock.advance(60)
    day_one_playground = await playground_chat(owner, project_id, leave["id"], "Day one, Draft")
    # 6 November: v2 goes live mid-Conversation, and the expenses Agent has a Visitor too.
    clock.advance(timedelta(days=1))
    token = await conversation_token(visitor, leave["public_id"])
    assert (await send(visitor, leave["public_id"], token, "Day two, v1")).status_code == 200
    v2 = await published(owner, project_id, leave["id"])
    assert (await send(visitor, leave["public_id"], token, "Day two, v2")).status_code == 200
    clock.advance(60)
    await visitor_chat(visitor, expenses["public_id"], "Day two, expenses")
    # 7 November: only v2 answers.
    clock.advance(timedelta(days=1))
    await visitor_chat(visitor, leave["public_id"], "Day three, v2")

    def previews(page: dict[str, Any]) -> list[str]:
        return [item["preview"] for item in page["items"]]

    everything = await listed(owner, project_id)
    assert previews(everything) == [
        "Day three, v2",
        "Day two, expenses",
        "Day two, v1",
        "Day one, Draft",
        "Day one, v1",
    ]
    assert [i["version_numbers"] for i in everything["items"]] == [[2], [1], [1, 2], [], [1]]
    by_agent = await listed(owner, project_id, agent_id=expenses["id"])
    assert previews(by_agent) == ["Day two, expenses"]
    by_version = await listed(owner, project_id, version_id=v2["id"])
    assert previews(by_version) == ["Day three, v2", "Day two, v1"]
    by_v1 = await listed(owner, project_id, agent_id=leave["id"], version_id=leave["version"]["id"])
    assert previews(by_v1) == ["Day two, v1", "Day one, v1"]
    on_day_two = await listed(
        owner, project_id, start="2026-11-06T00:00:00Z", end="2026-11-07T00:00:00Z"
    )
    assert previews(on_day_two) == ["Day two, expenses", "Day two, v1"]
    from_day_two = await listed(owner, project_id, start="2026-11-06T00:00:00+00:00")
    assert previews(from_day_two) == previews(everything)[:3]
    before_day_two = await listed(owner, project_id, end="2026-11-06T00:00:00Z")
    assert previews(before_day_two) == ["Day one, Draft", "Day one, v1"]
    playground_only = await listed(owner, project_id, playground="true")
    assert [i["id"] for i in playground_only["items"]] == [day_one_playground]
    visitors_only = await listed(owner, project_id, playground="false", agent_id=leave["id"])
    assert previews(visitors_only) == ["Day three, v2", "Day two, v1", "Day one, v1"]
    assert visitors_only["total"] == 3


async def test_the_list_comes_in_pages(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    project_id = await knowledgeable_project(app, owner)
    agent = await create_agent(owner, project_id)
    for n in range(3):
        await playground_chat(owner, project_id, agent["id"], f"Question {n}")
        clock.advance(60)

    first = await listed(owner, project_id, page_size=2)
    second = await listed(owner, project_id, page_size=2, page=2)

    assert [i["preview"] for i in first["items"]] == ["Question 2", "Question 1"]
    assert [i["preview"] for i in second["items"]] == ["Question 0"]
    assert (first["total"], first["page"], first["page_size"]) == (3, 1, 2)
    assert (second["total"], second["page"]) == (3, 2)


async def test_a_conversation_with_nothing_asked_has_no_preview(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)
    await start_conversation(owner, project_id, agent["id"])

    (item,) = (await listed(owner, project_id))["items"]

    assert (item["message_count"], item["preview"], item["version_numbers"]) == (0, None, [])


async def test_a_long_first_question_is_cut_in_the_preview(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await knowledgeable_project(app, owner)
    agent = await create_agent(owner, project_id)
    question = "Why " + "really " * 40 + "?"
    await playground_chat(owner, project_id, agent["id"], question)

    (item,) = (await listed(owner, project_id))["items"]

    assert item["preview"] == question[:120]


async def test_the_list_holds_only_the_projects_conversations(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await knowledgeable_project(app, owner)
    other_project = await create_project(owner)
    agent = await create_agent(owner, project_id)
    elsewhere = await create_agent(owner, other_project)
    await playground_chat(owner, project_id, agent["id"], "Here")
    await start_conversation(owner, other_project, elsewhere["id"])

    here = await listed(owner, project_id)
    there = await listed(owner, other_project)
    # An Agent of another Project matches nothing here.
    crossed = await listed(owner, project_id, agent_id=elsewhere["id"])

    assert [i["preview"] for i in here["items"]] == ["Here"]
    assert [i["agent_id"] for i in there["items"]] == [elsewhere["id"]]
    assert crossed == {"items": [], "page": 1, "page_size": 25, "total": 0}


async def test_an_unknown_project_has_no_conversations(owner: SignedUpMember) -> None:
    response = await owner.client.get(conversations_path(owner, str(uuid.uuid4())))

    assert (response.status_code, response.json()) == (404, {"detail": "Not found"})


@pytest.mark.parametrize(
    "query",
    [{"page": "0"}, {"page_size": "101"}, {"start": "2026-11-06T00:00:00"}, {"playground": "x"}],
)
async def test_bad_filters_are_refused(owner: SignedUpMember, query: dict[str, str]) -> None:
    project_id = await create_project(owner)

    response = await owner.client.get(conversations_path(owner, project_id), params=query)

    assert response.status_code == 422, response.text


# One Conversation and its Traces


async def opened(member: SignedUpMember, project_id: str, conversation_id: str) -> dict[str, Any]:
    response = await member.client.get(conversations_path(member, project_id, conversation_id))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def trace_of(member: SignedUpMember, project_id: str, conversation_id: str, message_id: str) -> str:
    return conversations_path(member, project_id, conversation_id, "messages", message_id, "trace")


async def citing_project(app: FastAPI, owner: SignedUpMember) -> str:
    """The leave policy Project, answered by a model that cites the first Chunk."""
    project_id = await knowledgeable_project(app, owner)
    answer_with(app, three_tokens)
    return project_id


async def test_an_editor_reads_a_visitor_conversation_with_each_replys_version(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await citing_project(app, owner)
    agent = await live_agent_in(owner, project_id, "Leave helper")
    token = await conversation_token(visitor, agent["public_id"])
    assert (await send(visitor, agent["public_id"], token, "How much leave?")).status_code == 200
    await published(owner, project_id, agent["id"])
    assert (await send(visitor, agent["public_id"], token, "Really?")).status_code == 200
    (item,) = (await listed(editor, project_id))["items"]

    body = await opened(editor, project_id, item["id"])

    assert (body["id"], body["agent_id"], body["agent_name"]) == (
        item["id"],
        agent["id"],
        "Leave helper",
    )
    assert body["is_playground"] is False
    assert body["created_at"] == item["created_at"]
    assert body["last_activity_at"] == item["last_activity_at"]
    messages = body["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "How much leave?"),
        ("assistant", ANSWER),
        ("user", "Really?"),
        ("assistant", ANSWER),
    ]
    assert [m["agent_version_number"] for m in messages] == [None, 1, None, 2]
    assert [m["config_source"] for m in messages] == [None, "version", None, "version"]
    reply = messages[1]
    assert reply["agent_version_id"] == agent["version"]["id"]
    assert (reply["model_provider"], reply["model_name"]) == ("openai", "gpt-4.1-mini")
    assert reply["fallback"] is False
    assert reply["input_tokens"] > 0
    assert reply["output_tokens"] > 0


async def test_a_visitor_replys_trace_shows_its_version_and_the_chunks_it_cited(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    project_id = await citing_project(app, owner)
    agent = await live_agent_in(owner, project_id, "Leave helper")
    await visitor_chat(visitor, agent["public_id"], "How much leave?")
    (item,) = (await listed(owner, project_id))["items"]
    reply = (await opened(owner, project_id, item["id"]))["messages"][1]

    response = await owner.client.get(trace_of(owner, project_id, item["id"], reply["id"]))

    assert response.status_code == 200, response.text
    trace = response.json()
    assert trace["message_id"] == reply["id"]
    assert (trace["config_source"], trace["agent_version_id"]) == (
        "version",
        agent["version"]["id"],
    )
    assert trace["agent_version_number"] == 1
    # A Live Version's answer runs with the Instructions the Version pins, so it names none.
    assert trace["instructions_source"] is None
    assert (trace["model_provider"], trace["model_name"]) == ("openai", "gpt-4.1-mini")
    assert trace["fallback"] is False
    assert trace["guardrail_outcomes"] == []
    (chunk,) = trace["chunks"]
    assert (chunk["document_name"], chunk["text"], chunk["rank"], chunk["cited"]) == (
        "leave.txt",
        LEAVE,
        1,
        True,
    )


async def test_a_playground_conversation_opens_flagged_with_its_draft_traces(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await citing_project(app, owner)
    agent = await create_automatic_agent(owner, project_id)
    conversation_id = await playground_chat(owner, project_id, agent["id"], "Leave?")

    body = await opened(owner, project_id, conversation_id)
    reply = body["messages"][1]
    trace = await owner.client.get(trace_of(owner, project_id, conversation_id, reply["id"]))

    assert body["is_playground"] is True
    assert (reply["config_source"], reply["agent_version_number"]) == ("draft", None)
    assert reply["instructions_source"] == "draft"
    assert trace.status_code == 200, trace.text
    assert (trace.json()["config_source"], trace.json()["agent_version_number"]) == (
        "draft",
        None,
    )
    assert trace.json()["chunks"][0]["cited"] is True


async def test_conversations_and_traces_are_found_only_in_their_project(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await citing_project(app, owner)
    other_project = await create_project(owner)
    agent = await create_agent(owner, project_id)
    conversation_id = await playground_chat(owner, project_id, agent["id"], "Leave?")
    other_conversation = await playground_chat(owner, project_id, agent["id"], "Again?")
    question, reply = (await opened(owner, project_id, conversation_id))["messages"]
    unknown = str(uuid.uuid4())

    for path in (
        conversations_path(owner, other_project, conversation_id),
        conversations_path(owner, project_id, unknown),
        conversations_path(owner, unknown, conversation_id),
        trace_of(owner, other_project, conversation_id, reply["id"]),
        trace_of(owner, project_id, unknown, reply["id"]),
        trace_of(owner, unknown, conversation_id, reply["id"]),
        # A question has no Trace; a reply is traced only within its own Conversation.
        trace_of(owner, project_id, conversation_id, question["id"]),
        trace_of(owner, project_id, conversation_id, unknown),
        trace_of(owner, project_id, other_conversation, reply["id"]),
    ):
        response = await owner.client.get(path)
        assert (response.status_code, response.json()) == (404, {"detail": "Not found"}), path
