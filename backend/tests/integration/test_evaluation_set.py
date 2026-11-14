"""API seam: building an Agent's Evaluation Set. An Editor turns an Agent Message, a Visitor's
or the Playground's, into an Evaluation Case (the question prefilled, the cited passages
offered), copies cases from another Agent of the Project, and works with a capped, searchable,
filterable set. Cases outlive the Retention Window and keep no link to the Conversation
(ADR-0016).

Visitor Messages are made through the widget API and Playground ones through the Playground API,
answered by a scripted ``FunctionModel`` citing [C1]. The Purge is called directly, as its Beat
task would; Audit Events are read through the API.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo

from app.conversations.models import Message
from app.evaluation import service as evaluation_service
from app.retention.service import purge_messages
from tests.agents import (
    answer_with,
    ask,
    create_agent,
    create_automatic_agent,
    parse_sse,
    start_conversation,
)
from tests.conftest import ClientFactory, MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project, upload
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_versions import agent, published
from tests.integration.test_conversations import conversations_path, opened
from tests.integration.test_embed import conversation_token, send
from tests.integration.test_evaluation import (
    FAILING,
    PASSING,
    REFERENCE,
    UNAVAILABLE,
    evaluated,
    evaluation_path,
    judge_with,
    scripted,
)
from tests.integration.test_evaluation_expectations import (
    add_case,
    leave_document,
    post_case,
    source,
)
from tests.integration.test_playground import LEAVE, ready_agent, three_tokens
from tests.integration.test_projects import audit_events

PARKING = "Visitors park in the north car park, behind the main building."
ADDED_FROM_MESSAGE = "agent.evaluation_case_added_from_message"
CASE_DELETED = "agent.evaluation_case_deleted"
PURGED = "This Message's text has been purged, so it can't be added to the Evaluation Set."


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


async def cites_both(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    for token in ["Twenty-five days [C1], ", "and park north [C2]."]:
        yield token


async def playground_reply(
    member: SignedUpMember, project_id: str, agent_id: str, question: str
) -> tuple[str, str]:
    """Asks the Draft in a new Playground Conversation; returns it and the reply's ID."""
    conversation = await start_conversation(member, project_id, agent_id)
    response = await ask(member, project_id, agent_id, conversation["id"], question)
    assert response.status_code == 200, response.text
    (done,) = [data for event, data in parse_sse(response.text) if event == "done"]
    return conversation["id"], done["message_id"]


def prefill_path(member: SignedUpMember, project_id: str, agent_id: str, message_id: str) -> str:
    return evaluation_path(member, project_id, agent_id, "messages", message_id, "prefill")


async def prefill(
    member: SignedUpMember, project_id: str, agent_id: str, message_id: str
) -> httpx.Response:
    return await member.client.get(prefill_path(member, project_id, agent_id, message_id))


def cases_path(member: SignedUpMember, project_id: str, agent_id: str) -> str:
    return evaluation_path(member, project_id, agent_id, "cases")


async def listed(
    member: SignedUpMember, project_id: str, agent_id: str, **filters: Any
) -> list[dict[str, Any]]:
    response = await member.client.get(cases_path(member, project_id, agent_id), params=filters)
    assert response.status_code == 200, response.text
    found: list[dict[str, Any]] = response.json()
    return found


# Prefill from a Message


