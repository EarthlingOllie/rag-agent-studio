"""The clock port. Production reads the system clock; tests swap in a controllable one."""

from datetime import UTC, datetime
from typing import Protocol

from fastapi import Request


class Clock(Protocol):
    def now(self) -> datetime:
        """The current time, timezone-aware."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock
