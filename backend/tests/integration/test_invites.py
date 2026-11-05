"""API seam: Owners invite people by email or link, and the invited person joins.

Everything is observed through the API: the invite answers, emails in the outbox, sessions,
memberships (``/api/auth/me``) and Audit Events. Only the stored token hash has no API
surface, so one test reads the ``invites`` table.
"""

import hashlib
import logging
import re
import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.mail.outbox import OutboxMailer
from app.mail.port import Email
from tests.conftest import (
    STUDIO_URL,
    TEST_DATABASE_URL,
    ClientFactory,
    ControllableClock,
    SignedUpMember,
    TenantFactory,
)

NEW_PASSWORD = "a long enough password 42"
OTHER_PASSWORD = "a different password 77"
INVALID_INVITE = {"detail": "This invite link is invalid or has expired."}
WEEK = timedelta(days=7)


def invites_path(organisation_id: str) -> str:
    return f"/api/organisations/{organisation_id}/invites"


def unique_email(prefix: str = "invited") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.test"


async def invite(
    owner: SignedUpMember, email: str, role: str = "editor", **extra: object
) -> httpx.Response:
    return await owner.client.post(
        invites_path(owner.organisation_id), json={"email": email, "role": role, **extra}
    )


async def invite_ok(
    owner: SignedUpMember, email: str, role: str = "editor", **extra: object
) -> Any:
    response = await invite(owner, email, role, **extra)
    assert response.status_code == 201, response.text
    return response.json()


def token_from(text: str) -> str:
    match = re.search(re.escape(STUDIO_URL) + r"/accept-invite\?token=([\w-]+)", text)
    assert match is not None, text
    return match.group(1)


async def look_up(client: httpx.AsyncClient, token: str) -> httpx.Response:
    return await client.post("/api/invites/lookup", json={"token": token})


async def sign_up_with(
    client: httpx.AsyncClient, token: str, name: str = "New Person", password: str = NEW_PASSWORD
) -> httpx.Response:
    return await client.post(
        "/api/invites/sign-up", json={"token": token, "name": name, "password": password}
    )


async def accept(client: httpx.AsyncClient, token: str) -> httpx.Response:
    return await client.post("/api/invites/accept", json={"token": token})


async def pending(owner: SignedUpMember) -> list[dict[str, Any]]:
    response = await owner.client.get(invites_path(owner.organisation_id))
    assert response.status_code == 200, response.text
    result: list[dict[str, Any]] = response.json()
    return result


async def audit_events(owner: SignedUpMember, action: str) -> list[dict[str, Any]]:
    response = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/audit-events", params={"action": action}
    )
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


# Inviting


async def test_an_invited_person_without_an_account_creates_one_and_joins(
    owner: SignedUpMember, client: httpx.AsyncClient, outbox: OutboxMailer
) -> None:
    email = unique_email("New.Person")

    body = await invite_ok(owner, email.upper())

    assert body["email_sent"] is True
    assert body["invite"]["email"] == email.lower()
    assert body["invite"]["role"] == "editor"
    assert body["invite"]["invited_by"] == {
        "id": owner.member_id,
        "name": owner.name,
        "email": owner.email,
    }
    (message,) = outbox.sent
    assert message.to == email.lower()
    assert message.subject == f"Join {owner.organisation_name} on RAG Agent Studio"
    assert f"{owner.name} has invited you to join {owner.organisation_name}" in message.text
    assert "as an Editor" in message.text
    assert "expires in 7 days" in message.text
    token = token_from(message.text)
    assert token_from(body["link"]) == token

    joined = await sign_up_with(client, token)

    assert joined.status_code == 201, joined.text
    session = joined.json()
    assert session["member"]["email"] == email.lower()
    assert session["member"]["name"] == "New Person"
    assert session["organisations"] == [
        {"id": owner.organisation_id, "name": owner.organisation_name, "role": "editor"}
    ]
    assert (await client.get("/api/auth/me")).json() == session
    signed_in = await client.post(
        "/api/auth/sign-in", json={"email": email.upper(), "password": NEW_PASSWORD}
    )
    assert signed_in.status_code == 200


