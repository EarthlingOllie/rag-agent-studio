"""Under pytest-xdist every worker runs against its own Postgres and Redis databases."""

import asyncio
import os
import uuid

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import BASE_DATABASE_URL, BASE_REDIS_URL, TEST_DATABASE_URL, TEST_REDIS_URL
from tests.worker_resources import (
    ADMIN_DATABASE,
    ensure_database,
    worker_database_url,
    worker_redis_url,
)


def _admin_url() -> str:
    return make_url(TEST_DATABASE_URL).set(database=ADMIN_DATABASE).render_as_string(False)


async def _database_exists(name: str) -> bool:
    engine = create_async_engine(_admin_url())
    try:
        async with engine.connect() as connection:
            found = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            )
            return found is not None
    finally:
        await engine.dispose()


async def _drop_database(name: str) -> None:
    engine = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'DROP DATABASE "{name}"'))
    finally:
        await engine.dispose()


def test_a_missing_database_is_created_once() -> None:
    name = f"studio_test_probe_{uuid.uuid4().hex[:8]}"
    url = make_url(TEST_DATABASE_URL).set(database=name).render_as_string(False)
    try:
        ensure_database(url)
        ensure_database(url)  # already there: no error

        assert asyncio.run(_database_exists(name))
    finally:
        asyncio.run(_drop_database(name))


def test_the_suite_uses_this_workers_databases() -> None:
    worker_id = os.environ.get("PYTEST_XDIST_WORKER")

    assert worker_database_url(BASE_DATABASE_URL, worker_id) == TEST_DATABASE_URL
    assert worker_redis_url(BASE_REDIS_URL, worker_id) == TEST_REDIS_URL


async def test_the_app_talks_to_this_workers_databases(app: FastAPI) -> None:
    async with app.state.sessionmaker() as session:
        database = await session.scalar(text("SELECT current_database()"))
    redis_database = app.state.redis.connection_pool.connection_kwargs["db"]

    assert database == make_url(TEST_DATABASE_URL).database
    assert f"/{redis_database}" == "/" + TEST_REDIS_URL.rsplit("/", 1)[1]
