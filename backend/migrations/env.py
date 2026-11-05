"""Alembic environment: runs migrations over the async engine built from validated settings."""

import asyncio

from alembic import context
from sqlalchemy import MetaData
from sqlalchemy.engine import Connection

from app.core.db import create_engine
from app.core.logs import configure_logging
from app.core.settings import load_settings

config = context.config
if config.attributes.get("configure_logger", True):
    configure_logging("migrations")

# Models register their tables on this metadata as they are introduced.
target_metadata = MetaData()


def run_migrations_offline() -> None:
    context.configure(
        url=str(load_settings().database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_engine(load_settings())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_sync_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