async def test_an_existing_member_accepts_and_gains_the_membership(
    owner: SignedUpMember,
    tenant_factory: TenantFactory,
    new_client: ClientFactory,
    outbox: OutboxMailer,
) -> None:
    colleague = await tenant_factory()
    old_cookie = colleague.client.cookies["studio_session"]
    body = await invite_ok(owner, colleague.email, role="owner")
    assert "as an Owner" in outbox.sent[-1].text

    accepted = await accept(colleague.client, token_from(body["link"]))

    assert accepted.status_code == 200, accepted.text
    organisations = {o["id"]: o for o in accepted.json()["organisations"]}
    assert organisations == {
        colleague.organisation_id: {
            "id": colleague.organisation_id,
            "name": colleague.organisation_name,
            "role": "owner",
        },
        owner.organisation_id: {
            "id": owner.organisation_id,
            "name": owner.organisation_name,
            "role": "owner",
        },
    }
    joined = await colleague.client.get(f"/api/organisations/{owner.organisation_id}")
    assert joined.json()["role"] == "owner"
    # A new privilege, so the session is rotated: the old cookie no longer works.
    assert colleague.client.cookies["studio_session"] != old_cookie
    replay = await new_client()
    replay.cookies.set("studio_session", old_cookie)
    assert (await replay.get("/api/auth/me")).status_code == 401


async def test_a_copyable_link_works_without_sending_email(
    owner: SignedUpMember, client: httpx.AsyncClient, outbox: OutboxMailer
) -> None:
    body = await invite_ok(owner, unique_email(), send_email=False)

    assert body["email_sent"] is False
    assert outbox.sent == []
    assert (await sign_up_with(client, token_from(body["link"]))).status_code == 201


class _BrokenMailer:
    async def send(self, email: Email) -> None:
        raise ConnectionRefusedError("mail server down")


async def test_a_failed_invite_email_still_gives_the_owner_a_link(
    app: FastAPI, owner: SignedUpMember, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    app.state.mailer = _BrokenMailer()
    email = unique_email()

    with caplog.at_level(logging.ERROR):
        body = await invite_ok(owner, email)

    assert body["email_sent"] is False
    assert "Sending an invite email failed" in caplog.text
    assert [i["email"] for i in await pending(owner)] == [email]
    assert (await sign_up_with(client, token_from(body["link"]))).status_code == 201


async def test_inviting_someone_who_already_belongs_is_refused(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    colleague = await tenant_factory()
    assert (
        await accept(
            colleague.client, token_from((await invite_ok(owner, colleague.email))["link"])
        )
    ).status_code == 200

    again = await invite(owner, colleague.email.upper())
    myself = await invite(owner, owner.email)

    assert again.status_code == myself.status_code == 409
    assert again.json() == {"detail": "That person is already a Member of this Organisation"}


async def test_an_email_has_one_pending_invite_at_a_time(owner: SignedUpMember) -> None:
    email = unique_email()
    first = await invite_ok(owner, email)

    duplicate = await invite(owner, email, role="owner")

    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "detail": "That email already has a pending invite. Copy a new link or revoke it."
    }
    revoked = await owner.client.delete(
        f"{invites_path(owner.organisation_id)}/{first['invite']['id']}"
    )
    assert revoked.status_code == 204
    assert (await invite(owner, email, role="owner")).status_code == 201


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-email", "role": "editor"},
        {"email": "someone@example.test", "role": "admin"},
        {"email": "someone@example.test"},
    ],
    ids=["bad email", "unknown role", "no role"],
)
async def test_invites_need_a_valid_email_and_role(
    owner: SignedUpMember, body: dict[str, str]
) -> None:
    response = await owner.client.post(invites_path(owner.organisation_id), json=body)

    assert response.status_code == 422


# Tokens: single use, hashed, expiring, revocable


async def test_an_invite_link_works_only_once(
    owner: SignedUpMember, new_client: ClientFactory
) -> None:
    token = token_from((await invite_ok(owner, unique_email()))["link"])
    assert (await sign_up_with(await new_client(), token)).status_code == 201

    again = await sign_up_with(await new_client(), token, name="Someone Else")
    looked_up = await look_up(await new_client(), token)

    assert (again.status_code, again.json()) == (400, INVALID_INVITE)
    assert (looked_up.status_code, looked_up.json()) == (404, INVALID_INVITE)
    assert await pending(owner) == []


async def test_invite_tokens_are_stored_only_as_hashes(owner: SignedUpMember) -> None:
    body = await invite_ok(owner, unique_email())
    token = token_from(body["link"])

    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT invites::text AS everything, token_hash FROM invites WHERE id = :id"
                    ),
                    {"id": body["invite"]["id"]},
                )
            ).one()
    finally:
        await engine.dispose()

    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in row.everything


