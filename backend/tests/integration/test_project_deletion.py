"""API seam plus task seam: an Owner permanently deletes an archived Project after typing its
name, and the deletion cascade (a Celery task, run eagerly here) removes everything in it.

Outcomes are read through the API: the Project, the Projects lists, the Project's routes and
the Audit list. Two facts have no API surface once the Project is gone, and are read directly,
as the shared test seams allow: whether the Project's rows (Documents, Chunks, Tags, Agents,
Conversations...) are gone, and what the object store still holds.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.projects.tasks import delete_project
from app.storage.memory import InMemoryObjectStore
from tests.agents import answer_with, ask, start_conversation
from tests.conftest import MemberFactory, SignedUpMember
from tests.documents import documents, put_to_memory_store, start_upload, upload
from tests.fakes.clock import ControllableClock
from tests.integration.test_playground import ready_agent, three_tokens
from tests.integration.test_projects import (
    archive,
    audit_events,
    create_project,
    listed,
    projects_path,
    restore,
)

NOT_ARCHIVED = "Only an archived Project can be deleted. Archive it first."
NAME_MISMATCH = "Type the Project's name exactly to delete it."


async def delete_permanently(
    member: SignedUpMember, project_id: str, typed_name: str
) -> httpx.Response:
    return await member.client.request(
        "DELETE",
        projects_path(member.organisation_id, project_id),
        json={"confirm_name": typed_name},
    )


async def archived_project(owner: SignedUpMember, name: str = "HR handbook") -> dict[str, Any]:
    project = await create_project(owner, name)
    response = await archive(owner, project["id"])
    assert response.status_code == 200, response.text
    archived: dict[str, Any] = response.json()
    return archived


def stored_keys(app: FastAPI) -> list[str]:
    """The keys the in-memory object store holds; stored files have no API surface."""
    store = app.state.ingestion.object_store
    assert isinstance(store, InMemoryObjectStore)
    return sorted(store.objects)


# Rows of each table that belong to a Project, directly or through its Agents and Conversations.
PROJECT_ROWS = {
    "documents": "SELECT count(*) FROM documents WHERE project_id = :id",
    "staged_editions": "SELECT count(*) FROM staged_editions WHERE project_id = :id",
    "chunks": "SELECT count(*) FROM chunks WHERE project_id = :id",
    "tags": "SELECT count(*) FROM tags WHERE project_id = :id",
    "document_tags": (
        "SELECT count(*) FROM document_tags t JOIN tags g ON g.id = t.tag_id"
        " WHERE g.project_id = :id"
    ),
    "agents": "SELECT count(*) FROM agents WHERE project_id = :id",
    "agent_drafts": (
        "SELECT count(*) FROM agent_drafts d JOIN agents a ON a.id = d.agent_id"
        " WHERE a.project_id = :id"
    ),
    "projects": "SELECT count(*) FROM projects WHERE id = :id",
}


async def project_rows(app: FastAPI, project_id: str) -> dict[str, int]:
    async with app.state.sessionmaker() as session:
        return {
            table: (await session.scalar(text(query), {"id": project_id})) or 0
            for table, query in PROJECT_ROWS.items()
        }


async def conversation_rows(app: FastAPI, agent_id: str) -> dict[str, int]:
    """The Agent's Conversations, their Messages and the Messages' retrieved Chunks: once the
    Agent is gone, it has no API surface."""
    queries = {
        "conversations": "SELECT count(*) FROM conversations WHERE agent_id = :id",
        "messages": (
            "SELECT count(*) FROM messages m JOIN conversations c ON c.id = m.conversation_id"
            " WHERE c.agent_id = :id"
        ),
        "message_retrievals": (
            "SELECT count(*) FROM message_retrievals r JOIN messages m ON m.id = r.message_id"
            " JOIN conversations c ON c.id = m.conversation_id WHERE c.agent_id = :id"
        ),
    }
    async with app.state.sessionmaker() as session:
        return {
            table: (await session.scalar(text(query), {"id": agent_id})) or 0
            for table, query in queries.items()
        }


async def test_an_owner_permanently_deletes_an_archived_project(owner: SignedUpMember) -> None:
    kept = await create_project(owner, "Kept")
    project = await archived_project(owner, "HR handbook")

    response = await delete_permanently(owner, project["id"], "HR handbook")

    assert (response.status_code, response.content) == (202, b"")
    opened = await owner.client.get(projects_path(owner.organisation_id, project["id"]))
    assert opened.status_code == 404
    assert await listed(owner, archived="true") == []
    assert [p["id"] for p in await listed(owner)] == [kept["id"]]


async def test_deletion_cascades_to_everything_in_the_project(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, three_tokens)
    # A Project with a Document, an Agent and a Playground Conversation that retrieved a Chunk.
    _, project_id, agent_id = await ready_agent(app, owner)
    path = projects_path(owner.organisation_id, project_id)
    second = await upload(app, owner, project_id, "expenses.md", b"# Expenses\n\nWithin 30 days.")
    tag = (await owner.client.post(f"{path}/tags", json={"name": "HR"})).json()
    tagged = await owner.client.post(
        f"{path}/documents/tags", json={"document_ids": [second["id"]], "add": [tag["id"]]}
    )
    conversation = await start_conversation(owner, project_id, agent_id)
    asked = await ask(owner, project_id, agent_id, conversation["id"], "How much leave?")
    # An upload started and PUT to the store, never confirmed.
    started = (await start_upload(owner, project_id, "draft.md", 5)).json()
    await put_to_memory_store(app, started["url"], b"draft", started["content_type"])
    # Another Project, which keeps everything.
    other_id = (await create_project(owner, "Sales"))["id"]
    await upload(app, owner, other_id, "pricing.md", b"# Pricing\n\nList prices.")
    other_documents = await documents(owner, other_id)
    before = await project_rows(app, project_id)
    other_before = await project_rows(app, other_id)
    await archive(owner, project_id)

    response = await delete_permanently(owner, project_id, "Handbook")

    assert (tagged.status_code, asked.status_code, response.status_code) == (204, 200, 202)
    # Everything was there before ...
    assert before == {
        "documents": 2,
        "staged_editions": 0,
        "chunks": 2,
        "tags": 1,
        "document_tags": 1,
        "agents": 1,
        "agent_drafts": 1,
        "projects": 1,
    }
    # ... and nothing is left: rows, Conversations, and stored files.
    assert await project_rows(app, project_id) == dict.fromkeys(PROJECT_ROWS, 0)
    assert await conversation_rows(app, agent_id) == {
        "conversations": 0,
        "messages": 0,
        "message_retrievals": 0,
    }
    assert not any(project_id in key for key in stored_keys(app))
    for route in (path, f"{path}/documents", f"{path}/agents", f"{path}/tags"):
        assert (await owner.client.get(route)).status_code == 404
    # The other Project keeps its rows, Documents and stored files.
    assert await project_rows(app, other_id) == other_before
    assert await documents(owner, other_id) == other_documents
    assert len([key for key in stored_keys(app) if other_id in key]) == 2


async def test_deletion_is_an_audit_event(owner: SignedUpMember, clock: ControllableClock) -> None:
    project = await create_project(owner, "HR handbook", "Policies")
    await archive(owner, project["id"])
    clock.advance(timedelta(minutes=5))

    await delete_permanently(owner, project["id"], "HR handbook")

    (deleted,) = await audit_events(owner, "project.deleted")
    assert deleted["actor"]["id"] == owner.member_id
    assert deleted["target"] == {"type": "project", "id": project["id"]}
    assert deleted["before"] == {
        "name": "HR handbook",
        "description": "Policies",
        "document_count": 0,
        "agent_count": 0,
    }
    assert deleted["after"] is None
    assert datetime.fromisoformat(deleted["occurred_at"]) == clock.now()


async def test_editors_cannot_delete_a_project(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project = await archived_project(owner)

    response = await delete_permanently(editor, project["id"], "HR handbook")

    assert (response.status_code, response.json()) == (403, {"detail": "Only Owners can do this"})
    assert await listed(owner, archived="true") == [project]


async def test_only_an_archived_project_can_be_deleted(owner: SignedUpMember) -> None:
    project = await create_project(owner, "HR handbook")

    response = await delete_permanently(owner, project["id"], "HR handbook")

    assert (response.status_code, response.json()) == (409, {"detail": NOT_ARCHIVED})
    assert await listed(owner) == [project]


@pytest.mark.parametrize("typed", ["", "HR", "hr handbook", "HR handbook ", "HR  handbook"])
async def test_the_project_name_must_be_typed_exactly(owner: SignedUpMember, typed: str) -> None:
    project = await archived_project(owner)

    response = await delete_permanently(owner, project["id"], typed)
    missing = await owner.client.request(
        "DELETE", projects_path(owner.organisation_id, project["id"]), json={}
    )

    assert (response.status_code, response.json()) == (400, {"detail": NAME_MISMATCH})
    assert missing.status_code == 422
    assert await listed(owner, archived="true") == [project]


async def test_refused_deletions_record_no_audit_event_and_delete_nothing(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project = await create_project(owner, "HR handbook")
    await upload(app, owner, project["id"], "leave.md", b"# Leave\n\n25 days.")
    await delete_permanently(owner, project["id"], "HR handbook")  # not archived
    await archive(owner, project["id"])
    await delete_permanently(owner, project["id"], "HR")  # wrong name
    await delete_permanently(editor, project["id"], "HR handbook")  # not an Owner

    assert await audit_events(owner, "project.deleted") == []
    assert [d["name"] for d in await documents(owner, project["id"])] == ["leave.md"]
    assert len(stored_keys(app)) == 2


async def test_an_unknown_project_is_not_found(owner: SignedUpMember) -> None:
    project = await archived_project(owner)
    await delete_permanently(owner, project["id"], "HR handbook")

    again = await delete_permanently(owner, project["id"], "HR handbook")

    assert (again.status_code, again.json()) == (404, {"detail": "Not found"})
    assert len(await audit_events(owner, "project.deleted")) == 1


# The task seam: the cascade runs after the request, in a worker.


async def run_cascade(project_id: str, owner: SignedUpMember, clock: ControllableClock) -> None:
    """Runs the deletion cascade as a worker would, for a request made by ``owner`` now."""
    await asyncio.to_thread(
        delete_project.delay, project_id, owner.member_id, clock.now().isoformat()
    )


async def test_a_project_restored_before_the_cascade_runs_is_kept(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    project = await archived_project(owner)
    await upload_into_archived(app, owner, project["id"])
    await restore(owner, project["id"])

    # The cascade a deletion request enqueued runs only now, after the restore.
    await run_cascade(project["id"], owner, clock)

    assert [p["id"] for p in await listed(owner)] == [project["id"]]
    assert [d["name"] for d in await documents(owner, project["id"])] == ["leave.md"]
    assert len(stored_keys(app)) == 2
    assert await audit_events(owner, "project.deleted") == []


async def upload_into_archived(app: FastAPI, owner: SignedUpMember, project_id: str) -> None:
    """Restores the Project, uploads a Document, and archives it again."""
    await restore(owner, project_id)
    await upload(app, owner, project_id, "leave.md", b"# Leave\n\n25 days.")
    await archive(owner, project_id)


async def test_running_the_cascade_again_does_nothing(
    owner: SignedUpMember, clock: ControllableClock
) -> None:
    project = await archived_project(owner)
    await delete_permanently(owner, project["id"], "HR handbook")

    await run_cascade(project["id"], owner, clock)

    assert len(await audit_events(owner, "project.deleted")) == 1
