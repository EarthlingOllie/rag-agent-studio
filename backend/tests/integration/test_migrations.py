"""Migrations are excluded from coverage (ADR-0008), so every one must survive a round trip:
upgrade to head, downgrade to base, and upgrade to head again."""

import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    return Config(str(BACKEND_ROOT / "alembic.ini"))


def _database_state(database_url: str) -> tuple[str | None, bool]:
    """Return (current revision, whether pgvector is installed)."""

    async def query() -> tuple[str | None, bool]:
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as connection:
                has_version_table = await connection.scalar(
                    text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
                )
                revision = (
                    await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    if has_version_table
                    else None
                )
                has_vector = await connection.scalar(
                    text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
                )
                return revision, bool(has_vector)
        finally:
            await engine.dispose()

    return asyncio.run(query())


def test_migrations_upgrade_to_head_and_downgrade_to_base(
    settings_env: pytest.MonkeyPatch,
) -> None:
    from tests.conftest import TEST_DATABASE_URL

    config = _alembic_config()
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None

    command.upgrade(config, "head")
    assert _database_state(TEST_DATABASE_URL) == (head, True)

    command.downgrade(config, "base")
    assert _database_state(TEST_DATABASE_URL) == (None, False)

    command.upgrade(config, "head")
    assert _database_state(TEST_DATABASE_URL) == (head, True)
