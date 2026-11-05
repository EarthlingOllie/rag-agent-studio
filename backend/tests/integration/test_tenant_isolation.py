"""Cross-tenant isolation, shared by every spec.

Every Organisation-scoped route is listed in ``ORGANISATION_SCOPED_ROUTES``. For each one, a
Member of another Organisation gets the same 404 as for an Organisation that doesn't exist,
and a guard test fails when a new Organisation-scoped route is added without being listed.

To extend: add a ``ScopedRoute`` with the method and path (``{organisation_id}`` is filled in)
and, if the route needs a body or resources inside the Organisation, a ``prepare`` coroutine
that creates them as the owning Member and returns the path parameters and body to use.

The same routes are also checked for a Member who belongs to two Organisations: whichever
one is active, they reach each Organisation's resources only through that Organisation's
path, and a third Organisation stays not found.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from app.core.db import Base
from app.main import create_app
from app.tenancy.models import PLATFORM_TABLES
from tests.conftest import SignedUpMember, TenantFactory, join_organisation

Prepared = tuple[dict[str, str], dict[str, Any] | None]


async def _nothing_to_prepare(owner: SignedUpMember) -> Prepared:
    return {}, None


@dataclass(frozen=True)
class ScopedRoute:
    method: str
    path: str
    prepare: Callable[[SignedUpMember], Awaitable[Prepared]] = field(default=_nothing_to_prepare)

    def __str__(self) -> str:
        return f"{self.method} {self.path}"


async def _new_invite_body(owner: SignedUpMember) -> Prepared:
    return {}, {"email": f"isolation-{uuid.uuid4().hex[:12]}@example.test", "role": "editor"}


async def _pending_invite(owner: SignedUpMember) -> Prepared:
    _, body = await _new_invite_body(owner)
    response = await owner.client.post(
        f"/api/organisations/{owner.organisation_id}/invites", json=body
    )
    assert response.status_code == 201, response.text
    return {"invite_id": response.json()["invite"]["id"]}, {}


ORGANISATION_SCOPED_ROUTES = [
    ScopedRoute("GET", "/api/organisations/{organisation_id}"),
    ScopedRoute("GET", "/api/organisations/{organisation_id}/audit-events"),
    ScopedRoute("GET", "/api/organisations/{organisation_id}/audit-events/facets"),
    ScopedRoute("GET", "/api/organisations/{organisation_id}/invites"),
    ScopedRoute("POST", "/api/organisations/{organisation_id}/invites", _new_invite_body),
    ScopedRoute(
        "DELETE", "/api/organisations/{organisation_id}/invites/{invite_id}", _pending_invite
    ),
    ScopedRoute(
        "POST", "/api/organisations/{organisation_id}/invites/{invite_id}/renew", _pending_invite
    ),
]


async def _call(
    client: httpx.AsyncClient, route: ScopedRoute, organisation_id: str, prepared: Prepared
) -> httpx.Response:
    params, body = prepared
    path = route.path.format(organisation_id=organisation_id, **params)
    return await client.request(route.method, path, json=body)


@pytest.mark.parametrize("route", ORGANISATION_SCOPED_ROUTES, ids=str)
async def test_another_tenants_resources_are_not_found(
    route: ScopedRoute, tenant_factory: TenantFactory
) -> None:
    owner, outsider = await tenant_factory(), await tenant_factory()
    prepared = await route.prepare(owner)

    # The outsider goes first, so a route that changes or removes the resource is still
    # checked against a resource that exists.
    other = await _call(outsider.client, route, owner.organisation_id, prepared)
    missing = await _call(outsider.client, route, str(uuid.uuid4()), prepared)
    own = await _call(owner.client, route, owner.organisation_id, prepared)

    assert own.status_code < 400, own.text
    assert other.status_code == 404
    assert other.json() == {"detail": "Not found"}
    # Indistinguishable from an Organisation that doesn't exist.
    assert (missing.status_code, missing.json()) == (other.status_code, other.json())


@pytest.mark.parametrize("route", ORGANISATION_SCOPED_ROUTES, ids=str)
async def test_organisation_scoped_routes_need_a_signed_in_member(
    route: ScopedRoute, owner: SignedUpMember, client: httpx.AsyncClient
) -> None:
    prepared = await route.prepare(owner)

    response = await _call(client, route, owner.organisation_id, prepared)

    assert response.status_code == 401


@dataclass(frozen=True)
class TwoOrganisations:
    """``member`` owns their own Organisation and joined ``other``'s as an Owner."""

    member: SignedUpMember
    other: SignedUpMember


