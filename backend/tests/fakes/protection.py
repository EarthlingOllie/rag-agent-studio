"""The recording Scale-in protection: the test fake for the Scale-in protection port.

It records each call the job reliability module makes (protect, renew, release) with the claim
it was made for, in order. Told to, it fails a step, as an unreachable ECS agent would, so tests
can show the job carries on."""

import threading
import uuid

from app.jobs.protection import ScaleInProtection


class ProtectionUnavailableError(Exception):
    """What a step told to fail raises."""


class RecordingProtection(ScaleInProtection):
    def __init__(self) -> None:
        self.calls: list[tuple[str, uuid.UUID]] = []
        self._failing: set[str] = set()
        # Jobs run eagerly in their own threads.
        self._lock = threading.Lock()

    def fail(self, step: str) -> None:
        """Every later ``step`` (protect, renew or release) raises."""
        self._failing.add(step)

    def steps(self) -> list[str]:
        """The steps called, in order, with runs of renewals shown once."""
        steps: list[str] = []
        for step, _ in self.calls:
            if not (step == "renew" and steps and steps[-1] == "renew"):
                steps.append(step)
        return steps

    def holders(self) -> list[uuid.UUID]:
        """The claims protection was set for, in order."""
        return [holder for step, holder in self.calls if step == "protect"]

    def calls_for(self, holder: uuid.UUID) -> list[str]:
        return [step for step, called in self.calls if called == holder]

    async def protect(self, holder: uuid.UUID) -> None:
        self._record("protect", holder)

    async def renew(self, holder: uuid.UUID) -> None:
        self._record("renew", holder)

    async def release(self, holder: uuid.UUID) -> None:
        self._record("release", holder)

    def _record(self, step: str, holder: uuid.UUID) -> None:
        with self._lock:
            self.calls.append((step, holder))
        if step in self._failing:
            raise ProtectionUnavailableError(step)
