"""Audit Events, at the API seam.

Events are written through the audit module's one public operation, ``app.audit.record``,
which later specs call alongside each change they make. They are read back only through the
Owner-only list endpoint. Until invites arrive (ticket 01-08) nothing in the API makes an
Editor, so ``add_member`` inserts that membership directly.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import audit
from app.tenancy.models import Membership, Role
from tests.conftest import SignedUpMember, TenantFactory


def _events_path(organisation_id: str) -> str:
    return f"/api/organisations/{organisation_id}/audit-events"


async def _list(member: SignedUpMember, **params: Any) -> httpx.Response:
    return await member.client.get(_events_path(member.organisation_id), params=params)


async def test_signing_up_records_the_organisation_being_created(
    owner: SignedUpMember,
) -> None:
    response = await _list(owner)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    (event,) = body["items"]
    assert event["action"] == "organisation.created"
    assert event["actor"] == {"id": owner.member_id, "name": owner.name, "email": owner.email}
    assert event["target"] == {"type": "organisation", "id": owner.organisation_id}
    assert event["before"] is None
    assert event["after"] == {"name": owner.organisation_name}
    occurred_at = datetime.fromisoformat(event["occurred_at"])
    assert abs(datetime.now(UTC) - occurred_at) < timedelta(minutes=1)


def _sessions(app: FastAPI) -> async_sessionmaker[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] = app.state.sessionmaker
    return sessionmaker


async def add_member(
    app: FastAPI, member: SignedUpMember, organisation_id: str, role: Role
) -> None:
    """Gives ``member`` a role in another Organisation (stands in for invites until 01-08)."""
    async with _sessions(app).begin() as session:
        session.add(
            Membership(
                organisation_id=uuid.UUID(organisation_id),
                member_id=uuid.UUID(member.member_id),
                role=role,
            )
        )


async def record_event(
    app: FastAPI,
    organisation_id: str,
    *,
    actor_id: str | None,
    action: str,
    target: audit.AuditTarget | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> None:
    """Records and commits an Audit Event, as a later feature's change would."""
    async with _sessions(app).begin() as session:
        await audit.record(
            session,
            organisation_id=uuid.UUID(organisation_id),
            actor_id=None if actor_id is None else uuid.UUID(actor_id),
            action=action,
            target=target or audit.AuditTarget("member", uuid.uuid4()),
            before=before,
            after=after,
            occurred_at=occurred_at,
        )


async def test_recorded_events_keep_the_actor_action_target_and_before_after_values(
    app: FastAPI, owner: SignedUpMember
) -> None:
    target_id = uuid.uuid4()
    at = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)
    await record_event(
        app,
        owner.organisation_id,
        actor_id=owner.member_id,
        action="member.role_changed",
        target=audit.AuditTarget("member", target_id),
        before={"role": "editor"},
        after={"role": "owner"},
        occurred_at=at,
    )

    body = (await _list(owner, action="member.role_changed")).json()

    (event,) = body["items"]
    assert event["actor"]["id"] == owner.member_id
    assert event["target"] == {"type": "member", "id": str(target_id)}
    assert (event["before"], event["after"]) == ({"role": "editor"}, {"role": "owner"})
    assert datetime.fromisoformat(event["occurred_at"]) == at


async def test_an_event_can_have_no_actor_and_a_target_without_an_id(
    app: FastAPI, owner: SignedUpMember
) -> None:
    await record_event(
        app,
        owner.organisation_id,
        actor_id=None,
        action="organisation.settings_viewed",
        target=audit.AuditTarget("organisation_settings"),
    )

    (event,) = (await _list(owner, action="organisation.settings_viewed")).json()["items"]

    assert event["actor"] is None
    assert event["target"] == {"type": "organisation_settings", "id": None}
    assert (event["before"], event["after"]) == (None, None)