async def test_a_playground_reply_prefills_its_question_and_cited_passages(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    answer_with(app, cites_both)
    editor, project_id, agent_id = await ready_agent(
        app, owner, await member_factory(owner, "editor")
    )
    leave = await leave_document(editor, project_id)
    parking = await upload(app, editor, project_id, "parking.txt", PARKING.encode())
    _, reply = await playground_reply(editor, project_id, agent_id, "  How much leave?  ")

    response = await prefill(editor, project_id, agent_id, reply)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["question"] == "How much leave?"
    # Each cited Chunk, in the order the model was given them, as a passage of its Document.
    assert sorted(
        (s["document_id"], s["document_name"], s["passage"]) for s in body["expected_sources"]
    ) == sorted([(leave["id"], "leave.txt", LEAVE), (parking["id"], "parking.txt", PARKING)])


async def test_a_visitor_reply_prefills_the_question_it_answered(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    answer_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    await published(owner, project_id, agent_id)
    public_id = (await agent(owner, project_id, agent_id))["public_id"]
    token = await conversation_token(visitor, public_id)
    for question in ("Hello there", "How much annual leave do I get?"):
        assert (await send(visitor, public_id, token, question)).status_code == 200
    (row,) = (await owner.client.get(conversations_path(owner, project_id))).json()["items"]
    messages = (await opened(owner, project_id, row["id"]))["messages"]
    first_reply, second_reply = [m for m in messages if m["role"] == "assistant"]

    first = (await prefill(owner, project_id, agent_id, first_reply["id"])).json()
    second = (await prefill(owner, project_id, agent_id, second_reply["id"])).json()

    assert first["question"] == "Hello there"
    assert second["question"] == "How much annual leave do I get?"
    assert [s["passage"] for s in second["expected_sources"]] == [LEAVE]


async def test_prefill_is_refused_for_purged_text_and_other_agents_messages(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    answer_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    other_agent = await create_automatic_agent(owner, project_id, "Other helper")
    conversation_id, reply = await playground_reply(owner, project_id, agent_id, "Leave?")
    _, other_reply = await playground_reply(owner, project_id, other_agent["id"], "Leave?")
    question = (await opened(owner, project_id, conversation_id))["messages"][0]["id"]

    # Another Agent's Message, a question rather than a reply, and no Message at all.
    for message_id in (other_reply, question, str(uuid.uuid4())):
        refused = await prefill(owner, project_id, agent_id, message_id)
        assert refused.status_code == 404, message_id
    # Another Organisation's Member doesn't find the Agent.
    stranger = await tenant_factory()
    assert (await prefill(stranger, project_id, agent_id, reply)).status_code == 404

    async with app.state.sessionmaker() as session:
        await purge_messages(
            session,
            Message.conversation_id == uuid.UUID(conversation_id),
            now=app.state.clock.now(),
        )
        await session.commit()

    refused = await prefill(owner, project_id, agent_id, reply)
    assert (refused.status_code, refused.json()) == (409, {"detail": PURGED})


# Saving a case from a Message


async def test_saving_a_case_from_a_message_and_deleting_one_are_audit_events(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    answer_with(app, three_tokens)
    editor, project_id, agent_id = await ready_agent(
        app, owner, await member_factory(owner, "editor")
    )
    _, reply = await playground_reply(editor, project_id, agent_id, "How much leave?")
    offered = (await prefill(editor, project_id, agent_id, reply)).json()
    path = cases_path(editor, project_id, agent_id)

    written = await add_case(editor, project_id, agent_id, reference_answer="25 days.")
    copied = await add_case(
        editor,
        project_id,
        agent_id,
        question=offered["question"] + " A year?",
        expected_sources=[
            source(s["document_id"], s["passage"]) for s in offered["expected_sources"]
        ],
        source="from_message",
    )
    edited = await editor.client.put(
        f"{path}/{copied['id']}", json={"question": "Leave a year?", "reference_answer": "25."}
    )

    assert (written["source"], copied["source"]) == ("written", "from_message")
    assert copied["question"] == "How much leave? A year?"
    assert edited.status_code == 200
    # Editing keeps where it came from.
    assert edited.json()["source"] == "from_message"
    (added,) = await audit_events(owner, ADDED_FROM_MESSAGE)
    assert added["actor"]["id"] == editor.member_id
    assert added["target"] == {"type": "agent", "id": agent_id}
    # The case and the Agent, never the question.
    assert added["before"] is None
    assert added["after"] == {"case_id": copied["id"]}
    assert "leave" not in str(added).lower()
    assert await audit_events(owner, CASE_DELETED) == []

    for case in (written, copied):
        assert (await editor.client.delete(f"{path}/{case['id']}")).status_code == 204

    deleted = await audit_events(owner, CASE_DELETED)
    target = {"type": "agent", "id": agent_id}
    assert [(e["target"], e["before"], e["after"]) for e in deleted] == [
        (target, {"case_id": copied["id"], "source": "from_message"}, None),
        (target, {"case_id": written["id"], "source": "written"}, None),
    ]
    assert {e["actor"]["id"] for e in deleted} == {editor.member_id}
    assert len(await audit_events(owner, ADDED_FROM_MESSAGE)) == 1


async def test_the_purge_clears_the_source_conversation_and_leaves_the_case(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    conversation_id, reply = await playground_reply(owner, project_id, agent_id, "Leave?")
    offered = (await prefill(owner, project_id, agent_id, reply)).json()
    case = await add_case(
        owner,
        project_id,
        agent_id,
        question=offered["question"],
        expected_sources=[
            source(s["document_id"], s["passage"]) for s in offered["expected_sources"]
        ],
        source="from_message",
    )
    # The case holds no reference to the Conversation or the Message.
    assert conversation_id not in str(case)
    assert reply not in str(case)

    async with app.state.sessionmaker() as session:
        purged = await purge_messages(
            session,
            Message.conversation_id == uuid.UUID(conversation_id),
            now=app.state.clock.now(),
        )
        await session.commit()

    assert purged == 2
    messages = (await opened(owner, project_id, conversation_id))["messages"]
    assert [m["content"] for m in messages] == ["", ""]
    read = await owner.client.get(f"{cases_path(owner, project_id, agent_id)}/{case['id']}")
    assert read.json() == case


# Copying from another Agent


def copy_path(member: SignedUpMember, project_id: str, agent_id: str) -> str:
    return evaluation_path(member, project_id, agent_id, "cases", "copy")


async def copy_cases(
    member: SignedUpMember, project_id: str, agent_id: str, from_agent: str, case_ids: list[str]
) -> httpx.Response:
    return await member.client.post(
        copy_path(member, project_id, agent_id),
        json={"agent_id": from_agent, "case_ids": case_ids},
    )


async def test_cases_are_copied_from_another_agent_as_independent_copies(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    editor, project_id, source_agent = await ready_agent(
        app, owner, await member_factory(owner, "editor")
    )
    leave = await leave_document(editor, project_id)
    target = (await create_agent(editor, project_id, "Second helper"))["id"]
    first = await add_case(
        editor, project_id, source_agent, expected_sources=[source(leave["id"], "25 days")]
    )
    clock.advance(1)
    second = await add_case(editor, project_id, source_agent, question="Q2", expect_fallback=True)
    await add_case(editor, project_id, source_agent, question="Not chosen", reference_answer="No")
    await add_case(editor, project_id, target, question="Already here", reference_answer="Yes")
    clock.advance(60)

    response = await copy_cases(
        editor, project_id, target, source_agent, [second["id"], first["id"]]
    )

    assert response.status_code == 201, response.text
    copies = response.json()
    # In the source set's order, after the cases already there.
    assert [c["question"] for c in copies] == ["How much leave do I get?", "Q2"]
    assert [c["question"] for c in await listed(editor, project_id, target)] == [
        "Already here",
        "How much leave do I get?",
        "Q2",
    ]
    copy_of_first, copy_of_second = copies
    assert copy_of_first["id"] not in (first["id"], second["id"])
    assert [
        (s["document_id"], s["passage"], s["stale"]) for s in copy_of_first["expected_sources"]
    ] == [(leave["id"], "25 days", False)]
    assert copy_of_second["expect_fallback"] is True
    assert copy_of_first["source"] == first["source"]
    assert copy_of_first["latest_result"] is None

    # Independent: editing or deleting the original leaves the copy as it was.
    path = cases_path(editor, project_id, source_agent)
    await editor.client.put(
        f"{path}/{first['id']}", json={"question": "Edited", "reference_answer": "A"}
    )
    await editor.client.delete(f"{path}/{second['id']}")
    assert await listed(editor, project_id, target) == [
        (await listed(editor, project_id, target))[0],
        copy_of_first,
        copy_of_second,
    ]


async def test_copying_is_refused_from_outside_the_project_or_for_others_cases(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    project_id = await create_project(owner)
    target = (await create_agent(owner, project_id, "Target"))["id"]
    sibling = (await create_agent(owner, project_id, "Sibling"))["id"]
    elsewhere_project = await create_project(owner, "Elsewhere")
    elsewhere = (await create_agent(owner, elsewhere_project, "Elsewhere"))["id"]
    theirs = await add_case(owner, elsewhere_project, elsewhere, reference_answer="A")
    own = await add_case(owner, project_id, target, reference_answer="A")
    sibling_case = await add_case(owner, project_id, sibling, reference_answer="A")
    agent_refused = {"detail": "Choose another Agent of this Project to copy cases from."}
    cases_refused = {"detail": "Choose cases of the Agent you are copying from."}

    for from_agent, case_ids, detail in [
        (elsewhere, [theirs["id"]], agent_refused),
        (str(uuid.uuid4()), [theirs["id"]], agent_refused),
        (target, [own["id"]], agent_refused),
        (sibling, [theirs["id"]], cases_refused),
        (sibling, [sibling_case["id"], str(uuid.uuid4())], cases_refused),
    ]:
        refused = await copy_cases(owner, project_id, target, from_agent, case_ids)
        assert (refused.status_code, refused.json()) == (422, detail)
    empty = await copy_cases(owner, project_id, target, sibling, [])
    assert empty.status_code == 422
    stranger = await tenant_factory()
    refused = await copy_cases(stranger, project_id, target, sibling, [sibling_case["id"]])
    assert refused.status_code == 404
    assert [c["id"] for c in await listed(owner, project_id, target)] == [own["id"]]


# The cap


async def test_the_set_holds_at_most_the_cap_under_concurrent_creates_and_copies(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real Postgres, parallel requests from two Members: the Agent row lock queues them. The
    cap is lowered from 200 so the set fills quickly."""
    monkeypatch.setattr(evaluation_service, "CASES_MAX", 4)
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    sibling = (await create_agent(owner, project_id, "Sibling"))["id"]
    to_copy = [
        await add_case(owner, project_id, sibling, question=f"S{i}", reference_answer="A")
        for i in range(2)
    ]
    await add_case(owner, project_id, agent_id, question="First", reference_answer="A")

    responses = await asyncio.gather(
        *(
            post_case(member, project_id, agent_id, question=f"Q{i}", reference_answer="A")
            for i, member in enumerate([owner, editor] * 3)
        ),
        copy_cases(editor, project_id, agent_id, sibling, [c["id"] for c in to_copy]),
    )

    statuses = [r.status_code for r in responses]
    held = await listed(owner, project_id, agent_id)
    assert len(held) == 4
    assert len(held) == 1 + statuses[:6].count(201) + 2 * statuses[6:].count(201)
    assert set(statuses) <= {201, 409}
    refused = next(r for r in responses if r.status_code == 409)
    assert refused.json()["detail"].startswith("An Evaluation Set holds at most 4 cases, and this")
    full = await post_case(owner, project_id, agent_id, reference_answer="A")
    assert (full.status_code, full.json()) == (
        409,
        {
            "detail": (
                f"An Evaluation Set holds at most 4 cases, and this one has {len(held)}. "
                "Delete cases before adding more."
            )
        },
    )


# Searching and filtering the set


async def test_the_set_is_searched_and_filtered_by_kind_stale_flag_and_latest_result(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    judge_with(
        app,
        scripted(
            *(PASSING, PASSING, PASSING),
            *(PASSING, FAILING, PASSING),
            *(FAILING, FAILING, FAILING),
            *(UNAVAILABLE, UNAVAILABLE, UNAVAILABLE),
        ),
    )
    _, project_id, agent_id = await ready_agent(app, owner)
    leave = await leave_document(owner, project_id)
    ids: dict[str, str] = {}
    for question in ("Steady leave?", "Flaky leave?", "Wrong leave?", "Broken?"):
        ids[question] = (
            await add_case(
                owner, project_id, agent_id, question=question, reference_answer=REFERENCE
            )
        )["id"]
        clock.advance(1)
    await evaluated(owner, project_id, agent_id)
    clock.advance(1)
    ids["Parking?"] = (
        await add_case(
            owner,
            project_id,
            agent_id,
            question="Parking?",
            expected_sources=[source(leave["id"], "north car park")],
        )
    )["id"]
    clock.advance(1)
    ids["Unknown?"] = (
        await add_case(owner, project_id, agent_id, question="Unknown?", expect_fallback=True)
    )["id"]

    async def questions(**filters: Any) -> list[str]:
        return [c["question"] for c in await listed(owner, project_id, agent_id, **filters)]

    assert await questions() == list(ids)
    # The question's text, letter case aside.
    assert await questions(q="LEAVE") == ["Steady leave?", "Flaky leave?", "Wrong leave?"]
    assert await questions(q="flaky") == ["Flaky leave?"]
    assert await questions(kind="reference_answer") == list(ids)[:4]
    assert await questions(kind="expected_source") == ["Parking?"]
    assert await questions(kind="fallback") == ["Unknown?"]
    assert await questions(stale="true") == ["Parking?"]
    assert await questions(stale="false") == [q for q in ids if q != "Parking?"]
    assert await questions(result="pass") == ["Steady leave?"]
    assert await questions(result="unsteady") == ["Flaky leave?"]
    assert await questions(result="fail") == ["Wrong leave?"]
    assert await questions(result="error") == ["Broken?"]
    assert await questions(result="not_run") == ["Parking?", "Unknown?"]
    assert await questions(q="leave", result="pass", kind="reference_answer", stale="false") == [
        "Steady leave?"
    ]
    refused = await owner.client.get(cases_path(owner, project_id, agent_id), params={"kind": "x"})
    assert refused.status_code == 422
