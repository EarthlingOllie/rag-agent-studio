"""API seam: Editors archive Agents they no longer need, without losing their history; Owners
restore them, or permanently delete an archived Agent after typing its name, which cascades to
its Draft and Conversations. Each change is an Audit Event.

Outcomes are read through the API. Once an Agent is deleted, whether its Conversations'
rows are gone has no API surface, so it is read directly, as the shared test seams allow.
"""

from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.agents import (
    FULL_DEFAULT_DRAFT,
    agents_path,
    answer_with,
    ask,
    create_agent,
    playground_path,
    save_draft,
    start_conversation,
    trace_path,
)
from tests.conftest import MemberFactory, SignedUpMember
from tests.documents import create_project
from tests.fakes.clock import ControllableClock
from tests.integration.test_playground import ready_agent, three_tokens
from tests.integration.test_project_deletion import conversation_rows
from tests.integration.test_projects import archive as archive_project
from tests.integration.test_provider_credentials import (
    ANTHROPIC_KEY,
    added,
    audit_events,
    credentials_path,
)

AGENT_ARCHIVED = "This Agent is archived. An Owner can restore it."
AGENT_NOT_ARCHIVED = "This Agent isn't archived."
PROJECT_ARCHIVED = "This Project is archived. An Owner can restore it."
ARCHIVE_BEFORE_DELETING = "Only an archived Agent can be deleted. Archive it first."
NAME_MISMATCH = "Type the Agent's name exactly to delete it."
OWNERS_ONLY = "Only Owners can do this"


async def archive(member: SignedUpMember, project_id: str, agent_id: str) -> httpx.Response:
    return await member.client.post(agents_path(member, project_id, agent_id, "archive"))


async def restore(member: SignedUpMember, project_id: str, agent_id: str) -> httpx.Response:
    return await member.client.post(agents_path(member, project_id, agent_id, "restore"))


async def delete_permanently(
    member: SignedUpMember, project_id: str, agent_id: str, typed_name: str
) -> httpx.Response:
    return await member.client.request(
        "DELETE", agents_path(member, project_id, agent_id), json={"confirm_name": typed_name}
    )


async def archived_agent(member: SignedUpMember, name: str = "HR helper") -> tuple[str, str]:
    """A Project with an archived Agent; returns their IDs."""
    project_id = await create_project(member)
    agent = await create_agent(member, project_id, name)
    response = await archive(member, project_id, agent["id"])
    assert response.status_code == 200, response.text
    return project_id, agent["id"]


async def listed(member: SignedUpMember, project_id: str, **params: str) -> list[str]:
    response = await member.client.get(agents_path(member, project_id), params=params)
    assert response.status_code == 200, response.text
    return [agent["name"] for agent in response.json()]


