"""API seam plus task seam for ingestion's limits (spec 21, ticket 21-04): a Document interrupted
three times is Failed with the Failure category ``interrupted``, conversion that runs too long is
stopped, and an automatic retry happens even when the broker lost its message.

As in ``test_interrupted_ingestion``: a kill comes from an adapter fake's kill switch, a lost
message from the Job publisher fake, and the sweeper is called directly as a task with the
controllable clock moved past each threshold. Outcomes are read through the API."""

import dataclasses
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core.settings import load_settings
from app.documents.converter import INTERRUPT_MARKER
from app.embeddings.port import EmbeddingProviderError
from app.main import create_app
from app.worker.celery_app import INGEST_TASK
from app.worker.publisher import Job
from tests.conftest import SignedUpMember
from tests.documents import chunks, create_project, project_path, replace, upload
from tests.fakes.clock import ControllableClock
from tests.fakes.jobs import RecordingJobPublisher
from tests.integration.test_interrupted_ingestion import (
    HeldConverter,
    held_converter,
    only_document,
    recovered,
    settle_jobs_in_flight,
    sweep,
)

HANDBOOK = b"# Handbook\n\nEveryone gets 25 days of annual leave a year."
HANDBOOK_2027 = b"# Handbook 2027\n\nEveryone gets 28 days of annual leave a year."
LOCAL_MODEL = "multilingual-e5-small"
INTERRUPTED = "Processing was interrupted 3 times. Retry it, or upload it again."
CONVERSION_FAILED = "This file couldn't be converted. Retry it, or upload a fixed copy."
DEAD = timedelta(minutes=5, seconds=1)


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
    """Each sweep sees only the test's own rows (see ``test_interrupted_ingestion``)."""
    await settle_jobs_in_flight(app)


async def retry(member: SignedUpMember, project_id: str, document_id: str) -> httpx.Response:
    return await member.client.post(
        f"{project_path(member, project_id)}/documents/{document_id}/retry"
    )


def failure_of(document: dict[str, Any]) -> tuple[str, str | None, str | None]:
    return document["status"], document["error_category"], document["error_message"]


async def interrupt(app: FastAPI, clock: ControllableClock) -> None:
    """The job now running dies at its next conversion; once it has been dead long enough, the
    sweeper puts it back and sends it again, and the sent job is killed at conversion too."""
    app.state.ingestion.converter.kill.arm("convert")
    clock.advance(DEAD)
    assert await sweep(clock) == 1


# --- The interruption cap -----------------------------------------------------------------------