async def test_an_invite_expires_after_seven_days(
    owner: SignedUpMember, new_client: ClientFactory, clock: ControllableClock
) -> None:
    token = token_from((await invite_ok(owner, unique_email()))["link"])
    clock.advance(WEEK - timedelta(seconds=1))
    assert (await look_up(await new_client(), token)).status_code == 200
    (listed,) = await pending(owner)
    assert listed["expired"] is False

    clock.advance(timedelta(seconds=1))

    looked_up = await look_up(await new_client(), token)
    joined = await sign_up_with(await new_client(), token)
    assert (looked_up.status_code, looked_up.json()) == (404, INVALID_INVITE)
    assert (joined.status_code, joined.json()) == (400, INVALID_INVITE)
    # Still listed, marked expired, so the Owner can renew or revoke it.
    (listed,) = await pending(owner)
    assert listed["expired"] is True


async def test_an_existing_member_cannot_accept_an_expired_invite(
    owner: SignedUpMember, tenant_factory: TenantFactory, clock: ControllableClock
) -> None:
    colleague = await tenant_factory()
    token = token_from((await invite_ok(owner, colleague.email))["link"])
    clock.advance(WEEK)

    response = await accept(colleague.client, token)

    assert (response.status_code, response.json()) == (400, INVALID_INVITE)
    assert len((await colleague.client.get("/api/auth/me")).json()["organisations"]) == 1


async def test_owners_revoke_a_pending_invite(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    colleague = await tenant_factory()
    body = await invite_ok(owner, colleague.email)
    path = f"{invites_path(owner.organisation_id)}/{body['invite']['id']}"

    revoked = await owner.client.delete(path)

    assert revoked.status_code == 204
    assert await pending(owner) == []
    refused = await accept(colleague.client, token_from(body["link"]))
    assert (refused.status_code, refused.json()) == (400, INVALID_INVITE)
    again = await owner.client.delete(path)
    assert (again.status_code, again.json()) == (404, {"detail": "Not found"})


async def test_an_accepted_invite_can_no_longer_be_revoked_or_renewed(
    owner: SignedUpMember, client: httpx.AsyncClient
) -> None:
    body = await invite_ok(owner, unique_email())
    assert (await sign_up_with(client, token_from(body["link"]))).status_code == 201
    path = f"{invites_path(owner.organisation_id)}/{body['invite']['id']}"

    assert (await owner.client.delete(path)).status_code == 404
    assert (await owner.client.post(f"{path}/renew", json={})).status_code == 404


async def test_renewing_an_invite_replaces_its_link_and_expiry(
    owner: SignedUpMember,
    new_client: ClientFactory,
    clock: ControllableClock,
    outbox: OutboxMailer,
) -> None:
    email = unique_email()
    body = await invite_ok(owner, email)
    clock.advance(WEEK + timedelta(days=1))

    renewed = await owner.client.post(
        f"{invites_path(owner.organisation_id)}/{body['invite']['id']}/renew", json={}
    )

    assert renewed.status_code == 200, renewed.text
    fresh = renewed.json()
    assert fresh["email_sent"] is False
    assert len(outbox.sent) == 1
    assert fresh["invite"]["id"] == body["invite"]["id"]
    assert fresh["invite"]["expired"] is False
    new_token = token_from(fresh["link"])
    assert new_token != token_from(body["link"])
    assert (await look_up(await new_client(), token_from(body["link"]))).status_code == 404
    assert (await look_up(await new_client(), new_token)).status_code == 200
    (listed,) = await pending(owner)
    assert listed["expired"] is False

    emailed = await owner.client.post(
        f"{invites_path(owner.organisation_id)}/{body['invite']['id']}/renew",
        json={"send_email": True},
    )

    assert emailed.json()["email_sent"] is True
    assert outbox.sent[-1].to == email
    assert token_from(outbox.sent[-1].text) == token_from(emailed.json()["link"])
    assert (await look_up(await new_client(), new_token)).status_code == 404


# Accepting


async def test_the_invite_lookup_says_what_the_link_offers(
    owner: SignedUpMember, tenant_factory: TenantFactory, client: httpx.AsyncClient
) -> None:
    colleague = await tenant_factory()
    for_newcomer = token_from((await invite_ok(owner, unique_email("newcomer")))["link"])
    for_colleague = token_from((await invite_ok(owner, colleague.email, role="owner"))["link"])

    newcomer = await look_up(client, for_newcomer)
    existing = await look_up(client, for_colleague)

    assert newcomer.status_code == 200
    assert newcomer.json() == {
        "organisation_id": owner.organisation_id,
        "organisation_name": owner.organisation_name,
        "email": newcomer.json()["email"],
        "role": "editor",
        "invited_by_name": owner.name,
        "account_exists": False,
    }
    assert newcomer.json()["email"].startswith("newcomer-")
    assert existing.json()["account_exists"] is True
    assert existing.json()["role"] == "owner"
    unknown = await look_up(client, "not-a-real-token")
    assert (unknown.status_code, unknown.json()) == (404, INVALID_INVITE)


async def test_an_invite_for_another_email_is_refused_and_stays_usable(
    owner: SignedUpMember, tenant_factory: TenantFactory, new_client: ClientFactory
) -> None:
    bystander = await tenant_factory()
    email = unique_email()
    token = token_from((await invite_ok(owner, email))["link"])

    refused = await accept(bystander.client, token)

    assert refused.status_code == 403
    assert refused.json() == {
        "detail": f"This invite is for {email}. Sign in with that email to accept it."
    }
    assert len((await bystander.client.get("/api/auth/me")).json()["organisations"]) == 1
    assert (await sign_up_with(await new_client(), token)).status_code == 201


async def test_accepting_as_an_existing_member_needs_a_session(
    owner: SignedUpMember, client: httpx.AsyncClient
) -> None:
    token = token_from((await invite_ok(owner, unique_email()))["link"])

    response = await accept(client, token)

    assert response.status_code == 401
    assert (await look_up(client, token)).status_code == 200


async def test_creating_an_account_for_an_email_that_has_one_is_refused(
    owner: SignedUpMember, tenant_factory: TenantFactory, client: httpx.AsyncClient
) -> None:
    colleague = await tenant_factory()
    token = token_from((await invite_ok(owner, colleague.email))["link"])

    response = await sign_up_with(client, token, password=OTHER_PASSWORD)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "An account with this email already exists. Sign in to accept the invite."
    }
    # The existing account is untouched and can still accept.
    assert (await accept(colleague.client, token)).status_code == 200