async def test_an_editor_archives_an_agent_and_it_leaves_the_list(
    owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(editor)
    agent = await create_agent(editor, project_id, "HR helper")
    await create_agent(editor, project_id, "Benefits FAQ")
    clock.advance(timedelta(hours=1))

    response = await archive(editor, project_id, agent["id"])

    assert response.status_code == 200, response.text
    archived: dict[str, Any] = response.json()
    assert datetime.fromisoformat(archived["archived_at"]) == clock.now()
    assert archived["draft"] == agent["draft"]
    assert await listed(editor, project_id) == ["Benefits FAQ"]
    assert await listed(editor, project_id, archived="true") == ["HR helper"]
    # Its page still opens, so its history can be read.
    opened = await editor.client.get(agents_path(editor, project_id, agent["id"]))
    assert opened.json() == archived
    (event,) = await audit_events(owner, "agent.archived")
    assert event["actor"]["id"] == editor.member_id
    assert event["target"] == {"type": "agent", "id": agent["id"]}
    assert event["before"] == {"name": "HR helper", "archived": False}
    assert event["after"] == {"name": "HR helper", "archived": True}
    assert datetime.fromisoformat(event["occurred_at"]) == clock.now()


async def test_an_archived_agent_cannot_be_archived_again_or_have_its_draft_changed(
    owner: SignedUpMember,
) -> None:
    project_id, agent_id = await archived_agent(owner)

    again = await archive(owner, project_id, agent_id)
    saved = await save_draft(owner, project_id, agent_id, {"retrieval": {"top_k": 3}})

    assert (again.status_code, again.json()["detail"]) == (409, AGENT_ARCHIVED)
    assert (saved.status_code, saved.json()["detail"]) == (409, AGENT_ARCHIVED)
    opened = await owner.client.get(agents_path(owner, project_id, agent_id))
    assert opened.json()["draft"] == FULL_DEFAULT_DRAFT
    assert len(await audit_events(owner, "agent.archived")) == 1


async def test_archiving_blocks_the_playground_but_keeps_its_conversations(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, three_tokens)
    _, project_id, agent_id = await ready_agent(app, owner)
    conversation = await start_conversation(owner, project_id, agent_id)
    asked = await ask(owner, project_id, agent_id, conversation["id"], "How much leave?")
    assert asked.status_code == 200, asked.text
    history = await owner.client.get(
        playground_path(owner, project_id, agent_id, conversation["id"])
    )
    answer_id = history.json()["messages"][1]["id"]
    trace = await owner.client.get(
        trace_path(owner, project_id, agent_id, conversation["id"], answer_id)
    )

    await archive(owner, project_id, agent_id)

    started = await owner.client.post(playground_path(owner, project_id, agent_id))
    again = await ask(owner, project_id, agent_id, conversation["id"], "And sick leave?")
    assert (started.status_code, started.json()["detail"]) == (409, AGENT_ARCHIVED)
    assert (again.status_code, again.json()["detail"]) == (409, AGENT_ARCHIVED)
    # Its history is kept and can still be read: nothing was added by the refused question.
    kept = await owner.client.get(playground_path(owner, project_id, agent_id, conversation["id"]))
    assert kept.json() == history.json()
    kept_trace = await owner.client.get(
        trace_path(owner, project_id, agent_id, conversation["id"], answer_id)
    )
    assert kept_trace.json() == trace.json()


async def test_an_owner_restores_an_archived_agent(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    answer_with(app, three_tokens)
    editor = await member_factory(owner, "editor")
    _, project_id, agent_id = await ready_agent(app, owner, editor)
    await archive(editor, project_id, agent_id)
    clock.advance(timedelta(minutes=5))

    by_editor = await restore(editor, project_id, agent_id)
    response = await restore(owner, project_id, agent_id)

    assert (by_editor.status_code, by_editor.json()["detail"]) == (403, OWNERS_ONLY)
    assert response.status_code == 200, response.text
    assert response.json()["archived_at"] is None
    assert await listed(editor, project_id) == ["HR helper"]
    assert await listed(editor, project_id, archived="true") == []
    # It is usable again: the Playground answers.
    conversation = await start_conversation(editor, project_id, agent_id)
    asked = await ask(editor, project_id, agent_id, conversation["id"], "How much leave?")
    assert asked.status_code == 200, asked.text
    (event,) = await audit_events(owner, "agent.restored")
    assert event["actor"]["id"] == owner.member_id
    assert event["target"] == {"type": "agent", "id": agent_id}
    assert event["before"] == {"name": "HR helper", "archived": True}
    assert event["after"] == {"name": "HR helper", "archived": False}
    assert datetime.fromisoformat(event["occurred_at"]) == clock.now()


async def test_only_an_archived_agent_can_be_restored(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)

    response = await restore(owner, project_id, agent["id"])

    assert (response.status_code, response.json()["detail"]) == (409, AGENT_NOT_ARCHIVED)
    assert await audit_events(owner, "agent.restored") == []


async def test_an_owner_permanently_deletes_an_archived_agent_after_typing_its_name(
    owner: SignedUpMember, clock: ControllableClock
) -> None:
    project_id, agent_id = await archived_agent(owner, "HR helper")
    kept = await create_agent(owner, project_id, "Benefits FAQ")
    agent = (await owner.client.get(agents_path(owner, project_id, agent_id))).json()
    clock.advance(timedelta(minutes=5))

    response = await delete_permanently(owner, project_id, agent_id, "HR helper")

    assert (response.status_code, response.content) == (204, b"")
    opened = await owner.client.get(agents_path(owner, project_id, agent_id))
    assert opened.status_code == 404
    assert await listed(owner, project_id) == ["Benefits FAQ"]
    assert await listed(owner, project_id, archived="true") == []
    assert (await owner.client.get(agents_path(owner, project_id, kept["id"]))).status_code == 200
    (event,) = await audit_events(owner, "agent.deleted")
    assert event["actor"]["id"] == owner.member_id
    assert event["target"] == {"type": "agent", "id": agent_id}
    assert event["before"] == {
        "name": "HR helper",
        "project_id": project_id,
        "public_id": agent["public_id"],
        "conversation_count": 0,
    }
    assert event["after"] is None
    assert datetime.fromisoformat(event["occurred_at"]) == clock.now()


async def test_deletion_cascades_to_the_draft_conversations_and_credential_references(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, three_tokens)
    credential_id = await _ready_agent_with_override(app, owner)
    project_id, agent_id, conversation_id = credential_id[1:]
    other_conversation = await start_conversation(owner, project_id, agent_id)
    before = await conversation_rows(app, agent_id)
    refused = await owner.client.delete(credentials_path(owner.organisation_id, credential_id[0]))
    await archive(owner, project_id, agent_id)

    response = await delete_permanently(owner, project_id, agent_id, "HR helper")

    assert response.status_code == 204, response.text
    assert refused.status_code == 409
    assert before == {"conversations": 2, "messages": 2, "message_retrievals": 1}
    assert await conversation_rows(app, agent_id) == dict.fromkeys(before, 0)
    for conversation in (conversation_id, other_conversation["id"]):
        gone = await owner.client.get(playground_path(owner, project_id, agent_id, conversation))
        assert gone.status_code == 404
    # The credential its Draft named is no longer referenced, so it can be deleted.
    freed = await owner.client.delete(credentials_path(owner.organisation_id, credential_id[0]))
    assert freed.status_code == 204, freed.text
    (event,) = await audit_events(owner, "agent.deleted")
    assert event["before"]["conversation_count"] == 2


async def _ready_agent_with_override(
    app: FastAPI, owner: SignedUpMember
) -> tuple[str, str, str, str]:
    """An Agent whose Draft names an Anthropic credential as its model override, with a
    Playground Conversation holding one answered question. Returns the credential, Project,
    Agent and Conversation IDs."""
    _, project_id, agent_id = await ready_agent(app, owner)
    credential = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY, name="Claude")
    credential_id = credential["id"]
    draft = {"behaviour": {"model": {"credential_id": credential_id, "model": "claude-haiku-4-5"}}}
    saved = await save_draft(owner, project_id, agent_id, draft)
    assert saved.status_code == 200, saved.text
    conversation = await start_conversation(owner, project_id, agent_id)
    asked = await ask(owner, project_id, agent_id, conversation["id"], "How much leave?")
    assert asked.status_code == 200, asked.text
    return credential_id, project_id, agent_id, conversation["id"]


@pytest.mark.parametrize("typed", ["", "hr helper", "HR helper ", "HR  helper", "Benefits FAQ"])
async def test_deletion_needs_the_name_typed_exactly(owner: SignedUpMember, typed: str) -> None:
    project_id, agent_id = await archived_agent(owner, "HR helper")

    response = await delete_permanently(owner, project_id, agent_id, typed)

    assert (response.status_code, response.json()["detail"]) == (400, NAME_MISMATCH)
    assert (await owner.client.get(agents_path(owner, project_id, agent_id))).status_code == 200
    assert await audit_events(owner, "agent.deleted") == []


async def test_only_an_archived_agent_can_be_deleted(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id, "HR helper")

    response = await delete_permanently(owner, project_id, agent["id"], "HR helper")

    assert (response.status_code, response.json()["detail"]) == (409, ARCHIVE_BEFORE_DELETING)
    assert await listed(owner, project_id) == ["HR helper"]


async def test_editors_cannot_delete_an_agent(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id, agent_id = await archived_agent(editor, "HR helper")

    response = await delete_permanently(editor, project_id, agent_id, "HR helper")

    assert (response.status_code, response.json()["detail"]) == (403, OWNERS_ONLY)
    assert await listed(editor, project_id, archived="true") == ["HR helper"]


async def test_an_archived_projects_agents_cannot_be_archived_restored_or_deleted(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    active = await create_agent(owner, project_id, "FAQ")
    archived = await create_agent(owner, project_id, "HR helper")
    await archive(owner, project_id, archived["id"])
    await archive_project(owner, project_id)

    responses = [
        await archive(owner, project_id, active["id"]),
        await restore(owner, project_id, archived["id"]),
        await delete_permanently(owner, project_id, archived["id"], "HR helper"),
    ]

    assert [(r.status_code, r.json()["detail"]) for r in responses] == [(409, PROJECT_ARCHIVED)] * 3


async def test_agents_of_another_project_are_not_found(owner: SignedUpMember) -> None:
    project_id, agent_id = await archived_agent(owner, "HR helper")
    other_project_id = await create_project(owner, "Sales")

    responses = [
        await archive(owner, other_project_id, agent_id),
        await restore(owner, other_project_id, agent_id),
        await delete_permanently(owner, other_project_id, agent_id, "HR helper"),
    ]

    assert [r.status_code for r in responses] == [404, 404, 404]
    assert await listed(owner, project_id, archived="true") == ["HR helper"]
