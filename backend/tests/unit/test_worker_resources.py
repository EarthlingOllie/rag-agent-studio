"""Each pytest-xdist worker gets its own Postgres database and Redis database.

A serial run (no worker id) keeps the configured names exactly.
"""

import pytest

from tests.worker_resources import worker_database_url, worker_redis_url

DATABASE = "postgresql+asyncpg://studio:studio@localhost:5432/studio_test"
REDIS = "redis://localhost:6379/15"


@pytest.mark.parametrize("worker_id", [None, "", "master"])
def test_a_serial_run_keeps_the_configured_names(worker_id: str | None) -> None:
    assert worker_database_url(DATABASE, worker_id) == DATABASE
    assert worker_redis_url(REDIS, worker_id) == REDIS


def test_each_worker_gets_its_own_database() -> None:
    assert worker_database_url(DATABASE, "gw0") == (
        "postgresql+asyncpg://studio:studio@localhost:5432/studio_test_gw0"
    )
    assert worker_database_url(DATABASE, "gw11") == (
        "postgresql+asyncpg://studio:studio@localhost:5432/studio_test_gw11"
    )


def test_the_database_query_string_is_kept() -> None:
    url = "postgresql+asyncpg://studio:studio@db:5432/studio_test?ssl=disable"

    assert worker_database_url(url, "gw2") == (
        "postgresql+asyncpg://studio:studio@db:5432/studio_test_gw2?ssl=disable"
    )


def test_each_worker_gets_a_redis_database_below_the_serial_one() -> None:
    assert worker_redis_url(REDIS, "gw0") == "redis://localhost:6379/14"
    assert worker_redis_url(REDIS, "gw1") == "redis://localhost:6379/13"
    assert worker_redis_url(REDIS, "gw14") == "redis://localhost:6379/0"


def test_more_workers_than_redis_databases_is_refused() -> None:
    with pytest.raises(ValueError, match="gw15"):
        worker_redis_url(REDIS, "gw15")


def test_a_redis_url_without_a_database_counts_down_from_database_0() -> None:
    with pytest.raises(ValueError, match="gw0"):
        worker_redis_url("redis://localhost:6379", "gw0")
