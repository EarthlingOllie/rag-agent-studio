"""The Require MFA policy at the API seam.

An Owner turns the policy on or off for their Organisation. While it is on, a Member without
MFA can still sign in and enrol, but every route of that Organisation answers 403 until they
do, and nobody can turn MFA off while any of their Organisations requires it. Policy changes
are Audit Events, read back through the Audit list endpoint.
"""

from datetime import timedelta
from typing import Any

import httpx
import pytest

from tests.conftest import (
    ClientFactory,
    MemberFactory,
    SignedUpMember,
    TenantFactory,
    join_organisation,
)
from tests.fakes.clock import ControllableClock
from tests.integration.test_tenant_isolation import ORGANISATION_SCOPED_ROUTES, ScopedRoute
from tests.totp import totp

MFA_REQUIRED = {
    "detail": "This Organisation requires MFA. Turn on MFA for your account to continue."
}
ENROL_FIRST = {"detail": "Turn on MFA for your own account before requiring it."}


def policy_path(organisation_id: str) -> str:
    return f"/api/organisations/{organisation_id}/mfa-policy"


async def enrol(member: SignedUpMember, clock: ControllableClock) -> str:
    """Turns MFA on for the Member; returns the TOTP secret."""
    started = await member.client.post("/api/auth/mfa/enrolment")
    assert started.status_code == 201, started.text
    secret: str = started.json()["secret"]
    confirmed = await member.client.post(
        "/api/auth/mfa/enrolment/confirm", json={"code": totp(secret, clock.now())}
    )
    assert confirmed.status_code == 200, confirmed.text
    # A later code must come from a later step than the confirming one.
    clock.advance(timedelta(seconds=30))
    return secret


async def set_policy(owner: SignedUpMember, require_mfa: bool) -> httpx.Response:
    return await owner.client.put(
        policy_path(owner.organisation_id), json={"require_mfa": require_mfa}
    )


async def require_mfa(owner: SignedUpMember, clock: ControllableClock) -> None:
    """The Owner enrols, then requires MFA in their Organisation."""
    await enrol(owner, clock)
    response = await set_policy(owner, True)
    assert response.status_code == 200, response.text


async def me(member: SignedUpMember) -> dict[str, Any]:
    response = await member.client.get("/api/auth/me")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def membership(session: dict[str, Any], organisation_id: str) -> dict[str, Any]:
    found: list[dict[str, Any]] = [
        o for o in session["organisations"] if o["id"] == organisation_id
    ]
    (only,) = found
    return only


async def policy_events(owner: SignedUpMember) -> list[dict[str, Any]]:
    response = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/audit-events",
        params={"action": "organisation.mfa_policy_changed"},
    )
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def test_owners_turn_the_policy_on_and_off_in_organisation_settings(
    owner: SignedUpMember, clock: ControllableClock
) -> None:
    organisation = await owner.client.get(f"/api/organisations/{owner.organisation_id}")
    assert organisation.json()["require_mfa"] is False
    assert membership(await me(owner), owner.organisation_id)["mfa_required"] is False
    await enrol(owner, clock)

    turned_on = await set_policy(owner, True)

    assert turned_on.status_code == 200, turned_on.text
    assert turned_on.json() == {
        "id": owner.organisation_id,
        "name": owner.organisation_name,
        "role": "owner",
        "require_mfa": True,
        "retention_days": 90,
    }
    organisation = await owner.client.get(f"/api/organisations/{owner.organisation_id}")
    assert organisation.json()["require_mfa"] is True
    assert membership(await me(owner), owner.organisation_id)["mfa_required"] is True

    turned_off = await set_policy(owner, False)

    assert turned_off.status_code == 200, turned_off.text
    assert turned_off.json()["require_mfa"] is False
    assert membership(await me(owner), owner.organisation_id)["mfa_required"] is False


async def test_an_owner_without_mfa_cannot_require_it(owner: SignedUpMember) -> None:
    response = await set_policy(owner, True)

    assert (response.status_code, response.json()) == (409, ENROL_FIRST)
    assert membership(await me(owner), owner.organisation_id)["mfa_required"] is False
    # Turning it off when it is already off needs no MFA: nothing changes.
    assert (await set_policy(owner, False)).status_code == 200