@pytest.mark.parametrize(
    ("name", "password"),
    [("", NEW_PASSWORD), ("New Person", "too short")],
    ids=["no name", "short password"],
)
async def test_a_new_account_needs_a_name_and_a_long_enough_password(
    owner: SignedUpMember, client: httpx.AsyncClient, name: str, password: str
) -> None:
    token = token_from((await invite_ok(owner, unique_email()))["link"])

    response = await sign_up_with(client, token, name=name, password=password)

    assert response.status_code == 422
    assert (await look_up(client, token)).status_code == 200


# Pending invites list


async def test_owners_list_pending_invites_newest_first(
    owner: SignedUpMember, client: httpx.AsyncClient
) -> None:
    older, accepted, revoked, newer = (
        unique_email(n) for n in ("older", "accepted", "revoked", "newer")
    )
    await invite_ok(owner, older)
    accepted_body = await invite_ok(owner, accepted, role="owner")
    revoked_body = await invite_ok(owner, revoked)
    await invite_ok(owner, newer, role="owner")
    await sign_up_with(client, token_from(accepted_body["link"]))
    await owner.client.delete(
        f"{invites_path(owner.organisation_id)}/{revoked_body['invite']['id']}"
    )

    listed = await pending(owner)

    assert [(i["email"], i["role"]) for i in listed] == [(newer, "owner"), (older, "editor")]
    assert all(i["invited_by"]["id"] == owner.member_id for i in listed)
    assert all(i["expired"] is False for i in listed)


async def test_an_organisation_lists_only_its_own_invites(tenant_factory: TenantFactory) -> None:
    first, second = await tenant_factory(), await tenant_factory()
    email = unique_email()
    await invite_ok(first, email)

    assert await pending(second) == []
    # The same email can be invited to two Organisations.
    await invite_ok(second, email)
    assert [i["email"] for i in await pending(second)] == [email]