async def test_secret_like_fields_are_redacted_before_storage(
    app: FastAPI, owner: SignedUpMember
) -> None:
    await record_event(
        app,
        owner.organisation_id,
        actor_id=owner.member_id,
        action="credential.rotated",
        before={
            "label": "OpenAI production",
            "api_key": "sk-before-1234",
            "nested": {"Client_Secret": "s3cr3t", "region": "eu-west-2"},
            "headers": [{"Authorization": "Bearer abc"}, {"accept": "json"}],
        },
        after={
            "label": "OpenAI production",
            "apiKey": "sk-after-5678",
            "password_hash": "$argon2id$...",
            "totp_secret": "JBSWY3DP",
            "recovery_codes": ["a", "b"],
            "session_token": "t",
            "private-key": "-----BEGIN",
        },
    )

    (event,) = (await _list(owner, action="credential.rotated")).json()["items"]

    assert event["before"] == {
        "label": "OpenAI production",
        "api_key": "[Redacted]",
        "nested": {"Client_Secret": "[Redacted]", "region": "eu-west-2"},
        "headers": [{"Authorization": "[Redacted]"}, {"accept": "json"}],
    }
    assert event["after"] == {
        "label": "OpenAI production",
        "apiKey": "[Redacted]",
        "password_hash": "[Redacted]",
        "totp_secret": "[Redacted]",
        "recovery_codes": "[Redacted]",
        "session_token": "[Redacted]",
        "private-key": "[Redacted]",
    }


async def test_redaction_happens_before_the_values_reach_the_database(
    app: FastAPI, owner: SignedUpMember
) -> None:
    # No API surface shows the stored row, so this one test reads it directly.
    await record_event(
        app,
        owner.organisation_id,
        actor_id=owner.member_id,
        action="credential.created",
        after={"api_key": "sk-never-stored"},
    )

    async with _sessions(app)() as session:
        stored = await session.scalar(
            text("SELECT after::text FROM audit_events WHERE organisation_id = :o AND action = :a"),
            {"o": owner.organisation_id, "a": "credential.created"},
        )

    assert stored is not None
    assert "sk-never-stored" not in stored
    assert '"[Redacted]"' in stored


async def test_audit_events_cannot_be_changed_or_removed(
    app: FastAPI, owner: SignedUpMember
) -> None:
    # Append-only is a database guarantee, so it is checked at the database.
    for statement in (
        "UPDATE audit_events SET action = 'tampered' WHERE organisation_id = :o",
        "DELETE FROM audit_events WHERE organisation_id = :o",
        "TRUNCATE audit_events",
    ):
        async with _sessions(app)() as session:
            with pytest.raises(DBAPIError, match="append-only"):
                await session.execute(text(statement), {"o": owner.organisation_id})

    (event,) = (await _list(owner)).json()["items"]
    assert event["action"] == "organisation.created"


