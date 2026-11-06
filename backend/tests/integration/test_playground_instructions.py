"""API seam: the Playground Instructions picker. An Editor asks the Agent's Draft a question
with the Project Instructions Draft (the default) or a chosen Instructions Version, and each
answer records which one it ran with.

The chat model is a ``FunctionModel`` echo, so the Instructions text that reached the model is
read back from the answer. Everything else is observed through the API."""

import asyncio
import json
import uuid
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import text

from app.tenancy.erasure import erase_organisation
from tests.agents import (
    answer_text,
    answer_with,
    parse_sse,
    playground_path,
    start_conversation,
    trace_path,
)
from tests.conftest import SignedUpMember, TenantFactory
from tests.documents import create_project
from tests.integration.test_playground import echo, ready_agent
from tests.integration.test_project_deletion import delete_permanently
from tests.integration.test_project_instructions_versions import (
    _migrate,
    publish,
    revert,
    save_draft,
)
from tests.integration.test_projects import archive

NOT_IN_PROJECT = "That Instructions Version isn't one of this Project's."


async def ask_with(
    member: SignedUpMember,
    project_id: str,
    agent_id: str,
    conversation_id: str,
    question: str,
    body: dict[str, Any],
) -> httpx.Response:
    return await member.client.post(
        playground_path(member, project_id, agent_id, conversation_id, "messages"),
        json={"content": question, **body},
    )


def instructions_seen(response: httpx.Response) -> str:
    """The Project Instructions the model was given: the system part after the preamble."""
    assert response.status_code == 200, response.text
    parts = json.loads(answer_text(response))
    instructions: str = parts[1][2]
    return instructions


def done_event(response: httpx.Response) -> dict[str, Any]:
    (kind, data) = parse_sse(response.text)[-1]
    assert kind == "done"
    done: dict[str, Any] = data
    return done


async def versions(member: SignedUpMember, project_id: str) -> dict[int, str]:
    """Version number to ID, publishing two: v1 "Answer in English." and v2 "Answer in French."
    The Draft is then left as "Answer in Welsh.", unpublished."""
    ids = {}
    for number, rules in ((1, "Answer in English."), (2, "Answer in French.")):
        await save_draft(member, project_id, rules)
        response = await publish(member, project_id, f"Rules v{number}")
        assert response.status_code == 201, response.text
        ids[number] = response.json()["id"]
    await save_draft(member, project_id, "Answer in Welsh.")
    return ids


async def messages(
    member: SignedUpMember, project_id: str, agent_id: str, conversation_id: str
) -> list[dict[str, Any]]:
    response = await member.client.get(
        playground_path(member, project_id, agent_id, conversation_id)
    )
    assert response.status_code == 200, response.text
    found: list[dict[str, Any]] = response.json()["messages"]
    return found


async def test_by_default_the_playground_runs_the_instructions_draft(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, echo)
    member, project_id, agent_id = await ready_agent(app, owner)
    await versions(member, project_id)
    conversation = await start_conversation(member, project_id, agent_id)

    implicit = await ask_with(member, project_id, agent_id, conversation["id"], "Hi?", {})
    explicit = await ask_with(
        member,
        project_id,
        agent_id,
        conversation["id"],
        "Hello?",
        {"instructions_version_id": None},
    )

    # The unpublished Draft, not the Current Version, reaches the model both times.
    assert instructions_seen(implicit) == "Answer in Welsh."
    assert instructions_seen(explicit) == "Answer in Welsh."
    draft_marker = {
        "instructions_source": "draft",
        "instructions_version_id": None,
        "instructions_version_number": None,
    }
    for response in (implicit, explicit):
        done = done_event(response)
        assert {key: done[key] for key in draft_marker} == draft_marker
    question, answer, *_ = await messages(member, project_id, agent_id, conversation["id"])
    # Only answers say what produced them.
    assert {key: question[key] for key in draft_marker} == dict.fromkeys(draft_marker)
    assert {key: answer[key] for key in draft_marker} == draft_marker
    assert answer["config_source"] == "draft"


async def test_a_chosen_instructions_version_reaches_the_model_and_is_recorded(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, echo)
    member, project_id, agent_id = await ready_agent(app, owner)
    ids = await versions(member, project_id)
    conversation = await start_conversation(member, project_id, agent_id)

    # v1 is neither the Draft nor the Current Version (v2).
    older = await ask_with(
        member, project_id, agent_id, conversation["id"], "Hi?", {"instructions_version_id": ids[1]}
    )
    current = await ask_with(
        member,
        project_id,
        agent_id,
        conversation["id"],
        "Again?",
        {"instructions_version_id": ids[2]},
    )
    draft = await ask_with(member, project_id, agent_id, conversation["id"], "And now?", {})

    assert instructions_seen(older) == "Answer in English."
    assert instructions_seen(current) == "Answer in French."
    assert instructions_seen(draft) == "Answer in Welsh."
    assert {
        key: done_event(older)[key]
        for key in ("instructions_source", "instructions_version_id", "instructions_version_number")
    } == {
        "instructions_source": "version",
        "instructions_version_id": ids[1],
        "instructions_version_number": 1,
    }
    answers = [
        (m["instructions_source"], m["instructions_version_id"], m["instructions_version_number"])
        for m in await messages(member, project_id, agent_id, conversation["id"])
        if m["role"] == "assistant"
    ]
    # Each answer in the one Conversation keeps the Instructions it ran with.
    assert answers == [
        ("version", ids[1], 1),
        ("version", ids[2], 2),
        ("draft", None, None),
    ]