async def test_editors_cannot_change_the_policy(
    owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    editor = await member_factory(owner, "editor")
    await enrol(editor, clock)

    response = await editor.client.put(
        policy_path(owner.organisation_id), json={"require_mfa": True}
    )

    assert (response.status_code, response.json()) == (403, {"detail": "Only Owners can do this"})
    assert membership(await me(owner), owner.organisation_id)["mfa_required"] is False


async def test_me_says_whether_the_member_has_mfa(
    owner: SignedUpMember, clock: ControllableClock
) -> None:
    assert (await me(owner))["member"]["mfa_enabled"] is False
    await enrol(owner, clock)
    assert (await me(owner))["member"]["mfa_enabled"] is True


@pytest.mark.parametrize("route", ORGANISATION_SCOPED_ROUTES, ids=str)
async def test_members_without_mfa_are_refused_every_organisation_route(
    route: ScopedRoute,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    clock: ControllableClock,
) -> None:
    prepared = await route.prepare(owner, member_factory)
    member_without_mfa = await member_factory(owner, "owner")
    await require_mfa(owner, clock)
    params, body = prepared

    response = await member_without_mfa.client.request(
        route.method, route.path.format(organisation_id=owner.organisation_id, **params), json=body
    )

    assert (response.status_code, response.json()) == (403, MFA_REQUIRED)


async def test_the_api_lets_a_member_in_once_they_enrol(
    owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    editor = await member_factory(owner, "editor")
    await require_mfa(owner, clock)
    organisation_path = f"/api/organisations/{owner.organisation_id}"

    refused = await editor.client.get(organisation_path)
    session = await me(editor)

    assert (refused.status_code, refused.json()) == (403, MFA_REQUIRED)
    # Still signed in, and told why, so the Studio can send them to enrolment.
    assert session["member"]["mfa_enabled"] is False
    assert membership(session, owner.organisation_id)["mfa_required"] is True
    # The MFA routes are open to them.
    assert (await editor.client.get("/api/auth/mfa")).status_code == 200

    await enrol(editor, clock)

    allowed = await editor.client.get(organisation_path)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["require_mfa"] is True
    assert (await me(editor))["member"]["mfa_enabled"] is True


async def test_a_member_signing_in_without_mfa_gets_a_session_to_enrol_with(
    owner: SignedUpMember,
    member_factory: MemberFactory,
    new_client: ClientFactory,
    clock: ControllableClock,
) -> None:
    editor = await member_factory(owner, "editor")
    await require_mfa(owner, clock)
    browser = await new_client()

    signed_in = await browser.post(
        "/api/auth/sign-in", json={"email": editor.email, "password": editor.password}
    )

    assert signed_in.status_code == 200, signed_in.text
    assert membership(signed_in.json(), owner.organisation_id)["mfa_required"] is True
    refused = await browser.get(f"/api/organisations/{owner.organisation_id}")
    assert (refused.status_code, refused.json()) == (403, MFA_REQUIRED)
    assert (await browser.post("/api/auth/mfa/enrolment")).status_code == 201


async def test_the_policy_applies_only_to_its_own_organisation(
    owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    editor = await member_factory(owner, "editor")
    await require_mfa(owner, clock)

    # The Editor's own Organisation (from signing up) doesn't require MFA.
    session = await me(editor)
    (own,) = [o for o in session["organisations"] if o["id"] != owner.organisation_id]
    response = await editor.client.get(f"/api/organisations/{own['id']}")

    assert response.status_code == 200, response.text
    assert own["mfa_required"] is False


async def test_turning_the_policy_off_lets_members_without_mfa_back_in(
    owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    editor = await member_factory(owner, "editor")
    await require_mfa(owner, clock)
    assert (await editor.client.get(f"/api/organisations/{owner.organisation_id}")).status_code == (
        403
    )

    assert (await set_policy(owner, False)).status_code == 200

    assert (await editor.client.get(f"/api/organisations/{owner.organisation_id}")).status_code == (
        200
    )


async def test_a_member_cannot_disable_mfa_while_an_organisation_requires_it(
    owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    editor = await member_factory(owner, "editor")
    secret = await enrol(editor, clock)
    await require_mfa(owner, clock)
    code = totp(secret, clock.now())

    refused = await editor.client.post(
        "/api/auth/mfa/disable", json={"password": editor.password, "code": code}
    )

    assert refused.status_code == 409
    assert refused.json() == {
        "detail": f"MFA can't be turned off while {owner.organisation_name} requires it."
    }
    assert (await editor.client.get("/api/auth/mfa")).json()["enabled"] is True

    assert (await set_policy(owner, False)).status_code == 200
    # The refused attempt didn't use the code up.
    disabled = await editor.client.post(
        "/api/auth/mfa/disable", json={"password": editor.password, "code": code}
    )
    assert disabled.status_code == 204, disabled.text


async def test_an_owner_cannot_disable_mfa_while_their_organisation_requires_it(
    owner: SignedUpMember, clock: ControllableClock
) -> None:
    secret = await enrol(owner, clock)
    assert (await set_policy(owner, True)).status_code == 200

    refused = await owner.client.post(
        "/api/auth/mfa/disable",
        json={"password": owner.password, "code": totp(secret, clock.now())},
    )

    assert refused.status_code == 409
    assert (await owner.client.get("/api/auth/mfa")).json()["enabled"] is True


async def test_every_requiring_organisation_is_named_when_disabling_is_refused(
    tenant_factory: TenantFactory, clock: ControllableClock
) -> None:
    first, second, member = await tenant_factory(), await tenant_factory(), await tenant_factory()
    await join_organisation(first, member, "editor")
    await join_organisation(second, member, "editor")
    secret = await enrol(member, clock)
    await require_mfa(first, clock)
    await require_mfa(second, clock)

    refused = await member.client.post(
        "/api/auth/mfa/disable",
        json={"password": member.password, "code": totp(secret, clock.now())},
    )

    assert refused.status_code == 409
    assert refused.json() == {
        "detail": "MFA can't be turned off while "
        f"{first.organisation_name} and {second.organisation_name} require it."
    }


async def test_policy_changes_are_audit_events(
    owner: SignedUpMember, clock: ControllableClock
) -> None:
    await set_policy(owner, True)  # refused: the Owner has no MFA yet
    await enrol(owner, clock)
    await set_policy(owner, True)
    await set_policy(owner, True)  # already on: nothing changes
    clock.advance(timedelta(minutes=1))
    await set_policy(owner, False)

    turned_off, turned_on = await policy_events(owner)  # newest first

    for event in (turned_on, turned_off):
        assert event["actor"]["id"] == owner.member_id
        assert event["target"] == {"type": "organisation", "id": owner.organisation_id}
    assert (turned_on["before"], turned_on["after"]) == (
        {"require_mfa": False},
        {"require_mfa": True},
    )
    assert (turned_off["before"], turned_off["after"]) == (
        {"require_mfa": True},
        {"require_mfa": False},
    )
