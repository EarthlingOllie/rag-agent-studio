"""Per-worker test resources, so pytest-xdist workers never share state.

Under ``pytest -n N`` each worker process (``gw0``, ``gw1``, ...) gets its own Postgres
database (``<name>_<worker id>``, created on first use and migrated once per worker) and
its own Redis database (counting down from the configured one). A serial run, with no
worker id, uses the configured names unchanged.
"""

import asyncio
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

SERIAL_WORKER_IDS = (None, "", "master")
ADMIN_DATABASE = "postgres"


def _worker_index(worker_id: str) -> int:
    return int(worker_id.removeprefix("gw"))


def worker_database_url(database_url: str, worker_id: str | None) -> str:
    """The test database URL this worker uses."""
    if worker_id in SERIAL_WORKER_IDS:
        return database_url
    url = make_url(database_url)
    return url.set(database=f"{url.database}_{worker_id}").render_as_string(hide_password=False)


def worker_redis_url(redis_url: str, worker_id: str | None) -> str:
    """The test Redis URL this worker uses: one database below the serial one per worker."""
    if worker_id in SERIAL_WORKER_IDS:
        return redis_url
    parts = urlsplit(redis_url)
    base = int(parts.path.strip("/") or 0)
    database = base - 1 - _worker_index(worker_id)
    if database < 0:
        raise ValueError(
            f"Worker {worker_id} has no free Redis database below {base}; run fewer workers."
        )
    return urlunsplit(parts._replace(path=f"/{database}"))


def ensure_database(database_url: str) -> None:
    """Create the database if it is missing, through the server's admin database."""
    url = make_url(database_url)
    admin_url = url.set(database=ADMIN_DATABASE).render_as_string(hide_password=False)

    async def create() -> None:
        engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as connection:
                exists = await connection.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": url.database},
                )
                if not exists:
                    await connection.execute(text(f'CREATE DATABASE "{url.database}"'))
        finally:
            await engine.dispose()

    asyncio.run(create())