async def test_editors_cannot_manage_invites(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    editor = await tenant_factory()
    assert (
        await accept(editor.client, token_from((await invite_ok(owner, editor.email))["link"]))
    ).status_code == 200
    pending_id = (await invite_ok(owner, unique_email()))["invite"]["id"]
    path = invites_path(owner.organisation_id)

    responses = [
        await editor.client.get(path),
        await editor.client.post(path, json={"email": unique_email(), "role": "owner"}),
        await editor.client.delete(f"{path}/{pending_id}"),
        await editor.client.post(f"{path}/{pending_id}/renew", json={}),
    ]

    assert [r.status_code for r in responses] == [403, 403, 403, 403]
    assert {r.json()["detail"] for r in responses} == {"Only Owners can do this"}
    assert len(await pending(owner)) == 1


# Audit Events


async def test_invite_accept_revoke_and_renew_are_audit_events(
    owner: SignedUpMember, client: httpx.AsyncClient
) -> None:
    accepted_email, revoked_email = unique_email("joins"), unique_email("revoked")
    accepted_body = await invite_ok(owner, accepted_email)
    revoked_body = await invite_ok(owner, revoked_email, role="owner")
    renewed = await owner.client.post(
        f"{invites_path(owner.organisation_id)}/{accepted_body['invite']['id']}/renew", json={}
    )
    joined = await sign_up_with(client, token_from(renewed.json()["link"]), name="Joiner")
    await owner.client.delete(
        f"{invites_path(owner.organisation_id)}/{revoked_body['invite']['id']}"
    )
    owner_actor = {"id": owner.member_id, "name": owner.name, "email": owner.email}
    joiner = joined.json()["member"]

    created = await audit_events(owner, "invite.created")
    (renew_event,) = await audit_events(owner, "invite.renewed")
    (accept_event,) = await audit_events(owner, "invite.accepted")
    (revoke_event,) = await audit_events(owner, "invite.revoked")

    assert [(e["actor"], e["target"], e["before"], e["after"]) for e in created] == [
        (
            owner_actor,
            {"type": "invite", "id": revoked_body["invite"]["id"]},
            None,
            {"email": revoked_email, "role": "owner"},
        ),
        (
            owner_actor,
            {"type": "invite", "id": accepted_body["invite"]["id"]},
            None,
            {"email": accepted_email, "role": "editor"},
        ),
    ]
    assert renew_event["actor"] == owner_actor
    assert renew_event["after"] == {"email": accepted_email, "role": "editor"}
    assert accept_event["actor"] == {"id": joiner["id"], "name": "Joiner", "email": accepted_email}
    assert accept_event["target"] == {"type": "invite", "id": accepted_body["invite"]["id"]}
    assert accept_event["after"] == {
        "email": accepted_email,
        "role": "editor",
        "member_id": joiner["id"],
    }
    assert revoke_event["actor"] == owner_actor
    assert revoke_event["target"] == {"type": "invite", "id": revoked_body["invite"]["id"]}
    assert revoke_event["before"] == {"email": revoked_email, "role": "owner"}
    assert revoke_event["after"] is None


async def test_refused_invite_actions_record_nothing(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    bystander = await tenant_factory()
    token = token_from((await invite_ok(owner, unique_email()))["link"])
    await invite(owner, owner.email)
    await accept(bystander.client, token)
    await owner.client.delete(f"{invites_path(owner.organisation_id)}/{uuid.uuid4()}")

    assert len(await audit_events(owner, "invite.created")) == 1
    assert await audit_events(owner, "invite.accepted") == []
    assert await audit_events(owner, "invite.revoked") == []


@pytest.mark.parametrize(("seconds", "wording"), [(24 * 60 * 60, "1 day"), (90 * 60, "90 minutes")])
async def test_the_invite_lifetime_follows_the_setting(
    app: FastAPI,
    owner: SignedUpMember,
    client: httpx.AsyncClient,
    clock: ControllableClock,
    outbox: OutboxMailer,
    seconds: int,
    wording: str,
) -> None:
    app.state.settings = app.state.settings.model_copy(update={"invite_ttl_seconds": seconds})

    token = token_from((await invite_ok(owner, unique_email()))["link"])

    assert f"expires in {wording}." in outbox.sent[-1].text
    clock.advance(timedelta(seconds=seconds - 1))
    assert (await look_up(client, token)).status_code == 200
    clock.advance(timedelta(seconds=1))
    assert (await look_up(client, token)).status_code == 404