async def test_owners_filter_by_actor_action_and_date_range(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    colleague = await tenant_factory()
    await add_member(app, colleague, owner.organisation_id, Role.OWNER)
    day = datetime(2026, 6, 1, tzinfo=UTC)
    for actor, action, at in [
        (owner, "member.invited", day),
        (colleague, "member.invited", day + timedelta(days=1)),
        (colleague, "member.removed", day + timedelta(days=2)),
        (owner, "member.removed", day + timedelta(days=3)),
    ]:
        await record_event(
            app, owner.organisation_id, actor_id=actor.member_id, action=action, occurred_at=at
        )

    async def actions(**params: Any) -> list[tuple[str, str]]:
        response = await _list(owner, **params)
        assert response.status_code == 200, response.text
        return [(e["actor"]["email"], e["action"]) for e in response.json()["items"]]

    by_colleague = await actions(actor_id=colleague.member_id)
    assert by_colleague == [
        (colleague.email, "member.removed"),
        (colleague.email, "member.invited"),
    ]
    assert await actions(action="member.removed") == [
        (owner.email, "member.removed"),
        (colleague.email, "member.removed"),
    ]
    # start is inclusive and end exclusive, so whole days select cleanly.
    assert await actions(
        start=(day + timedelta(days=1)).isoformat(), end=(day + timedelta(days=3)).isoformat()
    ) == [(colleague.email, "member.removed"), (colleague.email, "member.invited")]
    assert await actions(
        actor_id=owner.member_id, action="member.invited", end=(day + timedelta(days=1)).isoformat()
    ) == [(owner.email, "member.invited")]


async def test_dates_without_a_time_zone_are_refused(owner: SignedUpMember) -> None:
    response = await _list(owner, start="2026-06-01T00:00:00")

    assert response.status_code == 422


async def test_events_are_paginated_newest_first(app: FastAPI, owner: SignedUpMember) -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    for minute in range(5):
        await record_event(
            app,
            owner.organisation_id,
            actor_id=owner.member_id,
            action=f"test.step_{minute}",
            occurred_at=start + timedelta(minutes=minute),
        )
    old = {"end": (start + timedelta(days=1)).isoformat()}

    pages = [(await _list(owner, page=n, page_size=2, **old)).json() for n in (1, 2, 3, 4)]

    assert [[e["action"] for e in p["items"]] for p in pages] == [
        ["test.step_4", "test.step_3"],
        ["test.step_2", "test.step_1"],
        ["test.step_0"],
        [],
    ]
    assert {(p["total"], p["page_size"]) for p in pages} == {(5, 2)}
    assert [p["page"] for p in pages] == [1, 2, 3, 4]
    # Everything, sign-up included, fits on the default page.
    everything = (await _list(owner)).json()
    assert (everything["total"], everything["page_size"], len(everything["items"])) == (6, 25, 6)


async def test_page_sizes_are_bounded(owner: SignedUpMember) -> None:
    for params in ({"page_size": 0}, {"page_size": 101}, {"page": 0}):
        assert (await _list(owner, **params)).status_code == 422
    assert (await _list(owner, page_size=100)).status_code == 200


async def test_editors_are_refused_the_audit_events(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    editor = await tenant_factory()
    await add_member(app, editor, owner.organisation_id, Role.EDITOR)

    response = await editor.client.get(_events_path(owner.organisation_id))

    assert response.status_code == 403
    assert response.json() == {"detail": "Only Owners can do this"}
    # The Editor still owns, and can audit, their own Organisation.
    assert (await _list(editor)).status_code == 200


async def test_an_organisation_sees_only_its_own_events(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    other = await tenant_factory()
    await record_event(app, other.organisation_id, actor_id=other.member_id, action="x.y")

    mine = (await _list(owner)).json()
    theirs = (await _list(other)).json()

    assert [e["target"]["id"] for e in mine["items"]] == [owner.organisation_id]
    assert {e["action"] for e in theirs["items"]} == {"organisation.created", "x.y"}
    # Filtering by an actor from another Organisation finds nothing here.
    assert (await _list(owner, actor_id=other.member_id)).json()["total"] == 0


async def test_a_failed_sign_up_records_nothing(
    app: FastAPI, owner: SignedUpMember, client: httpx.AsyncClient
) -> None:
    retry = {
        "name": "Someone",
        "email": owner.email,
        "password": "another long password",
        "organisation_name": f"Never created {uuid.uuid4()}",
    }

    assert (await client.post("/api/auth/sign-up", json=retry)).status_code == 409

    async with _sessions(app)() as session:
        count = await session.scalar(
            text("SELECT count(*) FROM audit_events WHERE after->>'name' = :n"),
            {"n": retry["organisation_name"]},
        )
    assert count == 0


async def test_owners_get_the_actors_and_actions_they_can_filter_by(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    colleague, other = await tenant_factory(), await tenant_factory()
    await add_member(app, colleague, owner.organisation_id, Role.OWNER)
    for actor_id, action in [
        (colleague.member_id, "member.invited"),
        (colleague.member_id, "member.invited"),
        (None, "member.locked_out"),
    ]:
        await record_event(app, owner.organisation_id, actor_id=actor_id, action=action)
    await record_event(app, other.organisation_id, actor_id=other.member_id, action="x.y")

    response = await owner.client.get(f"{_events_path(owner.organisation_id)}/facets")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["actions"] == ["member.invited", "member.locked_out", "organisation.created"]
    assert sorted(body["actors"], key=lambda actor: actor["email"]) == sorted(
        [
            {"id": owner.member_id, "name": owner.name, "email": owner.email},
            {"id": colleague.member_id, "name": colleague.name, "email": colleague.email},
        ],
        key=lambda actor: actor["email"],
    )


async def test_editors_are_refused_the_filter_options(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    editor = await tenant_factory()
    await add_member(app, editor, owner.organisation_id, Role.EDITOR)

    response = await editor.client.get(f"{_events_path(owner.organisation_id)}/facets")

    assert (response.status_code, response.json()) == (403, {"detail": "Only Owners can do this"})
