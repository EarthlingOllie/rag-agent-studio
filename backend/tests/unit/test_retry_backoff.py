"""The backoff between automatic retries of a transient ingestion failure."""

from app.documents.limits import retry_delay


def test_the_wait_doubles_after_each_failed_attempt_up_to_the_maximum() -> None:
    delays = [retry_delay(attempt, base_seconds=10, max_seconds=60) for attempt in range(1, 6)]

    assert delays == [10, 20, 40, 60, 60]
