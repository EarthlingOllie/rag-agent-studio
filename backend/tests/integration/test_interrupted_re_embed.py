"""API seam plus task seam for a Re-embed that is cut short (spec 21, ADR-0020): a worker killed
mid-job, a job or retry that never reached the queue, two copies of one job, a job that keeps
being interrupted, and Re-embeds stuck before the sweeper looked after them.

The new model's provider is scripted (``tests.integration.test_re_embedding.Script``): a
``kill`` step stops the job as a dead worker would, without its error handling, and the script
counts the embedding calls. A lost message comes from the Job publisher fake. The sweeper is
called as a task, as Beat calls it, with the controllable clock moved past each threshold.
Outcomes are read through the API, as an Editor sees them, and the traces."""

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import update

from app.documents.models import Document, DocumentStatus, StagedEdition
from app.main import create_app
from app.re_embedding.models import ReEmbedJob, ReEmbedStatus
from app.re_embedding.tasks import re_embed_project
from tests.conftest import SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.fakes.jobs import RecordingJobPublisher
from tests.integration.test_embedding_models import LOCAL, choose
from tests.integration.test_interrupted_ingestion import recovered, sweep
from tests.integration.test_provider_credentials import audit_events
from tests.integration.test_re_embedding import (
    EXPENSES,
    LEAVE,
    OFFICES,
    VOYAGE,
    credential,
    knowledge_base,
    probe_models,
    progress,
    re_embed,
    scripted,
    state,
)

RE_EMBED = "projects.re_embed"


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
    """Earlier tests on this worker's database may have left Documents or Re-embeds in flight;
    each test here starts with them settled, so every sweep sees only the test's own rows."""
    in_flight = (DocumentStatus.QUEUED, DocumentStatus.PROCESSING)
    async with app.state.sessionmaker() as session, session.begin():
        for model in (Document, StagedEdition):
            await session.execute(
                update(model)
                .where(model.status.in_(in_flight))
                .values(status=DocumentStatus.FAILED, claim_id=None, heartbeat_at=None)
            )
        await session.execute(
            update(ReEmbedJob)
            .where(ReEmbedJob.status == ReEmbedStatus.RUNNING)
            .values(status=ReEmbedStatus.FAILED, claim_id=None, heartbeat_at=None)
        )


def re_embeds_sent(jobs: RecordingJobPublisher) -> int:
    return jobs.tasks().count(RE_EMBED)


async def deliver_again(job_id: str) -> None:
    """A second delivery of the re-embed job, straight to the worker."""
    await asyncio.to_thread(re_embed_project.apply, args=(job_id,))


# --- A worker killed mid-job ----------------------------------------------------------------


async def test_a_re_embed_whose_worker_died_resumes_from_the_chunks_it_had_not_done(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    exporter: InMemorySpanExporter,
    settings_env: pytest.MonkeyPatch,
) -> None:
    settings_env.setenv("RE_EMBED_BATCH_SIZE", "1")
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE, EXPENSES, OFFICES)
    # The first batch is embedded and written; the worker dies embedding the second.
    script = scripted(app, "ok", "kill")

    await choose(owner, project_id, VOYAGE, voyage)

    assert len(jobs.killed) == 1
    job = await re_embed(owner, project_id)
    assert progress(job) == ("running", 1, 3)
    # Within the dead-after time, the sweeper leaves it alone.
    clock.advance(timedelta(minutes=4, seconds=59))
    assert await sweep(clock) == 0
    assert script.calls == 2

    clock.advance(timedelta(seconds=2))
    assert await sweep(clock) == 1

    assert progress(await re_embed(owner, project_id)) == ("completed", 3, 3)
    # Only the two Chunks still missing the new vector were embedded again.
    assert script.calls == 4
    assert (await state(owner, project_id))["model_id"] == VOYAGE
    assert await probe_models(owner, project_id, OFFICES) == (VOYAGE, OFFICES)
    assert recovered(exporter) == [(RE_EMBED, job["id"], "no heartbeat")]


