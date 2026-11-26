"""API seam plus task seam: every background job is sent through the Job publisher (ticket
21-01). The fake publisher records what was sent and can lose, hold or fail a message; a send
that fails never fails the request that queued the job, since its committed row is the record
(ADR-0020). Outcomes are read through the API.

The last tests send through the real Celery adapter to the Redis broker and read the message
there, which has no API surface: every job but the worker health probe ignores its result."""

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import redis
from fastapi import FastAPI

from app.core.settings import load_settings
from app.embeddings.port import EmbeddingProviderError
from app.worker.celery_app import (
    DELETE_OBJECTS_TASK,
    DELETE_PROJECT_TASK,
    EVALUATION_RUN_TASK,
    HEALTH_CHECK_TASK,
    INGEST_TASK,
    LIVE_VERDICT_TASK,
    RE_EMBED_TASK,
    SUGGESTION_RUN_TASK,
    configure_celery,
)
from app.worker.publisher import CeleryJobPublisher, Job
from tests.conftest import TEST_REDIS_URL, SignedUpMember
from tests.documents import create_project, documents, replace, upload
from tests.fakes.jobs import RecordingJobPublisher

HANDBOOK = b"# Handbook\n\nEveryone gets 25 days of annual leave a year."
LOCAL_MODEL = "multilingual-e5-small"


async def status_of(owner: SignedUpMember, project_id: str) -> str:
    (listed,) = await documents(owner, project_id)
    status: str = listed["status"]
    return status


async def test_a_send_that_fails_does_not_fail_the_upload_and_is_logged(
    app: FastAPI,
    owner: SignedUpMember,
    jobs: RecordingJobPublisher,
    caplog: pytest.LogCaptureFixture,
) -> None:
    project_id = await create_project(owner)
    jobs.fail_next(ConnectionError("broker unreachable"))

    with caplog.at_level(logging.ERROR, logger="app.worker.publisher"):
        document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    # The Document is committed, Queued, and stays the record of the job.
    assert await status_of(owner, project_id) == "queued"
    (record,) = [r for r in caplog.records if r.name == "app.worker.publisher"]
    assert (record.__dict__["job"], record.__dict__["job_id"]) == (INGEST_TASK, document["id"])
    assert record.exc_info is not None


async def test_a_lost_job_leaves_its_row_as_committed(
    app: FastAPI, owner: SignedUpMember, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    jobs.lose_next()

    document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    assert await status_of(owner, project_id) == "queued"
    assert jobs.lost == [Job(INGEST_TASK, (document["id"],))]


async def test_a_held_job_runs_once_released(
    app: FastAPI, owner: SignedUpMember, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    jobs.hold_next()

    await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    held = await status_of(owner, project_id)
    await jobs.release_held()

    assert held == "queued"
    assert await status_of(owner, project_id) == "ready"
    assert jobs.held == []


async def test_an_automatic_retry_is_sent_through_the_publisher(
    app: FastAPI, owner: SignedUpMember, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    app.state.ingestion.embedders[LOCAL_MODEL].failures = [EmbeddingProviderError("timeout")]

    document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    first, second = jobs.sent
    assert first == Job(INGEST_TASK, (document["id"],))
    assert (second.task, second.args, second.kwargs) == (
        INGEST_TASK,
        (document["id"],),
        {"attempt": 2},
    )
    assert second.countdown is not None
    assert second.countdown > 0
    assert await status_of(owner, project_id) == "ready"


async def test_object_deletions_after_ingestion_are_sent_through_the_publisher(
    app: FastAPI, owner: SignedUpMember, jobs: RecordingJobPublisher
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    replaced = await replace(
        app, owner, project_id, document["id"], "handbook.md", HANDBOOK + b"\n\nAnd 3 days off."
    )

    assert replaced.status_code == 202, replaced.text
    # Ingesting the new edition sends the object-deletion job, which carries no keys: the old
    # edition's are in the deletions table.
    assert jobs.tasks() == [INGEST_TASK, INGEST_TASK, DELETE_OBJECTS_TASK]
    assert jobs.sent[-1] == Job(DELETE_OBJECTS_TASK, ())


async def test_a_worker_health_probe_that_cannot_be_sent_is_reported(
    app: FastAPI, owner: SignedUpMember, jobs: RecordingJobPublisher
) -> None:
    jobs.fail_next(ConnectionError("broker unreachable"))

    failed = await owner.client.get("/api/health/worker")
    answered = await owner.client.get("/api/health/worker")

    assert (failed.status_code, failed.json()) == (503, {"status": "error", "reply": None})
    assert (answered.status_code, answered.json()) == (200, {"status": "ok", "reply": "pong"})


# --- Through the Redis broker -----------------------------------------------------------------


@pytest.fixture
def broker(settings_env: pytest.MonkeyPatch) -> Iterator[redis.Redis]:
    """Celery sending to the test Redis broker instead of running tasks eagerly; the queue is
    emptied afterwards, and the next app's startup configures Celery again."""
    settings_env.setenv("CELERY_TASK_ALWAYS_EAGER", "false")
    configure_celery(load_settings())
    with redis.Redis.from_url(TEST_REDIS_URL) as connection:
        connection.flushdb()
        yield connection
        connection.flushdb()


def queued_headers(connection: redis.Redis) -> dict[str, dict[str, object]]:
    messages = [json.loads(raw) for raw in connection.lrange("celery", 0, -1)]
    return {message["headers"]["task"]: message["headers"] for message in messages}


def test_every_job_but_the_health_probe_ignores_its_result(broker: redis.Redis) -> None:
    publisher = CeleryJobPublisher()
    requested_at = datetime(2026, 11, 26, tzinfo=UTC).isoformat()
    for job in (
        Job(INGEST_TASK, ("document",)),
        Job(INGEST_TASK, ("retried-document",), {"attempt": 2}, countdown=5),
        Job(DELETE_OBJECTS_TASK, ()),
        Job(EVALUATION_RUN_TASK, ("run",)),
        Job(LIVE_VERDICT_TASK, ("verdict",)),
        Job(SUGGESTION_RUN_TASK, ("suggestion",)),
        Job(RE_EMBED_TASK, ("re-embed",)),
        Job(DELETE_PROJECT_TASK, ("project", "actor", requested_at)),
    ):
        publisher.send(job)
    publisher.probe()

    headers = queued_headers(broker)

    assert {task: header["ignore_result"] for task, header in headers.items()} == {
        INGEST_TASK: True,
        DELETE_OBJECTS_TASK: True,
        EVALUATION_RUN_TASK: True,
        LIVE_VERDICT_TASK: True,
        SUGGESTION_RUN_TASK: True,
        RE_EMBED_TASK: True,
        DELETE_PROJECT_TASK: True,
        HEALTH_CHECK_TASK: False,
    }
