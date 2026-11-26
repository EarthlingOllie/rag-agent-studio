"""API seam plus task seam for ingestion that is cut short (spec 21, ADR-0020): a worker killed
mid-ingestion, a job that never reached the queue, a job delivered twice or run as two copies at
once, and Documents stuck before the sweeper shipped.

A kill comes from arming an adapter fake's kill switch (converter, embedder, object store), which
stops the job without running its error handling. A lost or held message comes from the Job
publisher fake. The sweeper is called directly as a task, as Beat would call it, with the
controllable clock moved past each threshold. Outcomes are read through the API, as an Editor
would see them, and the traces."""

import asyncio
import threading
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import pytest
from asgi_lifespan import LifespanManager
from docling_core.types.doc.document import DoclingDocument
from fastapi import FastAPI
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import update

from app.core.settings import load_settings
from app.documents.converter import FakeConverter
from app.documents.models import Document, DocumentStatus, StagedEdition
from app.documents.tasks import ingest_document
from app.evaluation.models import LiveStatus, LiveVerdict
from app.jobs.reliability import Timings
from app.jobs.tasks import sweep_jobs
from app.main import create_app
from tests.conftest import SignedUpMember
from tests.documents import (
    chunks,
    confirm,
    create_project,
    documents,
    put_to_memory_store,
    replace,
    start_upload,
    upload,
)
from tests.fakes.clock import ControllableClock
from tests.fakes.jobs import RecordingJobPublisher

HANDBOOK = b"# Handbook\n\nEveryone gets 25 days of annual leave a year."
HANDBOOK_2027 = b"# Handbook 2027\n\nEveryone gets 28 days of annual leave a year."
INGEST = "documents.ingest"


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
async def app(
    settings_env: pytest.MonkeyPatch, database_schema: None, exporter: InMemorySpanExporter
) -> AsyncIterator[FastAPI]:
    """The app, with its spans also captured in memory, so tests can read the traces."""
    application = create_app(extra_span_processors=[SimpleSpanProcessor(exporter)])
    async with LifespanManager(application):
        yield application


@pytest.fixture(autouse=True)
async def no_jobs_left_by_earlier_tests(app: FastAPI) -> None:
    """The test database is shared by the tests a worker runs, one after another, so earlier
    tests may have left Documents or replacements Queued or Processing (a lost job, a kill).
    The sweeper would recover those too, so each test here starts with them settled as Failed:
    every sweep then sees only the test's own rows."""
    await settle_jobs_in_flight(app)


async def settle_jobs_in_flight(app: FastAPI) -> None:
    """Settles every job row earlier tests left in flight: Documents and replacements Queued or
    Processing as Failed, Live Verdicts Pending as Errors."""
    in_flight = (DocumentStatus.QUEUED, DocumentStatus.PROCESSING)
    async with app.state.sessionmaker() as session, session.begin():
        for model in (Document, StagedEdition):
            await session.execute(
                update(model)
                .where(model.status.in_(in_flight))
                .values(status=DocumentStatus.FAILED, claim_id=None, heartbeat_at=None)
            )
        await session.execute(
            update(LiveVerdict)
            .where(LiveVerdict.status == LiveStatus.PENDING)
            .values(status=LiveStatus.ERROR)
        )


async def sweep(clock: ControllableClock) -> int | None:
    """Runs the sweeper task as Beat would, as of the controllable clock's time (in a thread: the
    task runs its own event loop, and jobs it sends run eagerly in it)."""
    result = await asyncio.to_thread(sweep_jobs.apply, kwargs={"at": clock.now().isoformat()})
    # (Another job may be running eagerly in another thread, which Celery takes for a task.)
    swept: int | None = result.get(disable_sync_subtasks=False)
    return swept


async def deliver_again(document_id: str) -> None:
    """A second delivery of the Document's ingestion job, straight to the worker."""
    await asyncio.to_thread(ingest_document.apply, args=(document_id,))


async def only_document(owner: SignedUpMember, project_id: str) -> dict[str, Any]:
    (listed,) = await documents(owner, project_id)
    return listed