@pytest.fixture
async def two_organisations(tenant_factory: TenantFactory) -> TwoOrganisations:
    member, other = await tenant_factory(), await tenant_factory()
    await join_organisation(other, member, "owner")
    return TwoOrganisations(member, other)


async def _switch(member: SignedUpMember, organisation_id: str) -> None:
    response = await member.client.put(
        "/api/auth/me/active-organisation", json={"organisation_id": organisation_id}
    )
    assert response.status_code == 200, response.text


def _has_resource(route: ScopedRoute) -> bool:
    return "{" in route.path.replace("{organisation_id}", "")


@pytest.mark.parametrize("route", ORGANISATION_SCOPED_ROUTES, ids=str)
@pytest.mark.parametrize("active", ["own", "other"])
async def test_a_member_of_two_organisations_cannot_reach_a_third(
    route: ScopedRoute,
    active: str,
    two_organisations: TwoOrganisations,
    tenant_factory: TenantFactory,
) -> None:
    member, other = two_organisations.member, two_organisations.other
    await _switch(member, member.organisation_id if active == "own" else other.organisation_id)
    third = await tenant_factory()
    prepared = await route.prepare(third)

    response = await _call(member.client, route, third.organisation_id, prepared)

    assert (response.status_code, response.json()) == (404, {"detail": "Not found"})


@pytest.mark.parametrize(
    "route", [r for r in ORGANISATION_SCOPED_ROUTES if _has_resource(r)], ids=str
)
async def test_one_organisations_resources_are_not_found_through_the_members_other_organisation(
    route: ScopedRoute, two_organisations: TwoOrganisations
) -> None:
    member, other = two_organisations.member, two_organisations.other
    # The resource belongs to the other Organisation, which is also the active one.
    prepared = await route.prepare(other)
    await _switch(member, other.organisation_id)

    crossed = await _call(member.client, route, member.organisation_id, prepared)
    through_its_own = await _call(member.client, route, other.organisation_id, prepared)

    assert (crossed.status_code, crossed.json()) == (404, {"detail": "Not found"})
    assert through_its_own.status_code < 400, through_its_own.text


async def test_a_member_of_two_organisations_sees_each_ones_data_only_in_it(
    two_organisations: TwoOrganisations,
) -> None:
    member, other = two_organisations.member, two_organisations.other
    own_invite = await member.client.post(
        f"/api/organisations/{member.organisation_id}/invites",
        json={"email": "own-only@example.test", "role": "editor", "send_email": False},
    )
    other_invite = await other.client.post(
        f"/api/organisations/{other.organisation_id}/invites",
        json={"email": "other-only@example.test", "role": "editor", "send_email": False},
    )
    assert own_invite.status_code == other_invite.status_code == 201

    for active in (other.organisation_id, member.organisation_id):
        await _switch(member, active)
        seen = {}
        for organisation_id in (member.organisation_id, other.organisation_id):
            base = f"/api/organisations/{organisation_id}"
            organisation = (await member.client.get(base)).json()
            invites = (await member.client.get(f"{base}/invites")).json()
            events = (await member.client.get(f"{base}/audit-events")).json()
            seen[organisation_id] = (
                organisation["name"],
                {i["email"] for i in invites},
                {
                    e["after"].get("email")
                    for e in events["items"]
                    if e["action"] == "invite.created"
                },
            )

        assert seen == {
            member.organisation_id: (
                member.organisation_name,
                {"own-only@example.test"},
                {"own-only@example.test"},
            ),
            other.organisation_id: (
                other.organisation_name,
                {"other-only@example.test"},
                {"other-only@example.test", member.email},
            ),
        }


def test_every_organisation_scoped_route_is_in_the_isolation_test() -> None:
    """New Organisation-scoped routes must be added to ORGANISATION_SCOPED_ROUTES."""
    listed = {(r.method, r.path) for r in ORGANISATION_SCOPED_ROUTES}

    found = {
        (method.upper(), path)
        for path, operations in create_app().openapi()["paths"].items()
        if "{organisation_id}" in path
        for method in operations
    }

    assert found == listed


def test_every_table_below_the_platform_level_carries_an_organisation_id() -> None:
    for name, table in Base.metadata.tables.items():
        if name in PLATFORM_TABLES:
            continue
        column = table.columns.get("organisation_id")
        assert column is not None, f"{name} has no organisation_id"
        assert not column.nullable, f"{name}.organisation_id is nullable"
