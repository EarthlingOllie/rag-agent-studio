"""TOTP MFA at the API seam: enrolment, the sign-in challenge, recovery codes and disabling.

Audit Events have no list endpoint until ticket 01-05, so ``_audit_actions`` reads the
``audit_events`` table directly; that is the only place these tests look below the API.
"""

import asyncio
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import select, text

from app.audit.models import AuditEvent
from app.core.clock import ControllableClock
from app.main import create_app
from tests.conftest import (
    BASE_URL,
    ClientFactory,
    SignedUpMember,
    TenantFactory,
    new_member_details,
)
from tests.totp import hotp, totp

CODE_INCORRECT = {"detail": "Code is incorrect"}
SIGN_IN_AGAIN = {"detail": "Sign in again"}


def test_the_test_totp_generator_matches_rfc_6238() -> None:
    # RFC 6238 appendix B, SHA-1, T = 59 s: 94287082; six digits are its last six.
    assert hotp(b"12345678901234567890", 59 // 30) == "287082"


async def _start_enrolment(member: SignedUpMember) -> dict[str, Any]:
    response = await member.client.post("/api/auth/mfa/enrolment")
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def _enrol(member: SignedUpMember, clock: ControllableClock) -> tuple[str, list[str]]:
    """Enrols the Member; returns the TOTP secret and the recovery codes."""
    secret = (await _start_enrolment(member))["secret"]
    response = await member.client.post(
        "/api/auth/mfa/enrolment/confirm", json={"code": totp(secret, clock.now())}
    )
    assert response.status_code == 200, response.text
    codes: list[str] = response.json()["recovery_codes"]
    # Later codes in the test must come from a later step than the confirming one.
    clock.advance(timedelta(seconds=30))
    return secret, codes


async def _password_step(
    new_client: ClientFactory, member: SignedUpMember
) -> tuple[httpx.AsyncClient, httpx.Response]:
    client = await new_client()
    response = await client.post(
        "/api/auth/sign-in", json={"email": member.email, "password": member.password}
    )
    return client, response


async def _audit_actions(app: FastAPI, member: SignedUpMember) -> list[tuple[str, Any, Any]]:
    async with app.state.sessionmaker() as session:
        rows = await session.execute(
            select(AuditEvent.action, AuditEvent.before, AuditEvent.after)
            .where(
                AuditEvent.actor_member_id == uuid.UUID(member.member_id),
                AuditEvent.organisation_id == uuid.UUID(member.organisation_id),
                AuditEvent.action.like("mfa.%"),
            )
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
        return [tuple(row) for row in rows]


async def test_a_new_member_has_mfa_off(owner: SignedUpMember) -> None:
    response = await owner.client.get("/api/auth/mfa")

    assert response.status_code == 200
    assert response.json() == {"enabled": False, "recovery_codes_remaining": 0}


async def test_mfa_routes_need_a_signed_in_member(client: httpx.AsyncClient) -> None:
    for method, path in [
        ("GET", "/api/auth/mfa"),
        ("POST", "/api/auth/mfa/enrolment"),
        ("POST", "/api/auth/mfa/enrolment/confirm"),
        ("POST", "/api/auth/mfa/disable"),
        ("POST", "/api/auth/mfa/recovery-codes"),
    ]:
        response = await client.request(method, path, json={"code": "123456", "password": "x"})
        assert response.status_code == 401, (method, path)


async def test_enrolment_shows_a_qr_code_for_an_otpauth_uri(owner: SignedUpMember) -> None:
    enrolment = await _start_enrolment(owner)

    assert re.fullmatch(r"[A-Z2-7]{32}", enrolment["secret"])
    uri = urlparse(enrolment["otpauth_uri"])
    assert (uri.scheme, uri.netloc) == ("otpauth", "totp")
    assert uri.path == f"/RAG%20Agent%20Studio:{owner.email.replace('@', '%40')}"
    query = parse_qs(uri.query)
    assert query["secret"] == [enrolment["secret"]]
    assert query["issuer"] == ["RAG Agent Studio"]
    qr_code = unquote(enrolment["qr_code"])
    assert qr_code.startswith("data:image/svg+xml;charset=utf-8,<svg")
    assert "<path" in qr_code
    # Not enabled until a code confirms the authenticator has the secret.
    assert (await owner.client.get("/api/auth/mfa")).json()["enabled"] is False


async def test_enrolment_needs_a_confirming_code(
    owner: SignedUpMember, clock: ControllableClock, new_client: ClientFactory
) -> None:
    secret = (await _start_enrolment(owner))["secret"]

    wrong = await owner.client.post(
        "/api/auth/mfa/enrolment/confirm", json={"code": totp(secret, clock.now(), step_offset=5)}
    )

    assert wrong.status_code == 400
    assert wrong.json() == CODE_INCORRECT
    assert (await owner.client.get("/api/auth/mfa")).json()["enabled"] is False
    _, sign_in = await _password_step(new_client, owner)
    assert sign_in.status_code == 200

    right = await owner.client.post(
        "/api/auth/mfa/enrolment/confirm", json={"code": totp(secret, clock.now())}
    )

    assert right.status_code == 200
    assert (await owner.client.get("/api/auth/mfa")).json() == {
        "enabled": True,
        "recovery_codes_remaining": 10,
    }


async def test_confirming_without_starting_enrolment_is_refused(owner: SignedUpMember) -> None:
    response = await owner.client.post("/api/auth/mfa/enrolment/confirm", json={"code": "123456"})

    assert response.status_code == 409
    assert response.json() == {"detail": "Start enrolment first"}


async def test_starting_enrolment_again_replaces_the_unconfirmed_secret(
    owner: SignedUpMember, clock: ControllableClock
) -> None:
    first = (await _start_enrolment(owner))["secret"]
    second = (await _start_enrolment(owner))["secret"]

    stale = await owner.client.post(
        "/api/auth/mfa/enrolment/confirm", json={"code": totp(first, clock.now())}
    )
    fresh = await owner.client.post(
        "/api/auth/mfa/enrolment/confirm", json={"code": totp(second, clock.now())}
    )

    assert first != second
    assert stale.status_code == 400
    assert fresh.status_code == 200


async def test_enrolling_twice_is_refused(owner: SignedUpMember, clock: ControllableClock) -> None:
    await _enrol(owner, clock)

    again = await owner.client.post("/api/auth/mfa/enrolment")
    confirm = await owner.client.post("/api/auth/mfa/enrolment/confirm", json={"code": "123456"})

    assert again.status_code == 409
    assert again.json() == {"detail": "MFA is already enabled"}
    assert confirm.status_code == 409
    assert confirm.json() == {"detail": "MFA is already enabled"}


async def test_ten_single_use_recovery_codes_are_shown_once(
    owner: SignedUpMember, clock: ControllableClock
) -> None:
    _, codes = await _enrol(owner, clock)

    assert len(codes) == 10
    assert len(set(codes)) == 10
    for code in codes:
        assert re.fullmatch(r"[A-Z2-7]{4}-[A-Z2-7]{4}-[A-Z2-7]{4}-[A-Z2-7]{4}", code)
    # Nothing shows them again: the status only counts them.
    status = await owner.client.get("/api/auth/mfa")
    assert codes[0] not in status.text
    assert status.json() == {"enabled": True, "recovery_codes_remaining": 10}


async def test_recovery_codes_and_the_totp_secret_are_not_stored_in_the_clear(
    owner: SignedUpMember, clock: ControllableClock, app: FastAPI
) -> None:
    secret, codes = await _enrol(owner, clock)

    async with app.state.sessionmaker() as session:
        stored_codes = (
            await session.execute(
                text("SELECT code_hash FROM mfa_recovery_codes WHERE member_id = :id"),
                {"id": owner.member_id},
            )
        ).scalars()
        sealed = await session.scalar(
            text("SELECT secret_sealed FROM mfa_factors WHERE member_id = :id"),
            {"id": owner.member_id},
        )
    hashes = list(stored_codes)
    assert len(hashes) == 10
    for code in codes:
        assert code not in hashes
        assert code.replace("-", "") not in hashes
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes)
    assert secret.encode() not in sealed
    assert sealed[0] == 1  # envelope format version


async def test_sign_in_for_an_mfa_member_is_pending_until_a_code_is_given(
    owner: SignedUpMember, clock: ControllableClock, new_client: ClientFactory
) -> None:
    secret, _ = await _enrol(owner, clock)

    client, response = await _password_step(new_client, owner)

    assert response.status_code == 202
    assert response.json() == {"mfa_required": True}
    assert "studio_session" not in response.cookies
    pending_cookie = response.headers["set-cookie"]
    assert pending_cookie.startswith("studio_mfa_pending=")
    for attribute in ("HttpOnly", "Secure", "SameSite=lax", "Max-Age=300", "Path=/api/auth"):
        assert attribute in pending_cookie
    # MFA pending is not a session.
    assert (await client.get("/api/auth/me")).status_code == 401

    verified = await client.post("/api/auth/mfa/verify", json={"code": totp(secret, clock.now())})

    assert verified.status_code == 200
    assert verified.json()["member"]["id"] == owner.member_id
    assert "studio_session" in verified.cookies
    assert (await client.get("/api/auth/me")).status_code == 200
    # The pending state is used up.
    assert "studio_mfa_pending" not in client.cookies


@pytest.mark.parametrize(("offset", "accepted"), [(-2, False), (-1, True), (1, True), (2, False)])
async def test_codes_one_step_either_side_are_accepted(
    owner: SignedUpMember,
    clock: ControllableClock,
    new_client: ClientFactory,
    offset: int,
    accepted: bool,
) -> None:
    secret, _ = await _enrol(owner, clock)
    # Move two steps past the confirming code, so even step - 2 is unused: only the window
    # can refuse it.
    clock.advance(timedelta(seconds=60))
    client, _ = await _password_step(new_client, owner)

    response = await client.post(
        "/api/auth/mfa/verify", json={"code": totp(secret, clock.now(), step_offset=offset)}
    )

    assert response.status_code == (200 if accepted else 400)


async def test_a_wrong_code_keeps_the_sign_in_pending(
    owner: SignedUpMember, clock: ControllableClock, new_client: ClientFactory
) -> None:
    secret, _ = await _enrol(owner, clock)
    client, _ = await _password_step(new_client, owner)

    wrong = await client.post(
        "/api/auth/mfa/verify", json={"code": totp(secret, clock.now(), step_offset=9)}
    )
    right = await client.post("/api/auth/mfa/verify", json={"code": totp(secret, clock.now())})

    assert wrong.status_code == 400
    assert wrong.json() == CODE_INCORRECT
    assert "studio_session" not in wrong.cookies
    assert right.status_code == 200


async def test_a_code_cannot_be_used_twice(
    owner: SignedUpMember, clock: ControllableClock, new_client: ClientFactory
) -> None:
    secret, _ = await _enrol(owner, clock)
    code = totp(secret, clock.now())
    first, _ = await _password_step(new_client, owner)
    assert (await first.post("/api/auth/mfa/verify", json={"code": code})).status_code == 200

    second, _ = await _password_step(new_client, owner)
    replay = await second.post("/api/auth/mfa/verify", json={"code": code})

    assert replay.status_code == 400
    assert replay.json() == CODE_INCORRECT


async def test_five_wrong_codes_end_the_pending_sign_in(
    owner: SignedUpMember, clock: ControllableClock, new_client: ClientFactory
) -> None:
    secret, _ = await _enrol(owner, clock)
    client, _ = await _password_step(new_client, owner)
    for _ in range(5):
        wrong = await client.post("/api/auth/mfa/verify", json={"code": "000000"})
        assert wrong.status_code == 400

    right = await client.post("/api/auth/mfa/verify", json={"code": totp(secret, clock.now())})

    assert right.status_code == 401
    assert right.json() == SIGN_IN_AGAIN


async def test_verify_without_a_pending_sign_in_asks_to_sign_in_again(
    client: httpx.AsyncClient,
) -> None:
    missing = await client.post("/api/auth/mfa/verify", json={"code": "123456"})
    client.cookies.set("studio_mfa_pending", "made-up", domain="testserver", path="/api/auth")
    forged = await client.post("/api/auth/mfa/verify", json={"code": "123456"})

    assert missing.status_code == 401
    assert missing.json() == SIGN_IN_AGAIN
    assert forged.status_code == 401
    assert forged.json() == SIGN_IN_AGAIN


async def test_a_recovery_code_completes_sign_in_once(
    owner: SignedUpMember, clock: ControllableClock, new_client: ClientFactory, app: FastAPI
) -> None:
    _, codes = await _enrol(owner, clock)
    client, _ = await _password_step(new_client, owner)

    # Typed loosely: lower case, without dashes, with spaces around.
    used = await client.post(
        "/api/auth/mfa/verify", json={"code": f" {codes[3].replace('-', '').lower()} "}
    )

    assert used.status_code == 200
    assert (await client.get("/api/auth/mfa")).json() == {
        "enabled": True,
        "recovery_codes_remaining": 9,
    }
    again, _ = await _password_step(new_client, owner)
    reuse = await again.post("/api/auth/mfa/verify", json={"code": codes[3]})
    assert reuse.status_code == 400
    assert reuse.json() == CODE_INCORRECT
    assert (await _audit_actions(app, owner))[-1] == (
        "mfa.recovery_code_used",
        None,
        {"recovery_codes_remaining": 9},
    )


async def test_another_members_recovery_code_does_not_work(
    tenant_factory: TenantFactory, clock: ControllableClock, new_client: ClientFactory
) -> None:
    alice, bob = await tenant_factory(), await tenant_factory()
    await _enrol(alice, clock)
    _, bobs_codes = await _enrol(bob, clock)
    client, _ = await _password_step(new_client, alice)

    response = await client.post("/api/auth/mfa/verify", json={"code": bobs_codes[0]})

    assert response.status_code == 400


async def test_disabling_mfa_needs_the_password_and_a_code(
    owner: SignedUpMember, clock: ControllableClock, new_client: ClientFactory
) -> None:
    secret, _ = await _enrol(owner, clock)
    code = totp(secret, clock.now())

    attempts = [
        {"password": "not the password", "code": code},
        {"password": owner.password, "code": totp(secret, clock.now(), step_offset=7)},
    ]
    for attempt in attempts:
        refused = await owner.client.post("/api/auth/mfa/disable", json=attempt)
        assert refused.status_code == 400
        assert refused.json() == {"detail": "Password or code is incorrect"}
    assert (await owner.client.get("/api/auth/mfa")).json()["enabled"] is True

    disabled = await owner.client.post(
        "/api/auth/mfa/disable", json={"password": owner.password, "code": code}
    )

    assert disabled.status_code == 204
    assert (await owner.client.get("/api/auth/mfa")).json() == {
        "enabled": False,
        "recovery_codes_remaining": 0,
    }
    _, sign_in = await _password_step(new_client, owner)
    assert sign_in.status_code == 200


async def test_a_wrong_password_with_a_good_code_does_not_use_the_code(
    owner: SignedUpMember, clock: ControllableClock
) -> None:
    _, codes = await _enrol(owner, clock)

    await owner.client.post("/api/auth/mfa/disable", json={"password": "nope", "code": codes[0]})

    assert (await owner.client.get("/api/auth/mfa")).json()["recovery_codes_remaining"] == 10


async def test_a_recovery_code_can_disable_mfa(
    owner: SignedUpMember, clock: ControllableClock
) -> None:
    _, codes = await _enrol(owner, clock)

    response = await owner.client.post(
        "/api/auth/mfa/disable", json={"password": owner.password, "code": codes[0]}
    )

    assert response.status_code == 204


async def test_disabling_when_mfa_is_off_is_refused(owner: SignedUpMember) -> None:
    response = await owner.client.post(
        "/api/auth/mfa/disable", json={"password": owner.password, "code": "123456"}
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "MFA is not enabled"}


async def test_recovery_codes_can_be_replaced_with_a_code(
    owner: SignedUpMember, clock: ControllableClock, new_client: ClientFactory
) -> None:
    secret, old_codes = await _enrol(owner, clock)

    wrong = await owner.client.post("/api/auth/mfa/recovery-codes", json={"code": "000000"})
    response = await owner.client.post(
        "/api/auth/mfa/recovery-codes", json={"code": totp(secret, clock.now())}
    )

    assert wrong.status_code == 400
    assert wrong.json() == CODE_INCORRECT
    assert response.status_code == 200
    new_codes = response.json()["recovery_codes"]
    assert len(new_codes) == 10
    assert not set(new_codes) & set(old_codes)
    client, _ = await _password_step(new_client, owner)
    stale = await client.post("/api/auth/mfa/verify", json={"code": old_codes[0]})
    assert stale.status_code == 400
    fresh = await client.post("/api/auth/mfa/verify", json={"code": new_codes[0]})
    assert fresh.status_code == 200


async def test_replacing_recovery_codes_needs_mfa_on(owner: SignedUpMember) -> None:
    response = await owner.client.post("/api/auth/mfa/recovery-codes", json={"code": "123456"})

    assert response.status_code == 409
    assert response.json() == {"detail": "MFA is not enabled"}


async def test_enrolment_disabling_and_recovery_code_use_are_audit_events(
    owner: SignedUpMember, clock: ControllableClock, new_client: ClientFactory, app: FastAPI
) -> None:
    secret, codes = await _enrol(owner, clock)
    client, _ = await _password_step(new_client, owner)
    await client.post("/api/auth/mfa/verify", json={"code": codes[0]})
    await owner.client.post(
        "/api/auth/mfa/recovery-codes", json={"code": totp(secret, clock.now())}
    )
    clock.advance(timedelta(seconds=30))
    await owner.client.post(
        "/api/auth/mfa/disable",
        json={"password": owner.password, "code": totp(secret, clock.now())},
    )

    assert await _audit_actions(app, owner) == [
        ("mfa.enrolled", {"mfa_enabled": False}, {"mfa_enabled": True}),
        ("mfa.recovery_code_used", None, {"recovery_codes_remaining": 9}),
        ("mfa.recovery_codes_replaced", None, {"recovery_codes_remaining": 10}),
        ("mfa.disabled", {"mfa_enabled": True}, {"mfa_enabled": False}),
    ]


async def test_failed_attempts_record_no_audit_events(
    owner: SignedUpMember, clock: ControllableClock, app: FastAPI
) -> None:
    secret = (await _start_enrolment(owner))["secret"]
    await owner.client.post(
        "/api/auth/mfa/enrolment/confirm", json={"code": totp(secret, clock.now(), step_offset=4)}
    )

    assert await _audit_actions(app, owner) == []


async def test_audit_events_are_recorded_in_every_organisation_of_the_member(
    owner: SignedUpMember, clock: ControllableClock, app: FastAPI
) -> None:
    # A second Organisation for the same Member (invites arrive with 01-08).
    second_organisation = uuid.uuid4()
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(
            text("INSERT INTO organisations (id, name) VALUES (:id, 'Second')"),
            {"id": second_organisation},
        )
        await session.execute(
            text(
                "INSERT INTO memberships (id, organisation_id, member_id, role)"
                " VALUES (:id, :org, :member, 'editor')"
            ),
            {"id": uuid.uuid4(), "org": second_organisation, "member": owner.member_id},
        )

    await _enrol(owner, clock)

    async with app.state.sessionmaker() as session:
        organisations = set(
            (
                await session.execute(
                    select(AuditEvent.organisation_id).where(
                        AuditEvent.actor_member_id == uuid.UUID(owner.member_id),
                        AuditEvent.action == "mfa.enrolled",
                    )
                )
            ).scalars()
        )
    assert organisations == {uuid.UUID(owner.organisation_id), second_organisation}


async def test_the_audit_event_targets_the_member(
    owner: SignedUpMember, clock: ControllableClock, app: FastAPI
) -> None:
    await _enrol(owner, clock)

    async with app.state.sessionmaker() as session:
        event = await session.scalar(
            select(AuditEvent).where(AuditEvent.actor_member_id == uuid.UUID(owner.member_id))
        )
    assert event is not None
    assert (event.target_type, str(event.target_id)) == ("member", owner.member_id)


async def test_two_sign_ins_racing_with_one_code_let_only_one_in(
    owner: SignedUpMember, clock: ControllableClock, new_client: ClientFactory
) -> None:
    secret, _ = await _enrol(owner, clock)
    code = totp(secret, clock.now())
    first, _ = await _password_step(new_client, owner)
    second, _ = await _password_step(new_client, owner)

    responses = await asyncio.gather(
        first.post("/api/auth/mfa/verify", json={"code": code}),
        second.post("/api/auth/mfa/verify", json={"code": code}),
    )

    assert sorted(response.status_code for response in responses) == [200, 400]


async def test_something_that_is_neither_kind_of_code_is_incorrect(
    owner: SignedUpMember, clock: ControllableClock, new_client: ClientFactory
) -> None:
    await _enrol(owner, clock)
    client, _ = await _password_step(new_client, owner)

    response = await client.post("/api/auth/mfa/verify", json={"code": "not a code"})

    assert response.status_code == 400
    assert response.json() == CODE_INCORRECT


async def test_signing_in_again_on_a_signed_in_browser_ends_the_old_session_while_pending(
    owner: SignedUpMember, clock: ControllableClock
) -> None:
    await _enrol(owner, clock)
    old_session = owner.client.cookies["studio_session"]

    response = await owner.client.post(
        "/api/auth/sign-in", json={"email": owner.email, "password": owner.password}
    )

    assert response.status_code == 202
    assert "studio_session" not in owner.client.cookies
    owner.client.cookies.set("studio_session", old_session, domain="testserver")
    assert (await owner.client.get("/api/auth/me")).status_code == 401


async def test_if_mfa_is_turned_off_while_a_sign_in_is_pending_it_must_start_again(
    owner: SignedUpMember, clock: ControllableClock, new_client: ClientFactory
) -> None:
    secret, _ = await _enrol(owner, clock)
    client, _ = await _password_step(new_client, owner)
    await owner.client.post(
        "/api/auth/mfa/disable",
        json={"password": owner.password, "code": totp(secret, clock.now())},
    )

    response = await client.post("/api/auth/mfa/verify", json={"code": "123456"})
    again = await client.post("/api/auth/mfa/verify", json={"code": "123456"})

    assert response.status_code == 401
    assert response.json() == SIGN_IN_AGAIN
    assert again.json() == SIGN_IN_AGAIN


async def test_without_an_injected_clock_codes_follow_the_system_clock(
    owner: SignedUpMember,
) -> None:
    secret = (await _start_enrolment(owner))["secret"]

    response = await owner.client.post(
        "/api/auth/mfa/enrolment/confirm", json={"code": totp(secret, datetime.now(UTC))}
    )

    assert response.status_code == 200


async def test_a_pending_sign_in_expires(
    settings_env: pytest.MonkeyPatch, database_schema: None
) -> None:
    settings_env.setenv("MFA_PENDING_TTL_SECONDS", "1")
    application = create_app()
    async with (
        LifespanManager(application),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url=BASE_URL) as c,
    ):
        details = new_member_details()
        await c.post("/api/auth/sign-up", json=details)
        secret = (await c.post("/api/auth/mfa/enrolment")).json()["secret"]
        confirm = {"code": totp(secret, datetime.now(UTC))}
        assert (await c.post("/api/auth/mfa/enrolment/confirm", json=confirm)).status_code == 200
        credentials = {"email": details["email"], "password": details["password"]}
        sign_in = await c.post("/api/auth/sign-in", json=credentials)
        assert "Max-Age=1;" in sign_in.headers["set-cookie"]

        await asyncio.sleep(1.5)
        # The browser would have dropped the cookie; send it anyway to prove the server forgot it.
        c.cookies.set("studio_mfa_pending", sign_in.cookies["studio_mfa_pending"])
        response = await c.post(
            "/api/auth/mfa/verify", json={"code": totp(secret, datetime.now(UTC), step_offset=1)}
        )

    assert response.status_code == 401
    assert response.json() == SIGN_IN_AGAIN
