"""API seam plus task seam: a deleted Document's files, and a replaced edition's, are removed from
storage even when the object-deletion job is lost, fails or dies (spec 21, ADR-0020), and the work
that follows a new edition is finished by the sweeper if the worker died before doing it.

The keys to delete are written to the deletions table in the transaction that removes the last
reference to them; the object-deletion job, and every sweep, delete what the table holds. A lost
message comes from the Job publisher fake, a dead worker from an adapter fake's kill switch or
from the publisher fake killing the job that sends. Stored files have no API surface, so they are
read from the in-memory object store."""

import asyncio
import threading
from datetime import timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.documents.tasks import delete_stored_objects
from app.jobs import deletions
from app.jobs.models import ObjectDeletion
from app.storage.memory import InMemoryObjectStore
from app.worker.celery_app import DELETE_OBJECTS_TASK, INGEST_TASK
from tests.conftest import SignedUpMember
from tests.documents import create_project, project_path, replace, upload
from tests.fakes.clock import ControllableClock
from tests.fakes.jobs import RecordingJobPublisher
from tests.integration.test_evaluation_expectations import add_case, leave_document, source
from tests.integration.test_expected_source_warning import expected_sources
from tests.integration.test_interrupted_ingestion import sweep
from tests.integration.test_playground import ready_agent

HANDBOOK = b"# Handbook\n\nEveryone gets 25 days of annual leave."
HANDBOOK_2027 = b"# Handbook 2027\n\nEveryone gets 28 days of annual leave."
FAQ = b"# FAQ\n\nAsk HR."


def store(app: FastAPI) -> InMemoryObjectStore:
    found = app.state.ingestion.object_store
    assert isinstance(found, InMemoryObjectStore)
    return found


def stored(app: FastAPI) -> list[bytes]:
    """The stored files' contents, sorted: originals and converted markdown."""
    return sorted(data for data, _ in store(app).objects.values())


async def entries(app: FastAPI) -> int:
    """How many entries the deletions table holds: it has no API surface."""
    async with app.state.sessionmaker() as session:
        count: int = await session.scalar(select(func.count()).select_from(ObjectDeletion))
    return count


async def deliver_deletion_job() -> None:
    """A delivery of the object-deletion job, straight to the worker."""
    await asyncio.to_thread(delete_stored_objects.apply)


async def delete(owner: SignedUpMember, project_id: str, document_id: str) -> None:
    deleted = await owner.client.delete(
        f"{project_path(owner, project_id)}/documents/{document_id}"
    )
    assert deleted.status_code == 204, deleted.text


async def test_a_deleted_documents_files_are_removed_by_the_sweeper_when_the_job_is_lost(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "faq.md", FAQ)
    document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    jobs.lose_next()

    await delete(owner, project_id, document["id"])

    assert len(stored(app)) == 4
    await sweep(clock)
    assert stored(app) == [b"# FAQ\n\nAsk HR.", b"## FAQ\n\nAsk HR."]