async def status_of(owner: SignedUpMember, project_id: str) -> str:
    status: str = (await only_document(owner, project_id))["status"]
    return status


def recovered(exporter: InMemorySpanExporter) -> list[tuple[Any, ...]]:
    """The recoveries the sweeper recorded in the traces: job, identifier and reason."""
    template = "Sweeper recovered {job} {job_id}: {reason}"
    return [
        (attributes["job"], attributes["job_id"], attributes["reason"])
        for span in exporter.get_finished_spans()
        if (attributes := span.attributes or {}).get("logfire.msg_template") == template
    ]


class HeldConverter(FakeConverter):
    """The fake converter, holding its first conversion until the test releases it (so a job can
    stay Processing while the test acts), then converting or raising ``failure_on_release``.
    Later conversions run at once."""

    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()
        self.failure_on_release: Exception | None = None
        self.calls = 0

    def convert(self, data: bytes, filename: str, *, ocr: bool) -> DoclingDocument:
        self.calls += 1
        if self.calls == 1:
            self.started.set()
            assert self.release.wait(timeout=10)
            if self.failure_on_release is not None:
                raise self.failure_on_release
        return super().convert(data, filename, ocr=ocr)

    async def wait_until_started(self) -> None:
        assert await asyncio.to_thread(self.started.wait, 10)


