"""The controllable clock: the test fake for the Clock port."""

from datetime import UTC, datetime, timedelta


class ControllableClock:
    """A clock that stands still until a test moves it forward."""

    def __init__(self, start: datetime = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, by: timedelta | float) -> None:
        """Moves the clock forward (or back) by a timedelta or a number of seconds."""
        self._now += by if isinstance(by, timedelta) else timedelta(seconds=by)