async def test_a_worker_killed_before_deleting_from_storage_leaves_nothing_after_the_next_sweep(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    store(app).kill.arm("delete")

    await delete(owner, project_id, document["id"])

    assert [job.task for job in jobs.killed] == [DELETE_OBJECTS_TASK]
    assert stored(app) != []
    await sweep(clock)
    assert stored(app) == []


async def test_files_whose_first_delete_failed_are_deleted_by_the_next_sweep(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    store(app).failure = OSError("storage unavailable")

    await delete(owner, project_id, document["id"])

    assert len(stored(app)) == 2
    store(app).failure = None
    await sweep(clock)
    assert stored(app) == []


async def test_the_work_after_a_new_edition_is_finished_by_the_sweeper_if_the_worker_died(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    """The worker dies right after the new edition is swapped in, as it sends the deletion of the
    old edition's files: those files, and the Expected sources, are left for the sweeper."""
    _, project_id, agent_id = await ready_agent(app, owner)
    leave = await leave_document(owner, project_id)
    await add_case(
        owner,
        project_id,
        agent_id,
        expected_sources=[source(leave["id"], "25 days"), source(leave["id"], "30 days")],
    )
    before = stored(app)
    jobs.kill_when_sending(DELETE_OBJECTS_TASK)

    replaced = await replace(
        app, owner, project_id, leave["id"], "leave-2027.txt", b"Everyone gets 30 days a year."
    )

    assert replaced.status_code == 202, replaced.text
    assert [job.task for job in jobs.killed] == [INGEST_TASK]
    assert [stale for *_, stale, _ in await expected_sources(owner, project_id, agent_id)] == [
        False,
        True,
    ]
    assert set(before) <= set(stored(app))

    await sweep(clock)

    assert await expected_sources(owner, project_id, agent_id) == [
        (leave["id"], "leave.txt", "25 days", True, "passage_missing"),
        (leave["id"], "leave.txt", "30 days", False, None),
    ]
    assert not set(before) & set(stored(app))
    assert b"Everyone gets 30 days a year." in stored(app)


async def test_a_discarded_failed_replacements_files_are_removed_by_the_sweeper(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")
    await replace(app, owner, project_id, document["id"], "broken.md", b"# Broken")
    app.state.ingestion.converter.failure = None
    # The second replacement discards the failed one. Its deletion job is lost, and so is its
    # ingestion (which would otherwise send the deletion job again once it is Ready).
    jobs.lose_next()
    jobs.lose_next()

    replaced = await replace(app, owner, project_id, document["id"], "fixed.md", HANDBOOK_2027)

    assert replaced.status_code == 202, replaced.text
    assert b"# Broken" in stored(app)
    clock.advance(timedelta(minutes=16))
    await sweep(clock)
    assert stored(app) == [
        b"# Handbook 2027\n\nEveryone gets 28 days of annual leave.",
        b"## Handbook 2027\n\nEveryone gets 28 days of annual leave.",
    ]


async def test_an_entry_whose_files_are_already_gone_is_removed_without_error(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    jobs.lose_next()
    await delete(owner, project_id, document["id"])
    store(app).objects.clear()

    await sweep(clock)

    assert await entries(app) == 0


async def test_the_deletion_job_delivered_again_after_it_finished_does_nothing(
    app: FastAPI, owner: SignedUpMember, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "faq.md", FAQ)
    document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    await delete(owner, project_id, document["id"])

    await deliver_deletion_job()

    assert stored(app) == [b"# FAQ\n\nAsk HR.", b"## FAQ\n\nAsk HR."]
    assert await entries(app) == 0


class HeldStore(InMemoryObjectStore):
    """The in-memory store, holding its first delete until the test releases it."""

    def __init__(self, objects: dict[str, tuple[bytes, str]]) -> None:
        super().__init__()
        self.objects = objects
        self.started = threading.Event()
        self.release = threading.Event()
        self.deletes = 0

    async def delete(self, key: str) -> None:
        self.deletes += 1
        if self.deletes == 1:
            self.started.set()
            assert await asyncio.to_thread(self.release.wait, 10)
        await super().delete(key)


async def test_a_second_drain_skips_the_entry_the_first_is_deleting(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    held = HeldStore(store(app).objects)
    monkeypatch.setattr(app.state.ingestion, "object_store", held)
    deleting = asyncio.create_task(delete(owner, project_id, document["id"]))
    assert await asyncio.to_thread(held.started.wait, 10)

    await sweep(clock)

    # The sweep deleted the other entry and left the held one to the job holding it.
    assert held.deletes == 2
    held.release.set()
    await deleting
    assert held.deletes == 2
    assert stored(app) == []
    assert await entries(app) == 0


async def test_an_entry_can_be_a_prefix_whose_every_object_is_deleted(
    app: FastAPI, clock: ControllableClock
) -> None:
    objects = store(app)
    for key in ("organisations/a/one", "organisations/a/two", "organisations/b/three"):
        await objects.put(key, key.encode(), content_type="text/plain")
    async with app.state.sessionmaker() as session, session.begin():
        deletions.schedule(session, ["organisations/a/"], prefix=True)
    # The first attempt fails; the entry is kept for the next sweep.
    objects.failure = OSError("storage unavailable")
    await sweep(clock)
    assert len(objects.objects) == 3
    objects.failure = None

    await sweep(clock)

    assert sorted(objects.objects) == ["organisations/b/three"]
    assert await entries(app) == 0