def held_converter(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> HeldConverter:
    converter = HeldConverter()
    monkeypatch.setattr(app.state.ingestion, "converter", converter)
    return converter


async def upload_in_background(
    app: FastAPI, owner: SignedUpMember, project_id: str, data: bytes = HANDBOOK
) -> "asyncio.Task[dict[str, Any]]":
    return asyncio.create_task(upload(app, owner, project_id, "handbook.md", data))


# --- A worker killed mid-ingestion ----------------------------------------------------------


@pytest.mark.parametrize(
    ("adapter", "point"),
    [
        ("converter", "convert"),
        ("object_store", "put"),
        ("embedder", "embed"),
    ],
)
async def test_a_document_whose_worker_died_goes_back_to_queued_and_becomes_ready(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    exporter: InMemorySpanExporter,
    adapter: str,
    point: str,
) -> None:
    ports = app.state.ingestion
    fakes = {"embedder": next(iter(ports.embedders.values()))}
    fake = fakes[adapter] if adapter in fakes else getattr(ports, adapter)
    project_id = await create_project(owner)
    ticket = (await start_upload(owner, project_id, "handbook.md", len(HANDBOOK))).json()
    await put_to_memory_store(app, ticket["url"], HANDBOOK, ticket["content_type"])
    fake.kill.arm(point)

    confirmed = await confirm(owner, project_id, ticket["upload_id"])
    document = confirmed.json()

    assert len(jobs.killed) == 1
    assert await status_of(owner, project_id) == "processing"
    # Still within the dead-after time: the sweeper leaves it alone.
    clock.advance(timedelta(minutes=4, seconds=59))
    assert await sweep(clock) == 0
    assert await status_of(owner, project_id) == "processing"

    clock.advance(timedelta(seconds=2))
    jobs.hold_next()
    assert await sweep(clock) == 1

    assert await status_of(owner, project_id) == "queued"
    await jobs.release_held()
    assert await status_of(owner, project_id) == "ready"
    assert [c["text"] for c in await chunks(owner, project_id, document["id"])] == [
        "Everyone gets 25 days of annual leave a year."
    ]
    assert recovered(exporter) == [(INGEST, document["id"], "no heartbeat")]


async def test_a_replaced_document_whose_new_edition_was_interrupted_is_ingested_again(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "handbook-2026.md", HANDBOOK)
    app.state.ingestion.converter.kill.arm("convert")

    replaced = await replace(
        app, owner, project_id, document["id"], "handbook-2027.md", HANDBOOK_2027
    )

    assert replaced.status_code == 202, replaced.text
    interrupted = await only_document(owner, project_id)
    assert (interrupted["status"], interrupted["replacement"]["status"]) == ("ready", "processing")
    # The current edition keeps answering meanwhile.
    assert [c["text"] for c in await chunks(owner, project_id, document["id"])] == [
        "Everyone gets 25 days of annual leave a year."
    ]

    clock.advance(timedelta(minutes=6))
    assert await sweep(clock) == 1

    restarted = await only_document(owner, project_id)
    assert (restarted["status"], restarted["edition"], restarted["replacement"]) == (
        "ready",
        2,
        None,
    )
    assert [c["text"] for c in await chunks(owner, project_id, document["id"])] == [
        "Everyone gets 28 days of annual leave a year."
    ]


# --- A job that never reached the queue -----------------------------------------------------


async def test_a_document_that_never_reached_the_queue_is_sent_again_after_fifteen_minutes(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    exporter: InMemorySpanExporter,
) -> None:
    project_id = await create_project(owner)
    jobs.lose_next()

    document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    assert await status_of(owner, project_id) == "queued"
    clock.advance(timedelta(minutes=14))
    assert await sweep(clock) == 0
    assert jobs.tasks() == [INGEST]

    clock.advance(timedelta(minutes=1, seconds=1))
    assert await sweep(clock) == 1

    assert jobs.tasks() == [INGEST, INGEST]
    assert await status_of(owner, project_id) == "ready"
    assert recovered(exporter) == [(INGEST, document["id"], "queued too long")]


async def test_a_resent_job_lost_again_is_sent_again_fifteen_minutes_later(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    jobs.lose_next()
    await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    clock.advance(timedelta(minutes=16))
    jobs.lose_next()
    assert await sweep(clock) == 1

    clock.advance(timedelta(minutes=14))
    assert await sweep(clock) == 0
    clock.advance(timedelta(minutes=2))
    assert await sweep(clock) == 1

    assert jobs.tasks() == [INGEST, INGEST, INGEST]
    assert await status_of(owner, project_id) == "ready"


async def test_a_replacement_that_never_reached_the_queue_is_sent_again(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "handbook-2026.md", HANDBOOK)
    jobs.lose_next()
    await replace(app, owner, project_id, document["id"], "handbook-2027.md", HANDBOOK_2027)
    assert (await only_document(owner, project_id))["replacement"]["status"] == "queued"

    clock.advance(timedelta(minutes=16))
    assert await sweep(clock) == 1

    restarted = await only_document(owner, project_id)
    assert (restarted["edition"], restarted["replacement"]) == (2, None)


# --- Twice-safety ---------------------------------------------------------------------------


async def test_a_job_delivered_again_after_it_finished_does_nothing(
    app: FastAPI, owner: SignedUpMember, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    before = await chunks(owner, project_id, document["id"])

    await deliver_again(document["id"])

    assert await status_of(owner, project_id) == "ready"
    assert await chunks(owner, project_id, document["id"]) == before


async def test_a_second_copy_of_a_running_job_exits_without_doing_anything(
    app: FastAPI,
    owner: SignedUpMember,
    jobs: RecordingJobPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    converter = held_converter(app, monkeypatch)
    project_id = await create_project(owner)
    first = await upload_in_background(app, owner, project_id)
    await converter.wait_until_started()
    (listed,) = await documents(owner, project_id)

    await deliver_again(listed["id"])

    assert converter.calls == 1
    converter.release.set()
    document = await first
    assert await status_of(owner, project_id) == "ready"
    assert len(await chunks(owner, project_id, document["id"])) == 1


async def test_an_older_copy_still_running_after_a_restart_cannot_write_the_document(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first copy stalls (its heartbeat seems to stop), is given up for dead and restarted;
    when it wakes up, its final write is refused."""
    monkeypatch.setenv("JOB_HEARTBEAT_SECONDS", "3600")
    converter = held_converter(app, monkeypatch)
    project_id = await create_project(owner)
    first = await upload_in_background(app, owner, project_id)
    await converter.wait_until_started()
    clock.advance(timedelta(minutes=6))
    assert await sweep(clock) == 1
    (restarted,) = await documents(owner, project_id)
    assert restarted["status"] == "ready"
    written = await chunks(owner, project_id, restarted["id"])

    converter.release.set()
    await first

    assert await status_of(owner, project_id) == "ready"
    assert await chunks(owner, project_id, restarted["id"]) == written


async def test_an_older_copy_that_fails_after_a_restart_cannot_mark_the_document_failed(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JOB_HEARTBEAT_SECONDS", "3600")
    converter = held_converter(app, monkeypatch)
    converter.failure_on_release = RuntimeError("Docling crashed")
    project_id = await create_project(owner)
    first = await upload_in_background(app, owner, project_id)
    await converter.wait_until_started()
    clock.advance(timedelta(minutes=6))
    assert await sweep(clock) == 1

    converter.release.set()
    await first

    document = await only_document(owner, project_id)
    assert (document["status"], document["error_category"]) == ("ready", None)
    assert len(await chunks(owner, project_id, document["id"])) == 1


async def test_a_live_job_keeps_writing_heartbeats_so_the_sweeper_leaves_it_alone(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """However long conversion takes, a job whose worker is alive is never restarted."""
    monkeypatch.setenv("JOB_HEARTBEAT_SECONDS", "0.05")
    converter = held_converter(app, monkeypatch)
    project_id = await create_project(owner)
    first = await upload_in_background(app, owner, project_id)
    await converter.wait_until_started()

    clock.advance(timedelta(minutes=10))
    # A few heartbeats go by (in real time) after the clock moved.
    await asyncio.sleep(0.5)
    swept = await sweep(clock)

    assert swept == 0
    assert await status_of(owner, project_id) == "processing"
    converter.release.set()
    await first
    assert await status_of(owner, project_id) == "ready"
    assert converter.calls == 1


# --- The sweeper ----------------------------------------------------------------------------


async def test_two_sweeps_never_overlap(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = await create_project(owner)
    jobs.lose_next()
    await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    converter = held_converter(app, monkeypatch)
    clock.advance(timedelta(minutes=16))
    # The first sweep sends the job again, which runs (eagerly) inside it and is held there.
    first = asyncio.create_task(sweep(clock))
    await converter.wait_until_started()

    overlapping = await sweep(clock)

    assert overlapping is None
    converter.release.set()
    assert await first == 1
    assert jobs.tasks() == [INGEST, INGEST]
    assert await status_of(owner, project_id) == "ready"


async def test_documents_stuck_before_the_sweeper_shipped_are_recovered_by_the_first_sweep(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    """Rows left Processing or Queued by the code before this, as the migration leaves them: no
    claim, and their last update (an hour ago) taken as their heartbeat or queued time."""
    project_id = await create_project(owner)
    jobs.lose_next()
    processing = await upload(app, owner, project_id, "processing.md", HANDBOOK)
    jobs.lose_next()
    queued = await upload(app, owner, project_id, "queued.md", HANDBOOK_2027)
    an_hour_ago = clock.now() - timedelta(hours=1)
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(
            update(Document)
            .where(Document.id == processing["id"])
            .values(status=DocumentStatus.PROCESSING, queued_at=None, heartbeat_at=an_hour_ago)
        )
        await session.execute(
            update(Document).where(Document.id == queued["id"]).values(queued_at=an_hour_ago)
        )

    assert await sweep(clock) == 2

    assert {d["name"]: d["status"] for d in await documents(owner, project_id)} == {
        "processing.md": "ready",
        "queued.md": "ready",
    }


def test_the_thresholds_are_settings_with_their_defaults(
    settings_env: pytest.MonkeyPatch,
) -> None:
    assert Timings.from_settings(load_settings()) == Timings(
        heartbeat_seconds=30.0,
        dead_after=timedelta(minutes=5),
        queued_too_long=timedelta(minutes=15),
    )
    settings_env.setenv("JOB_HEARTBEAT_SECONDS", "10")
    settings_env.setenv("JOB_DEAD_AFTER_SECONDS", "120")
    settings_env.setenv("JOB_QUEUED_TOO_LONG_SECONDS", "600")

    assert Timings.from_settings(load_settings()) == Timings(
        heartbeat_seconds=10.0,
        dead_after=timedelta(minutes=2),
        queued_too_long=timedelta(minutes=10),
    )