async def test_the_third_interruption_fails_the_document_as_interrupted(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    app.state.ingestion.converter.kill.arm("convert")
    await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    # The first and second interruptions restart it (the restarted job is killed again).
    for _ in range(2):
        await interrupt(app, clock)
        assert (await only_document(owner, project_id))["status"] == "processing"

    clock.advance(DEAD)
    assert await sweep(clock) == 1

    document = await only_document(owner, project_id)
    assert failure_of(document) == ("failed", "interrupted", INTERRUPTED)
    assert len(jobs.killed) == 3


async def test_a_manual_retry_gives_an_interrupted_document_three_fresh_attempts(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    converter = app.state.ingestion.converter
    converter.kill.arm("convert")
    document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    for _ in range(2):
        await interrupt(app, clock)
    clock.advance(DEAD)
    assert await sweep(clock) == 1
    assert (await only_document(owner, project_id))["error_category"] == "interrupted"

    converter.kill.arm("convert")
    response = await retry(owner, project_id, document["id"])
    assert response.status_code == 202, response.text
    # Interrupted twice more: still short of the cap, so it restarts and becomes Ready.
    await interrupt(app, clock)
    clock.advance(DEAD)
    assert await sweep(clock) == 1

    retried = await only_document(owner, project_id)
    assert failure_of(retried) == ("ready", None, None)
    # The provider-retry count started again too: one attempt ran to the end.
    assert retried["attempt_count"] == 1


async def test_interruptions_are_counted_apart_from_provider_retries(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    embedder = app.state.ingestion.embedders[LOCAL_MODEL]
    app.state.ingestion.converter.kill.arm("convert")
    await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    await interrupt(app, clock)
    # The restart's provider fails three times; each is an automatic retry, not an interruption.
    embedder.failures = [EmbeddingProviderError("timeout")] * 3
    clock.advance(DEAD)
    assert await sweep(clock) == 1

    document = await only_document(owner, project_id)
    assert failure_of(document) == ("ready", None, None)
    # Four provider attempts (three failed), however many interruptions came before.
    assert document["attempt_count"] == 4


async def test_a_new_edition_interrupted_three_times_fails_while_the_current_one_keeps_answering(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "handbook-2026.md", HANDBOOK)
    app.state.ingestion.converter.kill.arm("convert")
    await replace(app, owner, project_id, document["id"], "handbook-2027.md", HANDBOOK_2027)
    for _ in range(2):
        await interrupt(app, clock)

    clock.advance(DEAD)
    assert await sweep(clock) == 1

    listed = await only_document(owner, project_id)
    assert (listed["status"], listed["edition"]) == ("ready", 1)
    assert listed["replacement"] == {
        "edition": 2,
        "name": "handbook-2027.md",
        "status": "failed",
        "error_message": INTERRUPTED,
        "error_category": "interrupted",
    }
    assert [c["text"] for c in await chunks(owner, project_id, document["id"])] == [
        "Everyone gets 25 days of annual leave a year."
    ]


async def test_a_ready_document_processed_again_and_interrupted_three_times_loses_its_chunks(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    app.state.ingestion.converter.kill.arm("convert")
    assert (await retry(owner, project_id, document["id"])).status_code == 202
    for _ in range(2):
        await interrupt(app, clock)

    clock.advance(DEAD)
    assert await sweep(clock) == 1

    listed = await only_document(owner, project_id)
    assert failure_of(listed) == ("failed", "interrupted", INTERRUPTED)
    assert listed["chunk_count"] == 0


async def test_the_interruption_cap_is_a_setting(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert load_settings().ingestion_max_interruptions == 3
    monkeypatch.setenv("INGESTION_MAX_INTERRUPTIONS", "1")
    project_id = await create_project(owner)
    app.state.ingestion.converter.kill.arm("convert")
    await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    clock.advance(DEAD)
    assert await sweep(clock) == 1

    assert failure_of(await only_document(owner, project_id)) == (
        "failed",
        "interrupted",
        "Processing was interrupted 1 time. Retry it, or upload it again.",
    )


# --- The conversion limit -----------------------------------------------------------------------


async def test_conversion_that_runs_past_its_limit_is_stopped_and_fails_as_a_conversion_error(
    app: FastAPI,
    owner: SignedUpMember,
    jobs: RecordingJobPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert load_settings().ingestion_conversion_timeout_seconds == 30 * 60
    monkeypatch.setenv("INGESTION_CONVERSION_TIMEOUT_SECONDS", "0.3")
    converter: HeldConverter = held_converter(app, monkeypatch)
    project_id = await create_project(owner)

    try:
        await upload(app, owner, project_id, "huge-scan.md", HANDBOOK)
        document = await only_document(owner, project_id)
    finally:
        converter.release.set()

    assert failure_of(document) == ("failed", "conversion", CONVERSION_FAILED)
    assert document["chunk_count"] == 0


# --- Automatic retries survive a lost message -------------------------------------------------


async def test_an_automatic_retry_whose_message_was_lost_is_sent_by_the_sweeper_once_due(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    exporter: InMemorySpanExporter,
) -> None:
    project_id = await create_project(owner)
    app.state.ingestion.embedders[LOCAL_MODEL].failures = [EmbeddingProviderError("timeout")]
    jobs.deliver_next()
    jobs.lose_next()

    document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    waiting = await only_document(owner, project_id)
    assert waiting["status"] == "queued"
    assert waiting["error_message"] == (
        "The Embedding Model's provider didn't respond. Retrying automatically (attempt 2 of 4)."
    )
    # The first backoff is 10 seconds: not due yet.
    clock.advance(timedelta(seconds=9))
    assert await sweep(clock) == 0
    clock.advance(timedelta(seconds=2))
    assert await sweep(clock) == 1

    retried = await only_document(owner, project_id)
    assert failure_of(retried) == ("ready", None, None)
    assert retried["attempt_count"] == 2
    assert jobs.tasks() == [INGEST_TASK] * 3
    assert recovered(exporter) == [(INGEST_TASK, document["id"], "retry due")]


async def test_lost_retries_never_give_more_provider_attempts_than_the_maximum(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    embedder = app.state.ingestion.embedders[LOCAL_MODEL]
    embedder.failures = [EmbeddingProviderError("down")] * 10
    jobs.deliver_next()
    jobs.lose_next()
    await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    # Each retry's message is lost; the sweeper sends it once it is due.
    for _ in range(3):
        clock.advance(timedelta(minutes=5))
        jobs.deliver_next()
        jobs.lose_next()
        assert await sweep(clock) == 1
    # A lost message that turns up late, still saying it is the first attempt, does nothing.
    jobs.held = [replace_kwargs(jobs.lost[-1], attempt=1)]
    await jobs.release_held()
    clock.advance(timedelta(hours=1))
    assert await sweep(clock) == 0

    document = await only_document(owner, project_id)
    assert failure_of(document) == (
        "failed",
        "provider",
        "The Embedding Model's provider didn't respond after 4 attempts. Retry the Document later.",
    )
    assert document["attempt_count"] == 4
    assert len(embedder.failures) == 10 - 4


def replace_kwargs(job: Job, **kwargs: Any) -> Job:
    return dataclasses.replace(job, kwargs=kwargs)


async def test_the_attempt_number_comes_from_the_row_not_the_message(
    app: FastAPI, owner: SignedUpMember, jobs: RecordingJobPublisher
) -> None:
    """A message claiming to be the last attempt doesn't fail a Document on its first."""
    project_id = await create_project(owner)
    app.state.ingestion.embedders[LOCAL_MODEL].failures = [EmbeddingProviderError("timeout")]
    jobs.hold_next()
    await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    (held,) = jobs.held
    jobs.held = [replace_kwargs(held, attempt=4)]

    await jobs.release_held()

    document = await only_document(owner, project_id)
    assert failure_of(document) == ("ready", None, None)
    assert document["attempt_count"] == 2


# --- The fake converter's test-only switch ------------------------------------------------------


async def test_a_file_marked_for_interruption_is_interrupted_once_then_becomes_ready(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    marked = f"{INTERRUPT_MARKER}{uuid.uuid4()}\n".encode() + HANDBOOK

    await upload(app, owner, project_id, "handbook.md", marked)

    assert len(jobs.killed) == 1
    assert (await only_document(owner, project_id))["status"] == "processing"
    clock.advance(DEAD)
    assert await sweep(clock) == 1
    document = await only_document(owner, project_id)
    assert failure_of(document) == ("ready", None, None)
    assert [c["text"] for c in await chunks(owner, project_id, document["id"])] == [
        "Everyone gets 25 days of annual leave a year."
    ]
