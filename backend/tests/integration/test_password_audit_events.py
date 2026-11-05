"""Password resets and changes are recorded as Audit Events in the Member's Organisations.

The Owner-only Audit Event list endpoint arrives with ticket 01-05, so on this branch the
events are read straight from the append-only ``audit_events`` table.
"""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.mail.outbox import OutboxMailer
from tests.conftest import TEST_DATABASE_URL, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.integration.test_password_reset import complete_reset, request_reset, reset_token


@pytest.fixture
async def database() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(TEST_DATABASE_URL)
    yield engine
    await engine.dispose()


async def audit_events(database: AsyncEngine, organisation_id: str) -> list[dict[str, Any]]:
    async with database.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT actor_id::text AS actor_id, action, target_type, target_id, before,"
                " after, occurred_at FROM audit_events WHERE organisation_id = :organisation"
                " AND action LIKE 'member.password%' ORDER BY occurred_at"
            ),
            {"organisation": organisation_id},
        )
        return [dict(row._mapping) for row in rows]


async def test_a_completed_reset_is_recorded(
    owner: SignedUpMember,
    client: httpx.AsyncClient,
    outbox: OutboxMailer,
    clock: ControllableClock,
    database: AsyncEngine,
) -> None:
    await request_reset(client, owner.email)
    assert await audit_events(database, owner.organisation_id) == []

    assert (await complete_reset(client, reset_token(outbox, owner.email))).status_code == 204

    assert await audit_events(database, owner.organisation_id) == [
        {
            "actor_id": owner.member_id,
            "action": "member.password_reset",
            "target_type": "member",
            "target_id": owner.member_id,
            "before": None,
            "after": None,
            "occurred_at": clock.now(),
        }
    ]


async def test_a_password_change_is_recorded_and_a_refused_one_is_not(
    owner: SignedUpMember, clock: ControllableClock, database: AsyncEngine
) -> None:
    refused = await owner.client.post(
        "/api/auth/me/password",
        json={"current_password": "not my password", "new_password": "changed on purpose 789"},
    )
    assert refused.status_code == 400
    assert await audit_events(database, owner.organisation_id) == []

    changed = await owner.client.post(
        "/api/auth/me/password",
        json={"current_password": owner.password, "new_password": "changed on purpose 789"},
    )

    assert changed.status_code == 204
    events = await audit_events(database, owner.organisation_id)
    assert [(e["actor_id"], e["action"], e["target_id"]) for e in events] == [
        (owner.member_id, "member.password_changed", owner.member_id)
    ]
    occurred_at: datetime = events[0]["occurred_at"]
    assert occurred_at == clock.now()