async def test_a_live_re_embed_keeps_writing_heartbeats_so_the_sweeper_leaves_it_alone(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JOB_HEARTBEAT_SECONDS", "0.05")
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    script = scripted(app, "hold")
    choosing = asyncio.create_task(choose(owner, project_id, VOYAGE, voyage))
    await script.wait_until_held()

    clock.advance(timedelta(minutes=10))
    await asyncio.sleep(0.5)

    assert await sweep(clock) == 0
    script.release()
    await choosing
    assert progress(await re_embed(owner, project_id)) == ("completed", 1, 1)
    assert script.calls == 1


# --- A job or retry that never reached the queue --------------------------------------------


async def test_a_re_embed_that_never_reached_the_queue_starts_within_fifteen_minutes(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    exporter: InMemorySpanExporter,
) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    jobs.lose_next()

    await choose(owner, project_id, VOYAGE, voyage)

    job = await re_embed(owner, project_id)
    assert progress(job) == ("running", 0, 1)
    clock.advance(timedelta(minutes=14))
    assert await sweep(clock) == 0

    clock.advance(timedelta(minutes=1, seconds=1))
    assert await sweep(clock) == 1

    assert re_embeds_sent(jobs) == 2
    assert progress(await re_embed(owner, project_id)) == ("completed", 1, 1)
    assert recovered(exporter) == [(RE_EMBED, job["id"], "queued too long")]


async def test_a_re_embed_whose_retry_was_lost_starts_within_fifteen_minutes_of_its_due_time(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    # The provider fails the first attempt; its retry, due in 10 seconds, is lost.
    script = scripted(app, "fail")
    jobs.deliver_next()
    jobs.lose_next()

    await choose(owner, project_id, VOYAGE, voyage)

    assert [job.kwargs for job in jobs.lost] == [{"attempt": 2}]
    assert (await re_embed(owner, project_id))["status"] == "running"
    clock.advance(timedelta(minutes=15))
    assert await sweep(clock) == 0

    clock.advance(timedelta(seconds=11))
    assert await sweep(clock) == 1

    assert re_embeds_sent(jobs) == 3
    assert progress(await re_embed(owner, project_id)) == ("completed", 1, 1)
    assert script.calls == 2


# --- Two copies of one job ------------------------------------------------------------------


async def test_a_second_copy_of_a_running_re_embed_fails_to_claim_and_embeds_nothing(
    app: FastAPI, owner: SignedUpMember, jobs: RecordingJobPublisher
) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    script = scripted(app, "hold")
    choosing = asyncio.create_task(choose(owner, project_id, VOYAGE, voyage))
    await script.wait_until_held()
    job = await re_embed(owner, project_id)

    await deliver_again(job["id"])

    assert script.calls == 1
    script.release()
    await choosing
    assert progress(await re_embed(owner, project_id)) == ("completed", 1, 1)
    assert script.calls == 1


async def test_a_re_embed_delivered_again_after_it_completed_does_nothing(
    app: FastAPI, owner: SignedUpMember, jobs: RecordingJobPublisher
) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    script = scripted(app)
    await choose(owner, project_id, VOYAGE, voyage)
    job = await re_embed(owner, project_id)

    await deliver_again(job["id"])

    assert script.calls == 1
    assert progress(await re_embed(owner, project_id)) == ("completed", 1, 1)


async def test_an_older_copy_still_running_after_a_restart_writes_nothing(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first copy stalls in its provider call (its heartbeat seems to stop), is given up for
    dead and restarted; the restarted copy switches over, and the first, waking up, writes
    nothing."""
    monkeypatch.setenv("JOB_HEARTBEAT_SECONDS", "3600")
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    script = scripted(app, "hold")
    choosing = asyncio.create_task(choose(owner, project_id, VOYAGE, voyage))
    await script.wait_until_held()
    clock.advance(timedelta(minutes=6))
    assert await sweep(clock) == 1
    assert progress(await re_embed(owner, project_id)) == ("completed", 1, 1)

    script.release()
    await choosing

    assert progress(await re_embed(owner, project_id)) == ("completed", 1, 1)
    assert (await state(owner, project_id))["model_id"] == VOYAGE
    assert await probe_models(owner, project_id, LEAVE) == (VOYAGE, LEAVE)


# --- A job that keeps being interrupted -----------------------------------------------------


async def test_a_re_embed_interrupted_three_times_without_progress_fails_and_can_be_chosen_again(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    script = scripted(app, "kill", "kill", "kill")
    await choose(owner, project_id, VOYAGE, voyage)

    for _ in range(2):
        clock.advance(timedelta(minutes=6))
        assert await sweep(clock) == 1
        assert (await re_embed(owner, project_id))["status"] == "running"
    clock.advance(timedelta(minutes=6))
    assert await sweep(clock) == 1

    job = await re_embed(owner, project_id)
    assert (job["status"], job["error_message"]) == (
        "failed",
        "Re-embedding was interrupted 3 times without embedding any new Chunks. "
        "The Project still uses multilingual-e5-small; choose the model again to retry.",
    )
    assert script.calls == 3
    assert (await state(owner, project_id))["model_id"] == LOCAL
    assert await probe_models(owner, project_id, LEAVE) == (LOCAL, LEAVE)
    (failed,) = await audit_events(owner, "project.re_embed_failed")
    assert failed["after"]["error_message"] == job["error_message"]

    await choose(owner, project_id, VOYAGE, voyage)

    again = await re_embed(owner, project_id)
    assert again["id"] != job["id"]
    assert progress(again) == ("completed", 1, 1)
    assert (await state(owner, project_id))["model_id"] == VOYAGE


async def test_interruptions_with_new_chunks_embedded_in_between_never_reach_the_cap(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    settings_env: pytest.MonkeyPatch,
) -> None:
    settings_env.setenv("RE_EMBED_BATCH_SIZE", "1")
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE, EXPENSES, OFFICES)
    # Each restart embeds one more Chunk before the worker dies again.
    scripted(app, "kill", "ok", "kill", "ok", "kill")
    await choose(owner, project_id, VOYAGE, voyage)

    for embedded in (1, 2):
        clock.advance(timedelta(minutes=6))
        assert await sweep(clock) == 1
        assert progress(await re_embed(owner, project_id)) == ("running", embedded, 3)
    clock.advance(timedelta(minutes=6))
    assert await sweep(clock) == 1

    assert progress(await re_embed(owner, project_id)) == ("completed", 3, 3)


async def test_the_interruption_cap_is_a_setting(
    app: FastAPI,
    owner: SignedUpMember,
    clock: ControllableClock,
    jobs: RecordingJobPublisher,
    settings_env: pytest.MonkeyPatch,
) -> None:
    settings_env.setenv("RE_EMBED_MAX_INTERRUPTIONS", "1")
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    scripted(app, "kill")
    await choose(owner, project_id, VOYAGE, voyage)

    clock.advance(timedelta(minutes=6))
    assert await sweep(clock) == 1

    job = await re_embed(owner, project_id)
    assert (job["status"], job["error_message"]) == (
        "failed",
        "Re-embedding was interrupted 1 times without embedding any new Chunks. "
        "The Project still uses multilingual-e5-small; choose the model again to retry.",
    )


# --- Re-embeds stuck before this shipped ----------------------------------------------------


async def test_re_embeds_stuck_before_the_sweeper_shipped_are_resumed_by_the_first_sweep(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock, jobs: RecordingJobPublisher
) -> None:
    """A job left running by the code before this, as the migration leaves it: no claim, and its
    start (an hour ago) taken as the time it was queued."""
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    jobs.lose_next()
    await choose(owner, project_id, VOYAGE, voyage)
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(
            update(ReEmbedJob)
            .where(ReEmbedJob.status == ReEmbedStatus.RUNNING)
            .values(queued_at=clock.now() - timedelta(hours=1))
        )

    assert await sweep(clock) == 1

    assert progress(await re_embed(owner, project_id)) == ("completed", 1, 1)
    assert (await state(owner, project_id))["model_id"] == VOYAGE
