"""API seam: Owners manage Members and roles, Members leave, and the last Owner stays.

Everything is observed through the API: the Members list, ``/api/auth/me`` memberships,
answers to Organisation-scoped routes, and Audit Events from the Audit list endpoint.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest

from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.fakes.clock import ControllableClock


def members_path(organisation_id: str, member_id: str | None = None) -> str:
    path = f"/api/organisations/{organisation_id}/members"
    return path if member_id is None else f"{path}/{member_id}"


async def members(owner: SignedUpMember) -> list[dict[str, Any]]:
    response = await owner.client.get(members_path(owner.organisation_id))
    assert response.status_code == 200, response.text
    result: list[dict[str, Any]] = response.json()
    return result


# Listing


async def test_owners_see_every_member_with_their_role(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    co_owner = await member_factory(owner, "owner")

    listed = await members(owner)

    assert [(m["id"], m["name"], m["email"], m["role"]) for m in listed] == [
        (owner.member_id, owner.name, owner.email, "owner"),
        (editor.member_id, editor.name, editor.email, "editor"),
        (co_owner.member_id, co_owner.name, co_owner.email, "owner"),
    ]
    assert all(isinstance(m["joined_at"], str) for m in listed)


async def test_the_members_list_shows_only_this_organisations_members(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    await tenant_factory()

    assert [m["id"] for m in await members(owner)] == [owner.member_id]


# Changing roles


async def change_role(actor: SignedUpMember, member_id: str, role: str) -> httpx.Response:
    return await actor.client.patch(
        members_path(actor.organisation_id, member_id), json={"role": role}
    )


async def role_in(member: SignedUpMember, organisation_id: str) -> str | None:
    """The Member's role in the Organisation, as their own session sees it."""
    me = (await member.client.get("/api/auth/me")).json()
    roles = {o["id"]: o["role"] for o in me["organisations"]}
    return roles.get(organisation_id)


