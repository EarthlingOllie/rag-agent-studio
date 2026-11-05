"""The clock port: the system clock in production, a controllable clock in tests."""

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """The current time, timezone-aware (UTC)."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class ControllableClock:
    """A clock that only moves when told to (the test fake)."""

    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, by: timedelta) -> None:
        self._now += by


_SYSTEM_CLOCK = SystemClock()


def get_clock() -> Clock:
    """Dependency: the app's clock. Tests replace it through ``dependency_overrides``."""
    return _SYSTEM_CLOCK