async def test_the_trace_names_the_instructions_an_answer_ran_with(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, echo)
    member, project_id, agent_id = await ready_agent(app, owner)
    ids = await versions(member, project_id)
    conversation = await start_conversation(member, project_id, agent_id)
    with_version = done_event(
        await ask_with(
            member,
            project_id,
            agent_id,
            conversation["id"],
            "Hi?",
            {"instructions_version_id": ids[2]},
        )
    )
    with_draft = done_event(
        await ask_with(member, project_id, agent_id, conversation["id"], "?", {})
    )

    traces = []
    for done in (with_version, with_draft):
        response = await member.client.get(
            trace_path(member, project_id, agent_id, conversation["id"], done["message_id"])
        )
        assert response.status_code == 200, response.text
        trace = response.json()
        traces.append(
            (
                trace["instructions_source"],
                trace["instructions_version_id"],
                trace["instructions_version_number"],
            )
        )
    assert traces == [("version", ids[2], 2), ("draft", None, None)]


async def test_a_reverted_version_can_still_be_chosen(app: FastAPI, owner: SignedUpMember) -> None:
    answer_with(app, echo)
    member, project_id, agent_id = await ready_agent(app, owner)
    ids = await versions(member, project_id)
    reverted = await revert(member, project_id)
    assert reverted.json()["number"] == 1
    conversation = await start_conversation(member, project_id, agent_id)

    response = await ask_with(
        member, project_id, agent_id, conversation["id"], "Hi?", {"instructions_version_id": ids[2]}
    )

    assert instructions_seen(response) == "Answer in French."


async def test_only_this_projects_instructions_versions_can_be_chosen(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    answer_with(app, echo)
    member, project_id, agent_id = await ready_agent(app, owner)
    await versions(member, project_id)
    # Another Project of the same Organisation, and another Organisation's Project.
    sibling = await create_project(member, "Sibling")
    sibling_ids = await versions(member, sibling)
    stranger = await tenant_factory()
    elsewhere = await create_project(stranger, "Elsewhere")
    elsewhere_ids = await versions(stranger, elsewhere)
    conversation = await start_conversation(member, project_id, agent_id)

    for version_id in (
        sibling_ids[1],
        elsewhere_ids[1],
        "00000000-0000-4000-8000-000000000000",
    ):
        response = await ask_with(
            member,
            project_id,
            agent_id,
            conversation["id"],
            "Hi?",
            {"instructions_version_id": version_id},
        )
        assert response.status_code == 422, response.text
        assert response.json() == {"detail": NOT_IN_PROJECT}
    not_an_id = await ask_with(
        member, project_id, agent_id, conversation["id"], "Hi?", {"instructions_version_id": "v1"}
    )
    assert not_an_id.status_code == 422
    # A refused question isn't saved.
    assert await messages(member, project_id, agent_id, conversation["id"]) == []


async def test_answers_saved_before_the_picker_are_marked_as_run_with_the_draft(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, echo)
    member, project_id, agent_id = await ready_agent(app, owner)
    conversation = await start_conversation(member, project_id, agent_id)
    response = await ask_with(member, project_id, agent_id, conversation["id"], "Hi?", {})
    assert response.status_code == 200, response.text
    # Back to 05-01's schema, where answers didn't record their Instructions; then forward.
    await asyncio.to_thread(_migrate, "downgrade", "0025_instructions_versions")
    try:
        await asyncio.to_thread(_migrate, "upgrade", "head")
    finally:
        # The pool's connections cached statements for the columns that were dropped.
        await app.state.engine.dispose()

    question, answer = await messages(member, project_id, agent_id, conversation["id"])

    assert question["instructions_source"] is None
    assert (
        answer["instructions_source"],
        answer["instructions_version_id"],
        answer["instructions_version_number"],
    ) == ("draft", None, None)


async def answered_with_a_version(
    app: FastAPI, owner: SignedUpMember
) -> tuple[SignedUpMember, str]:
    """A Project whose Agent answered with an Instructions Version in the Playground."""
    answer_with(app, echo)
    member, project_id, agent_id = await ready_agent(app, owner)
    ids = await versions(member, project_id)
    conversation = await start_conversation(member, project_id, agent_id)
    response = await ask_with(
        member, project_id, agent_id, conversation["id"], "Hi?", {"instructions_version_id": ids[1]}
    )
    assert response.status_code == 200, response.text
    return member, project_id


async def count(app: FastAPI, sql: str, **params: str) -> int:
    async with app.state.sessionmaker() as session:
        found: int = await session.scalar(text(sql), params)
    return found


async def test_permanently_deleting_the_project_removes_answers_that_name_its_versions(
    app: FastAPI, owner: SignedUpMember
) -> None:
    member, project_id = await answered_with_a_version(app, owner)
    assert (await archive(member, project_id)).status_code == 200

    response = await delete_permanently(member, project_id, "Handbook")

    assert response.status_code == 202, response.text
    assert (
        await count(
            app,
            "SELECT count(*) FROM project_instructions_versions WHERE project_id = :id",
            id=project_id,
        )
        == 0
    )


async def test_erasing_the_organisation_removes_answers_that_name_its_versions(
    app: FastAPI, owner: SignedUpMember
) -> None:
    await answered_with_a_version(app, owner)

    async with app.state.sessionmaker() as session:
        await erase_organisation(
            session, app.state.ingestion.object_store, uuid.UUID(owner.organisation_id)
        )

    assert (
        await count(
            app,
            "SELECT count(*) FROM messages WHERE organisation_id = :id",
            id=owner.organisation_id,
        )
        == 0
    )
