"""API seam: publishing an Agent. An Editor publishes the Agent's Draft as an immutable,
numbered Version that pins a Project Instructions Version and becomes the Agent's Live Version.
Everything is observed through the API, including the Live History and the Audit Events."""

import asyncio
import json
import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.agents import serving
from app.playground.service import answer
from app.runtime.prompt import preamble
from app.tenancy.erasure import erase_organisation
from tests.agents import (
    AUTOMATIC,
    FULL_DEFAULT_DRAFT,
    agents_path,
    answer_with,
    ask,
    create_agent,
    playground_path,
    save_draft,
    start_conversation,
    trace_path,
    use_default_model,
)
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project, project_path, upload
from tests.integration.test_agent_archive import archive as archive_agent
from tests.integration.test_agent_archive import delete_permanently as delete_agent
from tests.integration.test_playground import LEAVE, echo, without_canary
from tests.integration.test_project_instructions_versions import published as instructions
from tests.integration.test_projects import archive as archive_project
from tests.integration.test_provider_credentials import (
    OPENAI_KEY,
    added,
    audit_events,
    credentials_path,
)


async def publish(
    member: SignedUpMember, project_id: str, agent_id: str, **body: Any
) -> httpx.Response:
    return await member.client.post(
        agents_path(member, project_id, agent_id, "versions"), json={"note": "Ship it", **body}
    )


async def published(
    member: SignedUpMember, project_id: str, agent_id: str, **body: Any
) -> dict[str, Any]:
    response = await publish(member, project_id, agent_id, **body)
    assert response.status_code == 201, response.text
    version: dict[str, Any] = response.json()
    return version