async def test_owners_promote_an_editor_and_demote_them_again(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")

    promoted = await change_role(owner, editor.member_id, "owner")

    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["role"] == "owner"
    assert promoted.json()["email"] == editor.email
    assert await role_in(editor, owner.organisation_id) == "owner"
    # Owner-only routes open up straight away.
    assert (await editor.client.get(members_path(owner.organisation_id))).status_code == 200

    demoted = await change_role(owner, editor.member_id, "editor")

    assert demoted.json()["role"] == "editor"
    assert await role_in(editor, owner.organisation_id) == "editor"
    assert (await editor.client.get(members_path(owner.organisation_id))).status_code == 403


async def test_setting_the_role_a_member_already_has_changes_nothing(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")

    response = await change_role(owner, editor.member_id, "editor")

    assert response.status_code == 200
    assert response.json()["role"] == "editor"
    assert await audit_events(owner, "member.role_changed") == []


async def test_roles_are_owner_or_editor(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")

    response = await change_role(owner, editor.member_id, "admin")

    assert response.status_code == 422
    assert await role_in(editor, owner.organisation_id) == "editor"


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
async def test_members_of_other_organisations_are_not_found(
    method: str, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    outsider = await tenant_factory()

    for member_id in (outsider.member_id, str(uuid.uuid4())):
        response = await owner.client.request(
            method, members_path(owner.organisation_id, member_id), json={"role": "editor"}
        )
        assert (response.status_code, response.json()) == (404, {"detail": "Not found"})
    assert await role_in(outsider, outsider.organisation_id) == "owner"


# Removing and leaving


async def test_removing_a_member_ends_their_access_at_once(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    organisation_path = f"/api/organisations/{owner.organisation_id}"
    assert (await editor.client.get(organisation_path)).status_code == 200

    removed = await owner.client.delete(members_path(owner.organisation_id, editor.member_id))

    assert removed.status_code == 204
    # The same session, with no sign-out: the Organisation is gone for them.
    assert (await editor.client.get(organisation_path)).status_code == 404
    left = await editor.client.post(f"{organisation_path}/leave")
    assert left.status_code == 404
    assert await role_in(editor, owner.organisation_id) is None
    # They keep their account, signed in, and the Organisation they own.
    me = (await editor.client.get("/api/auth/me")).json()
    assert [o["role"] for o in me["organisations"]] == ["owner"]
    assert [m["id"] for m in await members(owner)] == [owner.member_id]


async def test_any_member_can_leave(owner: SignedUpMember, member_factory: MemberFactory) -> None:
    editor = await member_factory(owner, "editor")

    response = await editor.client.post(f"/api/organisations/{owner.organisation_id}/leave")

    assert response.status_code == 204
    assert await role_in(editor, owner.organisation_id) is None
    assert (
        await editor.client.get(f"/api/organisations/{owner.organisation_id}")
    ).status_code == 404
    assert [m["id"] for m in await members(owner)] == [owner.member_id]


async def test_an_owner_can_leave_or_step_down_while_another_owner_remains(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    co_owner = await member_factory(owner, "owner")

    stepped_down = await change_role(owner, owner.member_id, "editor")
    assert stepped_down.status_code == 200, stepped_down.text
    promoted_back = await change_role(co_owner, owner.member_id, "owner")
    assert promoted_back.status_code == 200
    removed_self = await owner.client.delete(members_path(owner.organisation_id, owner.member_id))

    assert removed_self.status_code == 204
    assert [(m["id"], m["role"]) for m in await members(co_owner)] == [
        (co_owner.member_id, "owner")
    ]


# The last Owner


PAIRS = 10
LAST_OWNER = {
    "detail": "An Organisation needs at least one Owner. Make someone else an Owner first."
}


async def test_the_last_owner_cannot_be_demoted_removed_or_leave(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    path = members_path(owner.organisation_id, owner.member_id)

    refused = [
        await change_role(owner, owner.member_id, "editor"),
        await owner.client.delete(path),
        await owner.client.post(f"/api/organisations/{owner.organisation_id}/leave"),
    ]

    assert [(r.status_code, r.json()) for r in refused] == [(409, LAST_OWNER)] * 3
    assert [(m["id"], m["role"]) for m in await members(owner)] == [
        (owner.member_id, "owner"),
        (editor.member_id, "editor"),
    ]
    for action in ("member.role_changed", "member.removed", "member.left"):
        assert await audit_events(owner, action) == []


async def test_two_owners_demoting_each_other_at_once_leave_one_owner(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    co_owner = await member_factory(owner, "owner")

    results = await asyncio.gather(
        change_role(owner, co_owner.member_id, "editor"),
        change_role(co_owner, owner.member_id, "editor"),
    )

    # One wins. The other is refused: 409, or 403 if it was already an Editor when it started.
    assert sorted(r.status_code for r in results)[0] == 200
    assert sorted(r.status_code for r in results)[1] in {403, 409}
    remaining = owner if results[0].status_code == 200 else co_owner
    assert sorted(m["role"] for m in await members(remaining)) == ["editor", "owner"]


async def test_owners_leaving_at_once_always_leave_one_owner(
    tenant_factory: TenantFactory, member_factory: MemberFactory
) -> None:
    # Several Organisations, each with two Owners who leave at the same moment, so the
    # requests interleave. In each, exactly one leaves and the other is refused.
    pairs = []
    for _ in range(PAIRS):
        owner = await tenant_factory()
        pairs.append((owner, await member_factory(owner, "owner")))

    async def both_leave(pair: tuple[SignedUpMember, SignedUpMember]) -> list[int]:
        leave = f"/api/organisations/{pair[0].organisation_id}/leave"
        results = await asyncio.gather(*(m.client.post(leave) for m in pair))
        return [r.status_code for r in results]

    outcomes = await asyncio.gather(*(both_leave(pair) for pair in pairs))

    assert all(sorted(codes) == [204, 409] for codes in outcomes), outcomes
    for pair, codes in zip(pairs, outcomes, strict=True):
        remaining = pair[codes.index(409)]
        assert [m["role"] for m in await members(remaining)] == ["owner"]


# Owner-only


async def test_editors_cannot_list_change_or_remove_members(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    other = await member_factory(owner, "editor")

    responses = [
        await editor.client.get(members_path(owner.organisation_id)),
        await change_role(editor, editor.member_id, "owner"),
        await change_role(editor, other.member_id, "owner"),
        await editor.client.delete(members_path(owner.organisation_id, other.member_id)),
    ]

    assert [r.status_code for r in responses] == [403] * 4
    assert {r.json()["detail"] for r in responses} == {"Only Owners can do this"}
    assert [m["role"] for m in await members(owner)] == ["owner", "editor", "editor"]


# Audit Events


async def audit_events(owner: SignedUpMember, action: str) -> list[dict[str, Any]]:
    response = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/audit-events", params={"action": action}
    )
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def test_role_changes_removals_and_leaving_are_audit_events(
    owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    promoted = await member_factory(owner, "editor")
    removed = await member_factory(owner, "editor")
    leaver = await member_factory(owner, "owner")

    await change_role(owner, promoted.member_id, "owner")
    clock.advance(timedelta(minutes=1))
    await owner.client.delete(members_path(owner.organisation_id, removed.member_id))
    clock.advance(timedelta(minutes=1))
    await leaver.client.post(f"/api/organisations/{owner.organisation_id}/leave")

    (role_changed,) = await audit_events(owner, "member.role_changed")
    assert role_changed["actor"]["id"] == owner.member_id
    assert role_changed["target"] == {"type": "member", "id": promoted.member_id}
    assert role_changed["before"] == {"email": promoted.email, "role": "editor"}
    assert role_changed["after"] == {"email": promoted.email, "role": "owner"}
    (removal,) = await audit_events(owner, "member.removed")
    assert removal["actor"]["id"] == owner.member_id
    assert removal["target"] == {"type": "member", "id": removed.member_id}
    assert removal["before"] == {"email": removed.email, "name": removed.name, "role": "editor"}
    assert removal["after"] is None
    (leaving,) = await audit_events(owner, "member.left")
    assert leaving["actor"]["id"] == leaver.member_id
    assert leaving["target"] == {"type": "member", "id": leaver.member_id}
    assert leaving["before"] == {"email": leaver.email, "name": leaver.name, "role": "owner"}
    # Recorded at the clock's time, one minute apart.
    times = [datetime.fromisoformat(e["occurred_at"]) for e in (role_changed, removal, leaving)]
    assert times[1] - times[0] == times[2] - times[1] == timedelta(minutes=1)
