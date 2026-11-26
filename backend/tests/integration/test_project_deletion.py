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
from app.worker.celery_app import DELETE_PROJECT_TASK
from tests.agents import answer_with, ask, start_conversation
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.documents import documents, put_to_memory_store, start_upload, upload
from tests.fakes.clock import ControllableClock
from tests.fakes.jobs import RecordingJobPublisher
from tests.integration.test_interrupted_ingestion import sweep
from tests.integration.test_playground import ready_agent, three_tokens
from tests.integration.test_projects import (
    archive,
    audit_events,
    create_project,
    listed,
    projects_path,
    restore,
)
from tests.jobs import settle_jobs_in_flight

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


async def run_cascade(project_id: str) -> None:
    """Delivers the deletion cascade for the Project to a worker. The message carries only the
    Project: who asked, and when, are on its row."""
    await asyncio.to_thread(delete_project.apply, args=(project_id,))


async def test_the_cascade_leaves_a_project_whose_deletion_was_never_asked_for(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project = await archived_project(owner)
    await upload_into_archived(app, owner, project["id"])

    await run_cascade(project["id"])

    (kept,) = await listed(owner, archived="true")
    assert (kept["id"], kept["deleting"]) == (project["id"], False)
    assert [d["name"] for d in await documents(owner, project["id"])] == ["leave.md"]
    assert len(stored_keys(app)) == 2
    assert await audit_events(owner, "project.deleted") == []


async def upload_into_archived(app: FastAPI, owner: SignedUpMember, project_id: str) -> None:
    """Restores the Project, uploads a Document, and archives it again."""
    await restore(owner, project_id)
    await upload(app, owner, project_id, "leave.md", b"# Leave\n\n25 days.")
    await archive(owner, project_id)


async def test_running_the_cascade_again_does_nothing(owner: SignedUpMember) -> None:
    project = await archived_project(owner)
    await delete_permanently(owner, project["id"], "HR handbook")

    await run_cascade(project["id"])

    assert len(await audit_events(owner, "project.deleted")) == 1


async def test_a_cascade_sent_with_who_asked_and_when_is_still_run(
    owner: SignedUpMember, jobs: RecordingJobPublisher, clock: ControllableClock
) -> None:
    """A message sent before the row became the record carries who asked and when; the worker
    ignores both and reads them from the row."""
    project = await archived_project(owner)
    jobs.lose_next()
    await delete_permanently(owner, project["id"], "HR handbook")

    await asyncio.to_thread(
        delete_project.apply, args=(project["id"], owner.member_id, clock.now().isoformat())
    )

    assert await listed(owner, archived="true") == []
    assert len(await audit_events(owner, "project.deleted")) == 1


# Deleting is visible, and always finishes (spec 21, ADR-0020): the request marks the Project
# Deleting, and the sweeper finishes a deletion whose job was lost or whose worker died.

PROJECT_DELETING = "This Project is being deleted. A deleted Project can't be restored."


async def deleting_project(
    app: FastAPI, owner: SignedUpMember, jobs: RecordingJobPublisher
) -> dict[str, Any]:
    """An archived Project holding a Document, whose deletion was asked for and whose job was
    lost: it stays Deleting until a sweep."""
    project = await archived_project(owner)
    await upload_into_archived(app, owner, project["id"])
    jobs.lose_next()
    response = await delete_permanently(owner, project["id"], "HR handbook")
    assert (response.status_code, response.content) == (202, b"")
    return project


async def test_a_project_shows_as_deleting_at_once_and_is_gone_after_a_lost_job_is_swept(
    app: FastAPI,
    owner: SignedUpMember,
    jobs: RecordingJobPublisher,
    clock: ControllableClock,
    member_factory: MemberFactory,
) -> None:
    await settle_jobs_in_flight(app)
    editor = await member_factory(owner, "editor")
    kept = await create_project(owner, "Kept")

    project = await deleting_project(app, owner, jobs)

    # Deleting at once: in the archived list with its state, and out of the main list.
    (shown,) = await listed(owner, archived="true")
    assert (shown["id"], shown["deleting"]) == (project["id"], True)
    assert [p["id"] for p in await listed(editor)] == [kept["id"]]
    assert kept["deleting"] is False
    opened = await editor.client.get(projects_path(owner.organisation_id, project["id"]))
    assert opened.json()["deleting"] is True
    # The sweeper finishes it: rows, stored files, and one Audit Event for the Owner who asked.
    requested_at = clock.now()
    clock.advance(timedelta(minutes=1))
    await sweep(clock)
    assert await listed(owner, archived="true") == []
    assert await project_rows(app, project["id"]) == dict.fromkeys(PROJECT_ROWS, 0)
    assert not any(project["id"] in key for key in stored_keys(app))
    (deleted,) = await audit_events(owner, "project.deleted")
    assert deleted["actor"]["id"] == owner.member_id
    assert datetime.fromisoformat(deleted["occurred_at"]) == requested_at


async def test_a_deleting_project_refuses_restoring_and_changes_with_the_reason(
    app: FastAPI, owner: SignedUpMember, jobs: RecordingJobPublisher
) -> None:
    project = await deleting_project(app, owner, jobs)
    path = projects_path(owner.organisation_id, project["id"])

    restored = await restore(owner, project["id"])
    renamed = await owner.client.patch(path, json={"name": "New"})
    uploaded = await start_upload(owner, project["id"], "more.md", 5)
    tagged = await owner.client.post(f"{path}/tags", json={"name": "HR"})

    for refused in (restored, renamed, uploaded, tagged):
        assert (refused.status_code, refused.json()) == (409, {"detail": PROJECT_DELETING})
    # An archived Project that isn't being deleted still gives the archived reason.
    other = await archived_project(owner, "Other")
    renamed_other = await owner.client.patch(
        projects_path(owner.organisation_id, other["id"]), json={"name": "New"}
    )
    assert renamed_other.json() == {"detail": "This Project is archived. An Owner can restore it."}


async def test_asking_again_while_deleting_is_accepted_and_keeps_who_asked_first(
    app: FastAPI,
    owner: SignedUpMember,
    jobs: RecordingJobPublisher,
    clock: ControllableClock,
    member_factory: MemberFactory,
) -> None:
    await settle_jobs_in_flight(app)
    second_owner = await member_factory(owner, "owner")
    project = await deleting_project(app, owner, jobs)
    requested_at = clock.now()
    clock.advance(timedelta(minutes=3))
    jobs.lose_next()

    again = await delete_permanently(second_owner, project["id"], "HR handbook")

    assert (again.status_code, again.content) == (202, b"")
    await sweep(clock)
    (deleted,) = await audit_events(owner, "project.deleted")
    assert deleted["actor"]["id"] == owner.member_id
    assert datetime.fromisoformat(deleted["occurred_at"]) == requested_at


async def test_a_worker_killed_after_the_rows_go_leaves_the_files_to_the_next_sweep(
    app: FastAPI, owner: SignedUpMember, jobs: RecordingJobPublisher, clock: ControllableClock
) -> None:
    await settle_jobs_in_flight(app)
    project = await archived_project(owner)
    await upload_into_archived(app, owner, project["id"])
    store = app.state.ingestion.object_store
    store.kill.arm("delete")

    await delete_permanently(owner, project["id"], "HR handbook")

    assert [job.task for job in jobs.killed] == [DELETE_PROJECT_TASK]
    assert await listed(owner, archived="true") == []
    assert len([key for key in stored_keys(app) if project["id"] in key]) == 2
    await sweep(clock)
    assert not any(project["id"] in key for key in stored_keys(app))


async def test_files_whose_first_delete_failed_are_deleted_by_the_next_sweep(
    app: FastAPI, owner: SignedUpMember, jobs: RecordingJobPublisher, clock: ControllableClock
) -> None:
    await settle_jobs_in_flight(app)
    project = await archived_project(owner)
    await upload_into_archived(app, owner, project["id"])
    store = app.state.ingestion.object_store
    store.failure = OSError("storage unavailable")

    await delete_permanently(owner, project["id"], "HR handbook")

    assert await listed(owner, archived="true") == []
    assert len(stored_keys(app)) == 2
    store.failure = None
    await sweep(clock)
    assert stored_keys(app) == []


async def test_a_second_copy_skips_the_project_the_first_is_deleting(
    app: FastAPI, owner: SignedUpMember, jobs: RecordingJobPublisher, clock: ControllableClock
) -> None:
    """While one copy of the cascade holds the Project (here, a transaction that holds its row
    lock), another copy and the sweeper pass it by; it is deleted once, by whichever comes next."""
    await settle_jobs_in_flight(app)
    project = await deleting_project(app, owner, jobs)
    async with app.state.sessionmaker() as first, first.begin():
        await first.execute(
            text("SELECT 1 FROM projects WHERE id = :id FOR UPDATE"), {"id": project["id"]}
        )

        await run_cascade(project["id"])
        await sweep(clock)

        assert len(await listed(owner, archived="true")) == 1
    await run_cascade(project["id"])
    await sweep(clock)
    assert await listed(owner, archived="true") == []
    assert len(await audit_events(owner, "project.deleted")) == 1


async def test_another_organisations_project_cannot_be_deleted(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    project = await archived_project(owner)
    stranger = await tenant_factory()

    response = await delete_permanently(stranger, project["id"], "HR handbook")
    across = await stranger.client.request(
        "DELETE",
        projects_path(owner.organisation_id, project["id"]),
        json={"confirm_name": "HR handbook"},
    )

    assert (response.status_code, response.json()) == (404, {"detail": "Not found"})
    assert across.status_code in (403, 404)
    (shown,) = await listed(owner, archived="true")
    assert shown["deleting"] is False