async def agent(member: SignedUpMember, project_id: str, agent_id: str) -> dict[str, Any]:
    response = await member.client.get(agents_path(member, project_id, agent_id))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_publishing_makes_v1_the_live_version(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    created = await create_agent(owner, project_id)

    response = await publish(editor, project_id, created["id"], note="First release")

    assert response.status_code == 201, response.text
    version = response.json()
    assert version["number"] == 1
    assert version["note"] == "First release"
    assert version["author"] == {"id": editor.member_id, "name": editor.name}
    assert version["config"] == FULL_DEFAULT_DRAFT
    assert version["instructions_version"] is None
    assert (await agent(owner, project_id, created["id"]))["live_version"] == {
        "id": version["id"],
        "number": 1,
    }


async def versions(member: SignedUpMember, project_id: str, agent_id: str) -> dict[str, Any]:
    response = await member.client.get(agents_path(member, project_id, agent_id, "versions"))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def live_history(
    member: SignedUpMember, project_id: str, agent_id: str
) -> list[dict[str, Any]]:
    response = await member.client.get(agents_path(member, project_id, agent_id, "live-history"))
    assert response.status_code == 200, response.text
    body: list[dict[str, Any]] = response.json()
    return body


def number(version: dict[str, Any]) -> dict[str, Any]:
    return {"id": version["id"], "number": version["number"]}


# Not live


async def test_an_agent_without_a_version_is_not_live(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    created = await create_agent(owner, project_id)

    assert created["live_version"] is None
    assert (await agent(owner, project_id, created["id"]))["live_version"] is None
    listed = await owner.client.get(agents_path(owner, project_id))
    assert [a["live_version"] for a in listed.json()] == [None]
    assert await versions(owner, project_id, created["id"]) == {
        "live_version_id": None,
        "versions": [],
    }
    assert await live_history(owner, project_id, created["id"]) == []


# Publishing


async def test_the_version_is_a_snapshot_of_the_draft_that_later_edits_leave_alone(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    saved = await save_draft(owner, project_id, agent_id, {"behaviour": {"system_prompt": "v1"}})
    assert saved.status_code == 200, saved.text
    first = await published(owner, project_id, agent_id)

    await save_draft(owner, project_id, agent_id, {"behaviour": {"system_prompt": "Work"}})

    fetched = await owner.client.get(
        agents_path(owner, project_id, agent_id, "versions", first["id"])
    )
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == first
    assert first["config"]["behaviour"]["system_prompt"] == "v1"
    current = await agent(owner, project_id, agent_id)
    assert current["draft"]["behaviour"]["system_prompt"] == "Work"
    assert current["live_version"] == number(first)


async def test_each_publish_adds_the_next_version_and_makes_it_live(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    first = await published(owner, project_id, agent_id, note="First")
    await save_draft(editor, project_id, agent_id, {"behaviour": {"system_prompt": "Be brief."}})
    second = await published(editor, project_id, agent_id, note="  Shorter answers  ")

    listed = await versions(editor, project_id, agent_id)

    assert second["note"] == "Shorter answers"
    assert listed["live_version_id"] == second["id"]
    assert listed["versions"] == [second, first]
    assert [(v["number"], v["author"]["id"]) for v in listed["versions"]] == [
        (2, editor.member_id),
        (1, owner.member_id),
    ]
    assert second["created_at"] >= first["created_at"]
    assert (await agent(owner, project_id, agent_id))["live_version"] == number(second)


@pytest.mark.parametrize(
    "body", [{}, {"note": ""}, {"note": "   "}, {"note": "x" * 501}, {"note": None}]
)
async def test_publishing_takes_a_note(owner: SignedUpMember, body: dict[str, object]) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]

    response = await owner.client.post(
        agents_path(owner, project_id, agent_id, "versions"), json=body
    )

    assert response.status_code == 422, response.text
    assert (await versions(owner, project_id, agent_id))["versions"] == []


# Pinned Instructions


async def test_a_version_pins_the_current_instructions_version_by_default(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await instructions(owner, project_id, "Be kind.", "Rules")
    current = await instructions(owner, project_id, "Be kinder.", "Kinder rules")
    # A Draft edit after publishing isn't pinned: only Versions are.
    await owner.client.put(
        f"{project_path(owner, project_id)}/instructions", json={"markdown": "Unpublished"}
    )

    version = await published(owner, project_id, agent_id)

    assert version["instructions_version"] == {"id": current["id"], "number": 2}


async def test_an_editor_can_pin_an_older_instructions_version(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    older = await instructions(owner, project_id, "Be kind.", "Rules")
    await instructions(owner, project_id, "Be kinder.", "Kinder rules")

    version = await published(owner, project_id, agent_id, instructions_version_id=older["id"])

    assert version["instructions_version"] == {"id": older["id"], "number": 1}
    listed = await versions(owner, project_id, agent_id)
    assert listed["versions"][0]["instructions_version"] == {"id": older["id"], "number": 1}


async def test_only_an_instructions_version_of_the_agents_project_can_be_pinned(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    other_project_id = await create_project(owner, "Sales")
    agent_id = (await create_agent(owner, project_id))["id"]
    elsewhere = await instructions(owner, other_project_id, "Sell.", "Sales rules")

    responses = [
        await publish(owner, project_id, agent_id, instructions_version_id=pinned)
        for pinned in (elsewhere["id"], str(uuid.uuid4()))
    ]

    for response in responses:
        assert response.status_code == 422, response.text
        assert response.json()["detail"] == (
            "That Instructions Version isn't one of this Project's."
        )
    assert (await versions(owner, project_id, agent_id))["versions"] == []
    assert await audit_events(owner, "agent.published") == []


# Live History and the Audit log


async def test_each_publish_writes_a_live_history_entry(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    first = await published(owner, project_id, agent_id)
    second = await published(editor, project_id, agent_id)

    history = await live_history(owner, project_id, agent_id)

    assert [
        (e["from_version"], e["to_version"], e["action"], e["actor"], e["bulk_operation_id"])
        for e in history
    ] == [
        (
            number(first),
            number(second),
            "publish",
            {"id": editor.member_id, "name": editor.name},
            None,
        ),
        (None, number(first), "publish", {"id": owner.member_id, "name": owner.name}, None),
    ]
    assert history[0]["occurred_at"] >= history[1]["occurred_at"]


async def test_publishing_is_recorded_as_an_audit_event(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    pinned = await instructions(owner, project_id, "Be kind.", "Rules")
    first = await published(owner, project_id, agent_id, note="First")
    second = await published(editor, project_id, agent_id, note="Second")

    events = await audit_events(owner, "agent.published")

    assert [(e["actor"]["id"], e["target"], e["before"], e["after"]) for e in events] == [
        (
            editor.member_id,
            {"type": "agent", "id": agent_id},
            {"live_version": {"version_id": first["id"], "number": 1}},
            {
                "live_version": {
                    "version_id": second["id"],
                    "number": 2,
                    "note": "Second",
                    "instructions_version": {"version_id": pinned["id"], "number": 1},
                }
            },
        ),
        (
            owner.member_id,
            {"type": "agent", "id": agent_id},
            {"live_version": None},
            {
                "live_version": {
                    "version_id": first["id"],
                    "number": 1,
                    "note": "First",
                    "instructions_version": {"version_id": pinned["id"], "number": 1},
                }
            },
        ),
    ]


# Refusals


async def test_an_archived_agent_or_project_cannot_be_published(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    other_id = (await create_agent(owner, project_id, "FAQ"))["id"]
    assert (await archive_agent(owner, project_id, agent_id)).status_code == 200

    archived_agent = await publish(owner, project_id, agent_id)
    assert (await archive_project(owner, project_id)).status_code == 200
    archived_project = await publish(owner, project_id, other_id)

    assert archived_agent.status_code == 409
    assert archived_agent.json()["detail"] == "This Agent is archived. An Owner can restore it."
    assert archived_project.status_code == 409
    assert "archived" in archived_project.json()["detail"]
    # Both can still be read.
    assert (await versions(owner, project_id, agent_id))["versions"] == []
    assert await live_history(owner, project_id, other_id) == []
    assert await audit_events(owner, "agent.published") == []


async def test_versions_are_not_found_outside_their_agent_and_organisation(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    stranger = await tenant_factory()
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    other_agent_id = (await create_agent(owner, project_id, "FAQ"))["id"]
    version = await published(owner, project_id, agent_id)
    missing = str(uuid.uuid4())
    stranger_path = f"/api/organisations/{owner.organisation_id}/projects/{project_id}/agents"

    responses = [
        await owner.client.get(
            agents_path(owner, project_id, other_agent_id, "versions", version["id"])
        ),
        await owner.client.get(agents_path(owner, project_id, agent_id, "versions", missing)),
        await owner.client.post(
            agents_path(owner, project_id, missing, "versions"), json={"note": "x"}
        ),
        await owner.client.get(agents_path(owner, project_id, missing, "versions")),
        await owner.client.get(agents_path(owner, project_id, missing, "live-history")),
        await stranger.client.post(f"{stranger_path}/{agent_id}/versions", json={"note": "x"}),
        await stranger.client.get(f"{stranger_path}/{agent_id}/versions/{version['id']}"),
    ]

    assert [r.status_code for r in responses] == [404] * len(responses)
    assert (await versions(owner, project_id, agent_id))["versions"] == [version]


# Immutability


async def test_versions_cannot_be_changed_through_the_api(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    version = await published(owner, project_id, agent_id)
    collection = agents_path(owner, project_id, agent_id, "versions")
    item = f"{collection}/{version['id']}"
    history = agents_path(owner, project_id, agent_id, "live-history")

    attempts = [
        await owner.client.request(method, path, json={"note": "Changed"})
        for path in (collection, item, history)
        for method in ("PUT", "PATCH", "DELETE")
    ] + [await owner.client.post(item, json={"note": "Changed"})]

    assert [r.status_code for r in attempts] == [405] * len(attempts)
    assert (await versions(owner, project_id, agent_id))["versions"] == [version]


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE agent_versions SET note = 'x' WHERE agent_id = :id",
        "UPDATE agent_versions SET config = '{}'::jsonb WHERE agent_id = :id",
        "UPDATE agent_live_history SET action = 'revert' WHERE agent_id = :id",
    ],
)
async def test_the_database_refuses_to_change_a_version_or_its_live_history(
    app: FastAPI, owner: SignedUpMember, statement: str
) -> None:
    """Defence in depth: even a direct UPDATE can't rewrite a Version or the Live History."""
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    version = await published(owner, project_id, agent_id)
    history = await live_history(owner, project_id, agent_id)

    async with app.state.sessionmaker() as session:
        with pytest.raises(DBAPIError, match="immutable"):
            await session.execute(text(statement), {"id": agent_id})

    assert (await versions(owner, project_id, agent_id))["versions"] == [version]
    assert await live_history(owner, project_id, agent_id) == history


# Concurrency


async def test_concurrent_publishes_get_consecutive_unique_numbers(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    """Real Postgres, parallel requests from two Members: the Agent row lock queues them."""
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]

    responses = await asyncio.gather(
        *(
            publish(member, project_id, agent_id, note=f"Publish {i}")
            for i, member in enumerate([owner, editor] * 4)
        )
    )

    assert [r.status_code for r in responses] == [201] * 8
    assert sorted(r.json()["number"] for r in responses) == list(range(1, 9))
    listed = await versions(owner, project_id, agent_id)
    assert [v["number"] for v in listed["versions"]] == list(range(8, 0, -1))
    # The last to take the lock is Live, and each entry moved Live on from the one before.
    assert listed["live_version_id"] == listed["versions"][0]["id"]
    history = await live_history(owner, project_id, agent_id)
    assert [e["to_version"]["number"] for e in history] == list(range(8, 0, -1))
    assert [e["from_version"] and e["from_version"]["number"] for e in history] == [
        7,
        6,
        5,
        4,
        3,
        2,
        1,
        None,
    ]


# Message attribution


async def test_playground_messages_record_the_draft_even_once_the_agent_is_live(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, echo)
    await use_default_model(owner)
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await published(owner, project_id, agent_id)
    conversation = await start_conversation(owner, project_id, agent_id)

    response = await ask(owner, project_id, agent_id, conversation["id"], "How much leave?")

    assert response.status_code == 200, response.text
    saved = await owner.client.get(playground_path(owner, project_id, agent_id, conversation["id"]))
    question, reply = saved.json()["messages"]
    assert (question["config_source"], question["agent_version_id"]) == (None, None)
    assert (reply["config_source"], reply["agent_version_id"]) == ("draft", None)
    trace = await owner.client.get(
        trace_path(owner, project_id, agent_id, conversation["id"], reply["id"])
    )
    assert (trace.json()["config_source"], trace.json()["agent_version_id"]) == ("draft", None)


async def knowledgeable_project(app: FastAPI, owner: SignedUpMember) -> str:
    """A Project holding the leave policy, so questions retrieve a Chunk rather than fall back,
    in an Organisation with a Default Model answering with the echoing ``FunctionModel``."""
    answer_with(app, echo)
    await use_default_model(owner)
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "leave.txt", LEAVE.encode())
    return project_id


async def serve(app: FastAPI, public_id: str, question: str) -> tuple[str, dict[str, Any]]:
    """Asks the Agent's Live Version, as the embed (spec 06) will; returns the answer and the
    saved answer Message's attribution."""
    async with app.state.sessionmaker() as session:
        conversation_id = await serving.start_conversation(
            session, public_id, now=app.state.clock.now()
        )
        prepared = await serving.prepare_turn(
            session, public_id, conversation_id, question, now=app.state.clock.now()
        )
    events = [
        event
        async for event in answer(
            prepared,
            sessionmaker=app.state.sessionmaker,
            gateway=app.state.model_gateway,
            guardrails=app.state.guardrails,
            embedders=app.state.ingestion.embedders,
            clock=app.state.clock,
        )
    ]
    tokens = "".join(getattr(event, "text", "") for event in events[:-1])
    async with app.state.sessionmaker() as session:
        row = (
            await session.execute(
                text(
                    "SELECT config_source, agent_version_id::text, c.is_playground "
                    "FROM messages m JOIN conversations c ON c.id = m.conversation_id "
                    "WHERE m.id = :id"
                ),
                {"id": events[-1].message_id},  # type: ignore[union-attr]
            )
        ).one()
    return tokens, dict(row._mapping)


async def test_served_messages_record_the_live_version_and_run_its_pinned_instructions(
    app: FastAPI, owner: SignedUpMember
) -> None:
    """The runtime contract spec 06 serves through: no API serves Visitors yet, so the serving
    module is driven directly with the echoing ``FunctionModel``."""
    project_id = await knowledgeable_project(app, owner)
    created = await create_agent(owner, project_id)
    agent_id = created["id"]
    await instructions(owner, project_id, "Pinned rules.", "Rules")
    # Automatic, so the model is given the Automatic preamble.
    live = {"behaviour": {"system_prompt": "Live prompt."}, "retrieval": AUTOMATIC}
    await save_draft(owner, project_id, agent_id, live)
    version = await published(owner, project_id, agent_id)
    # Neither the Draft nor newer Instructions reach a Visitor until they are published.
    await save_draft(owner, project_id, agent_id, {"behaviour": {"system_prompt": "Draft prompt."}})
    await instructions(owner, project_id, "Newer rules.", "Newer")

    reply, attribution = await serve(app, created["public_id"], "How much leave?")

    parts = json.loads(reply)
    assert [part[2] for part in parts[:3]] == [
        preamble("{canary}"),
        "Pinned rules.",
        "Live prompt.",
    ]
    assert attribution == {
        "config_source": "version",
        "agent_version_id": version["id"],
        "is_playground": False,
    }


async def test_a_version_without_instructions_runs_with_none(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await knowledgeable_project(app, owner)
    created = await create_agent(owner, project_id)
    # The Instructions Draft is never published, so the Version pins no Instructions Version.
    await owner.client.put(
        f"{project_path(owner, project_id)}/instructions", json={"markdown": "Unpublished"}
    )
    # Automatic, so the model is given the Automatic preamble.
    draft = {"behaviour": {"system_prompt": "Prompt."}, "retrieval": AUTOMATIC}
    await save_draft(owner, project_id, created["id"], draft)
    await published(owner, project_id, created["id"])

    reply, _ = await serve(app, created["public_id"], "Hi")

    parts = json.loads(reply)
    assert [part[2] for part in parts[:2]] == [preamble("{canary}"), "Prompt."]
    assert "Unpublished" not in without_canary(reply)


async def test_an_agent_that_is_not_live_serves_nothing(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    never_published = await create_agent(owner, project_id)
    archived = await create_agent(owner, project_id, "Archived")
    await published(owner, project_id, archived["id"])
    assert (await archive_agent(owner, project_id, archived["id"])).status_code == 200

    async with app.state.sessionmaker() as session:
        with pytest.raises(serving.AgentNotLiveError):
            await serving.start_conversation(
                session, never_published["public_id"], now=app.state.clock.now()
            )
        for public_id in (archived["public_id"], "agt_unknown"):
            with pytest.raises(serving.AgentNotServedError):
                await serving.start_conversation(session, public_id, now=app.state.clock.now())


async def test_a_served_question_needs_a_visitor_conversation_of_that_agent(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    created = await create_agent(owner, project_id)
    await published(owner, project_id, created["id"])
    playground = await start_conversation(owner, project_id, created["id"])

    async with app.state.sessionmaker() as session:
        for conversation_id in (uuid.UUID(playground["id"]), uuid.uuid4()):
            with pytest.raises(serving.AgentNotServedError):
                await serving.prepare_turn(
                    session, created["public_id"], conversation_id, "Hi", now=app.state.clock.now()
                )


# Deletion still works with Versions


async def test_deleting_the_agent_or_erasing_the_organisation_removes_its_versions(
    app: FastAPI, owner: SignedUpMember
) -> None:
    """Agents point at Versions, Versions at Instructions Versions, Messages and Live History
    at Versions, and none of them can be updated; the cascades still succeed."""
    project_id = await knowledgeable_project(app, owner)
    await instructions(owner, project_id, "Rules.", "Rules")
    doomed = await create_agent(owner, project_id, "Doomed")
    kept = await create_agent(owner, project_id, "Kept")
    for created in (doomed, kept):
        await published(owner, project_id, created["id"])
        await published(owner, project_id, created["id"])
        await serve(app, created["public_id"], "Hi")
    assert (await archive_agent(owner, project_id, doomed["id"])).status_code == 200

    deleted = await delete_agent(owner, project_id, doomed["id"], "Doomed")

    assert deleted.status_code == 204, deleted.text
    count = "SELECT count(*) FROM agent_versions WHERE organisation_id = :id"
    async with app.state.sessionmaker() as session:
        assert await session.scalar(text(count), {"id": owner.organisation_id}) == 2
        await erase_organisation(
            session, app.state.ingestion.object_store, uuid.UUID(owner.organisation_id)
        )
    async with app.state.sessionmaker() as session:
        assert await session.scalar(text(count), {"id": owner.organisation_id}) == 0


# The Live Version keeps its credentials


async def test_a_credential_the_live_version_uses_cant_be_deleted(owner: SignedUpMember) -> None:
    """Visitors are served the Live Version, so a credential it names stays referenced after
    the Draft stops naming it, until another Version without it goes Live."""
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY)
    project_id = await create_project(owner)
    created = await create_agent(owner, project_id, "HR helper")
    model = {"credential_id": openai["id"], "model": "gpt-4.1"}
    await save_draft(owner, project_id, created["id"], {"behaviour": {"model": model}})
    await published(owner, project_id, created["id"])
    await save_draft(owner, project_id, created["id"], FULL_DEFAULT_DRAFT)
    path = credentials_path(owner.organisation_id, openai["id"])

    refused = await owner.client.delete(path)

    assert refused.status_code == 409, refused.text
    assert refused.json()["references"] == [
        {"kind": "agent", "id": created["id"], "name": "HR helper Live Version (model)"}
    ]
    await published(owner, project_id, created["id"])
    assert (await owner.client.delete(path)).status_code == 204
