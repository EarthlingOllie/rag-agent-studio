"""The recording Job publisher: the test fake for the Job publisher port.

It records every job sent, then hands it on to the adapter it wraps (in tests, Celery in eager
mode, so the job runs at once). Told to, it loses the next job (as a broker that dropped it
would), holds it until released (as a busy worker would), or fails to send it.

A job killed through an adapter fake's kill switch (``app.jobs.faults``) stops where it was: the
fake swallows ``JobKilled`` as the broker forgets a dead worker's message."""

import asyncio
from typing import Any

from celery.result import AsyncResult

from app.jobs.faults import JobKilled
from app.worker.publisher import Job, JobPublisher


class RecordingJobPublisher(JobPublisher):
    def __init__(self, deliver_to: JobPublisher) -> None:
        self._deliver_to = deliver_to
        self.sent: list[Job] = []
        self.lost: list[Job] = []
        self.held: list[Job] = []
        self.killed: list[Job] = []
        self._next: list[str] = []
        self._kill_senders_of: set[str] = set()
        self._failure: Exception | None = None

    def deliver_next(self) -> None:
        """The next job is delivered (so that a fate told after it applies to the one after)."""
        self._next.append("deliver")

    def lose_next(self) -> None:
        self._next.append("lose")

    def hold_next(self) -> None:
        self._next.append("hold")

    def kill_when_sending(self, task: str) -> None:
        """The next job that sends ``task`` dies there, before it is sent."""
        self._kill_senders_of.add(task)

    def fail_next(self, error: Exception) -> None:
        """The next send (the health probe's included) raises ``error``."""
        self._failure = error

    def tasks(self) -> list[str]:
        return [job.task for job in self.sent]

    def send(self, job: Job) -> None:
        self._raise_failure()
        if job.task in self._kill_senders_of:
            self._kill_senders_of.discard(job.task)
            raise JobKilled(f"sending {job.task}")
        self.sent.append(job)
        fate = self._next.pop(0) if self._next else "deliver"
        if fate == "lose":
            self.lost.append(job)
        elif fate == "hold":
            self.held.append(job)
        else:
            self._deliver(job)

    def probe(self) -> "AsyncResult[Any]":
        self._raise_failure()
        return self._deliver_to.probe()

    async def release_held(self) -> None:
        """Delivers the held jobs, in the order they were sent."""
        held, self.held = self.held, []
        for job in held:
            await asyncio.to_thread(self._deliver, job)

    def _deliver(self, job: Job) -> None:
        try:
            self._deliver_to.send(job)
        except JobKilled:
            self.killed.append(job)

    def _raise_failure(self) -> None:
        failure, self._failure = self._failure, None
        if failure is not None:
            raise failure
