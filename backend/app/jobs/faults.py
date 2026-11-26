"""The test-only way to kill a job: the adapter fakes (converter, embedder, object store) carry
a ``KillSwitch`` that, once armed, stops the job at that point as a worker that died would.

``JobKilled`` is a ``BaseException``, so the job's own error handling (its ``except Exception``)
never runs: nothing marks the row Failed or puts it back, and its heartbeat stops. The fake Job
publisher swallows it where it delivers the job, as the broker loses a killed worker's message.
"""


class JobKilled(BaseException):
    """Raised by an armed fake: the worker running the job is gone."""


class KillSwitch:
    """Kills the next job that reaches a chosen point (an operation of the fake), once."""

    def __init__(self) -> None:
        self._armed: set[str] = set()

    def arm(self, point: str) -> None:
        self._armed.add(point)

    def check(self, point: str) -> None:
        """Called by the fake at each point; raises ``JobKilled`` when armed for it."""
        if point in self._armed:
            self._armed.discard(point)
            raise JobKilled(point)
