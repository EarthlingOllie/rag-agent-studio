"""API seam: a Member of several Organisations chooses which one is active.

The active Organisation is a remembered choice that ``/api/auth/me`` reports, so the Studio
opens it on the next visit. It never widens access: Organisation-scoped routes still take the
Organisation from the path (see ``test_tenant_isolation.py``).
"""

import uuid

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import (
    TEST_DATABASE_URL,
    ClientFactory,
    SignedUpMember,
    TenantFactory,
    join_organisation,
)

ACTIVE = "/api/auth/me/active-organisation"


async def switch(client: httpx.AsyncClient, organisation_id: str) -> httpx.Response:
    return await client.put(ACTIVE, json={"organisation_id": organisation_id})


async def active_organisation(client: httpx.AsyncClient) -> str | None:
    me = await client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    active: str | None = me.json()["active_organisation_id"]
    return active


async def test_a_new_member_starts_in_the_organisation_they_created(
    client: httpx.AsyncClient,
) -> None:
    signed_up = await client.post(
        "/api/auth/sign-up",
        json={
            "name": "Grace Hopper",
            "email": f"grace-{uuid.uuid4().hex[:12]}@example.test",
            "password": "a long enough password 42",
            "organisation_name": "Compilers",
        },
    )

    (organisation,) = signed_up.json()["organisations"]
    assert signed_up.json()["active_organisation_id"] == organisation["id"]
    assert await active_organisation(client) == organisation["id"]


async def test_a_member_of_two_organisations_switches_and_the_choice_is_remembered(
    owner: SignedUpMember, tenant_factory: TenantFactory, new_client: ClientFactory
) -> None:
    member = await tenant_factory()
    await join_organisation(owner, member, "editor")
    # Joining doesn't move the Member: they stay where they were.
    assert await active_organisation(member.client) == member.organisation_id

    switched = await switch(member.client, owner.organisation_id)

    assert switched.status_code == 200, switched.text
    assert switched.json()["active_organisation_id"] == owner.organisation_id
    assert {o["id"] for o in switched.json()["organisations"]} == {
        owner.organisation_id,
        member.organisation_id,
    }
    # A reload asks /me again and gets the same answer.
    assert await active_organisation(member.client) == owner.organisation_id
    # So does a later sign-in, in another browser.
    elsewhere = await new_client()
    signed_in = await elsewhere.post(
        "/api/auth/sign-in", json={"email": member.email, "password": member.password}
    )
    assert signed_in.json()["active_organisation_id"] == owner.organisation_id
    # And switching back is remembered too.
    assert (await switch(elsewhere, member.organisation_id)).status_code == 200
    assert await active_organisation(member.client) == member.organisation_id


async def test_switching_is_per_member(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    member, colleague = await tenant_factory(), await tenant_factory()
    await join_organisation(owner, member, "editor")
    await join_organisation(owner, colleague, "editor")

    await switch(member.client, owner.organisation_id)

    # Both belong to the Owner's Organisation, but only the Member switched to it.
    assert await active_organisation(member.client) == owner.organisation_id
    assert await active_organisation(colleague.client) == colleague.organisation_id


async def test_switching_to_an_organisation_the_member_does_not_belong_to_is_not_found(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    outsider = await tenant_factory()

    other = await switch(outsider.client, owner.organisation_id)
    missing = await switch(outsider.client, str(uuid.uuid4()))

    assert (other.status_code, other.json()) == (404, {"detail": "Not found"})
    assert (missing.status_code, missing.json()) == (other.status_code, other.json())
    assert await active_organisation(outsider.client) == outsider.organisation_id


async def test_switching_needs_a_signed_in_member(
    owner: SignedUpMember, client: httpx.AsyncClient
) -> None:
    response = await switch(client, owner.organisation_id)

    assert response.status_code == 401


async def test_switching_needs_an_organisation_id(owner: SignedUpMember) -> None:
    response = await owner.client.put(ACTIVE, json={"organisation_id": "not-a-uuid"})

    assert response.status_code == 422


async def test_a_remembered_organisation_the_member_has_left_is_not_active(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    member = await tenant_factory()
    await join_organisation(owner, member, "editor")
    await switch(member.client, owner.organisation_id)

    # Removing a Member has no API until ticket 01-09, so the membership is deleted directly.
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "DELETE FROM memberships"
                    " WHERE member_id = :member AND organisation_id = :organisation"
                ),
                {"member": member.member_id, "organisation": owner.organisation_id},
            )
    finally:
        await engine.dispose()

    assert await active_organisation(member.client) == member.organisation_id
    assert (await switch(member.client, owner.organisation_id)).status_code == 404
