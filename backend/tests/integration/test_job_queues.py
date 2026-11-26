"""Jobs go through SQS (ticket 22-03, ADR-0021), on Floci here as in the compose stack.

The API creates both queues at startup when SQS_CREATE_QUEUES says so (Floci starts empty;
Terraform creates them in AWS). A real worker takes jobs from them, and an automatic retry, which
waits its backoff before it runs again, gets through the transport too. Outcomes are read through
the API and through SQS itself (whether a queue exists, and its visibility timeout)."""

import asyncio
import contextlib
import uuid
from collections.abc import Iterator

import pytest
from asgi_lifespan import LifespanManager
from botocore.exceptions import ClientError
from celery.contrib.testing.worker import start_worker
from fastapi import FastAPI

from app.embeddings.port import EmbeddingProviderError
from app.main import create_app
from app.worker.celery_app import celery_app
from tests.conftest import TEST_SQS_ENDPOINT_URL, SignedUpMember
from tests.documents import create_project, documents, upload
from tests.sqs import client, empty_queues

HANDBOOK = b"# Handbook\n\nEveryone gets 25 days of annual leave a year."
LOCAL_MODEL = "multilingual-e5-small"


@pytest.fixture
def new_queues(settings_env: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    """Queue names no test has used, in the settings; deleted afterwards."""
    names = {kind: f"studio-test-{kind}-{uuid.uuid4().hex[:12]}" for kind in ("general", "runs")}
    for kind, name in names.items():
        settings_env.setenv(f"{kind.upper()}_QUEUE_NAME", name)
        settings_env.setenv(
            f"{kind.upper()}_QUEUE_URL", f"{TEST_SQS_ENDPOINT_URL}/000000000000/{name}"
        )
    yield names
    sqs = client()
    for name in names.values():
        with contextlib.suppress(ClientError):  # never created
            sqs.delete_queue(QueueUrl=sqs.get_queue_url(QueueName=name)["QueueUrl"])


def visibility_timeout(name: str) -> int:
    sqs = client()
    url = sqs.get_queue_url(QueueName=name)["QueueUrl"]
    attributes = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["VisibilityTimeout"])
    return int(attributes["Attributes"]["VisibilityTimeout"])


async def test_the_api_creates_both_queues_at_startup_when_told_to(
    settings_env: pytest.MonkeyPatch, new_queues: dict[str, str]
) -> None:
    settings_env.setenv("SQS_CREATE_QUEUES", "true")

    async with LifespanManager(create_app()):
        pass
    # Starting again, with the queues already there, works too.
    async with LifespanManager(create_app()):
        pass

    # The visibility timeouts the queue module gives them in AWS: one hour, and twelve.
    assert visibility_timeout(new_queues["general"]) == 3600
    assert visibility_timeout(new_queues["runs"]) == 43200


async def test_the_api_creates_no_queue_unless_told_to(
    settings_env: pytest.MonkeyPatch, new_queues: dict[str, str]
) -> None:
    async with LifespanManager(create_app()):
        pass

    for name in new_queues.values():
        with pytest.raises(ClientError, match=r"NonExistentQueue|QueueDoesNotExist"):
            client().get_queue_url(QueueName=name)


# --- A real worker on SQS -----------------------------------------------------------------------


@pytest.fixture
def through_sqs(settings_env: pytest.MonkeyPatch) -> Iterator[None]:
    """Jobs go through the test queues to a worker instead of running eagerly. Requested before
    ``app``, so the app starts with it."""
    settings_env.setenv("CELERY_TASK_ALWAYS_EAGER", "false")
    settings_env.setenv("INGESTION_RETRY_BASE_SECONDS", "1")
    empty_queues()
    yield
    empty_queues()


@pytest.fixture
def sqs_app(through_sqs: None, app: FastAPI) -> FastAPI:
    return app


async def wait_for_status(owner: SignedUpMember, project_id: str, status: str) -> str:
    seen = ""
    for _ in range(150):
        (listed,) = await documents(owner, project_id)
        seen = listed["status"]
        if seen == status:
            break
        await asyncio.sleep(0.2)
    return seen


async def test_an_automatic_retry_gets_through_sqs_to_a_worker(
    sqs_app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    # The Embedding Model's provider fails once: the ingestion is retried after its backoff.
    sqs_app.state.ingestion.embedders[LOCAL_MODEL].failures = [EmbeddingProviderError("timeout")]

    with start_worker(celery_app, pool="solo", perform_ping_check=False, shutdown_timeout=10):
        document = await upload(sqs_app, owner, project_id, "handbook.md", HANDBOOK)
        status = await wait_for_status(owner, project_id, "ready")

    assert status == "ready"
    (listed,) = await documents(owner, project_id)
    assert listed["id"] == document["id"]
    assert sqs_app.state.ingestion.embedders[LOCAL_MODEL].failures == []
