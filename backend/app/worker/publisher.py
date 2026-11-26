"""The Job publisher: the one port every background job is sent through (ADR-0020).

It has one operation per job the application queues. The API sends through it once the job's
row is committed, and tasks send follow-on work through it (an ingestion's next attempt, the
objects it no longer needs). A send that fails is logged with the job and its identifier and
never fails the caller: the committed row is the record of the job. The worker health probe is
the exception, since reporting whether a job gets through is its whole purpose.

The production adapter sends to Celery. Tests swap in a fake (``tests.fakes.jobs``) that
records what was sent and can lose or hold a message.
"""

import abc
import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from celery.result import AsyncResult

from app.worker.celery_app import (
    DELETE_OBJECTS_TASK,
    DELETE_PROJECT_TASK,
    EVALUATION_RUN_TASK,
    INGEST_TASK,
    LIVE_VERDICT_TASK,
    RE_EMBED_TASK,
    SUGGESTION_RUN_TASK,
    celery_app,
)
from app.worker.tasks import health_check

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    """One message for the worker: the task to run, its arguments, and how long to wait."""

    task: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any] = field(default_factory=dict)
    countdown: float | None = None

    @property
    def identifier(self) -> str:
        """What the job is about, for logs: the row it runs for, or the objects it deletes."""
        return str(self.args[0])


class JobPublisher(abc.ABC):
    """The port. Adapters implement ``send``, and ``probe`` for the worker health probe."""

    @abc.abstractmethod
    def send(self, job: Job) -> None:
        """Hands the job to the broker; blocks until it has. Raises when it couldn't."""

    @abc.abstractmethod
    def probe(self) -> "AsyncResult[Any]":
        """Sends the worker health probe and returns its pending reply."""

    async def _publish(self, job: Job) -> None:
        # Sending blocks on the broker; in eager mode (tests) the task itself runs there, with
        # its own event loop.
        try:
            await asyncio.to_thread(self.send, job)
        except Exception:
            logger.exception(
                "Sending a job failed; its row stays as committed",
                extra={"job": job.task, "job_id": job.identifier},
            )

    async def ingest_document(
        self, document_id: uuid.UUID, *, attempt: int = 1, countdown: float | None = None
    ) -> None:
        kwargs = {"attempt": attempt} if attempt > 1 else {}
        await self._publish(Job(INGEST_TASK, (str(document_id),), kwargs, countdown))

    async def delete_objects(self, keys: list[str]) -> None:
        await self._publish(Job(DELETE_OBJECTS_TASK, (keys,)))

    async def run_evaluation(self, run_id: uuid.UUID) -> None:
        await self._publish(Job(EVALUATION_RUN_TASK, (str(run_id),)))

    async def judge_live_verdict(self, verdict_id: uuid.UUID) -> None:
        await self._publish(Job(LIVE_VERDICT_TASK, (str(verdict_id),)))

    async def run_suggestion(self, suggestion_id: uuid.UUID) -> None:
        await self._publish(Job(SUGGESTION_RUN_TASK, (str(suggestion_id),)))

    async def re_embed(
        self, job_id: uuid.UUID, *, attempt: int = 1, countdown: float | None = None
    ) -> None:
        kwargs = {"attempt": attempt} if attempt > 1 else {}
        await self._publish(Job(RE_EMBED_TASK, (str(job_id),), kwargs, countdown))

    async def delete_project(
        self, project_id: uuid.UUID, *, actor_id: uuid.UUID, requested_at: datetime
    ) -> None:
        args = (str(project_id), str(actor_id), requested_at.isoformat())
        await self._publish(Job(DELETE_PROJECT_TASK, args))

    async def probe_worker(self) -> "AsyncResult[Any]":
        """The worker health probe. Unlike every other job, a failed send is raised, and the
        reply is kept for the caller to wait on."""
        return await asyncio.to_thread(self.probe)


class CeleryJobPublisher(JobPublisher):
    """Sends to Celery. Every job but the health probe ignores its result, so nobody
    subscribes to a reply nobody reads."""

    def send(self, job: Job) -> None:
        _task(job.task).apply_async(
            job.args, job.kwargs, countdown=job.countdown, ignore_result=True
        )

    def probe(self) -> "AsyncResult[Any]":
        result: AsyncResult[Any] = health_check.delay()
        return result


def _task(name: str) -> Any:
    """The registered task: importing the task modules (once) registers every task, so the
    API can send any job without importing the code that runs it."""
    celery_app.loader.import_default_modules()
    return celery_app.tasks[name]


_installed: list[JobPublisher] = [CeleryJobPublisher()]


def install_publisher(publisher: JobPublisher) -> None:
    """The API installs its publisher at startup; tests install the fake."""
    _installed[:] = [publisher]


def current_publisher() -> JobPublisher:
    return _installed[0]
