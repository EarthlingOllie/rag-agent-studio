"""Cross-tenant isolation and role enforcement, shared by every spec.

Every Organisation-scoped route is listed in ``ORGANISATION_SCOPED_ROUTES`` with the role it
requires. For each one, a Member of another Organisation gets the same 404 as for an
Organisation that doesn't exist, and an Editor gets 403 from an Owner-only route. Guard tests
fail when a new Organisation-scoped route is added without being listed, or when a route's
policy dependency (``app.tenancy.policy.RequireRole``) doesn't declare the listed role.

To extend: add a ``ScopedRoute`` with the method, path (``{organisation_id}`` is filled in)
and required role and, if the route needs a body or resources inside the Organisation, a
``prepare`` coroutine that creates them as the owning Member (it may add Members with the
given factory) and returns the path parameters and body to use.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.core.db import Base
from app.main import ROUTERS, create_app
from app.tenancy.models import PLATFORM_TABLES, Role
from app.tenancy.policy import RequireRole
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory

Prepared = tuple[dict[str, str], dict[str, Any] | None]
Prepare = Callable[[SignedUpMember, MemberFactory], Awaitable[Prepared]]

OWNER, EDITOR = Role.OWNER, Role.EDITOR


async def _nothing_to_prepare(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    return {}, None


@dataclass(frozen=True)
class ScopedRoute:
    method: str
    path: str
    # The lowest role allowed: Editor (any Member) or Owner.
    role: Role
    prepare: Prepare = field(default=_nothing_to_prepare)

    def __str__(self) -> str:
        return f"{self.method} {self.path}"


async def _new_invite_body(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    return {}, {"email": f"isolation-{uuid.uuid4().hex[:12]}@example.test", "role": "editor"}


async def _pending_invite(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    _, body = await _new_invite_body(owner, add_member)
    response = await owner.client.post(
        f"/api/organisations/{owner.organisation_id}/invites", json=body
    )
    assert response.status_code == 201, response.text
    return {"invite_id": response.json()["invite"]["id"]}, {}


async def _an_editor(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    editor = await add_member(owner, "editor")
    return {"member_id": editor.member_id}, {"role": "owner"}


async def _another_owner(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    # So the Owner calling the route isn't the last Owner, and may leave.
    await add_member(owner, "owner")
    return {}, None


ORGANISATION_SCOPED_ROUTES = [
    ScopedRoute("GET", "/api/organisations/{organisation_id}", EDITOR),
    ScopedRoute("GET", "/api/organisations/{organisation_id}/audit-events", OWNER),
    ScopedRoute("GET", "/api/organisations/{organisation_id}/audit-events/facets", OWNER),
    ScopedRoute("GET", "/api/organisations/{organisation_id}/invites", OWNER),
    ScopedRoute("POST", "/api/organisations/{organisation_id}/invites", OWNER, _new_invite_body),
    ScopedRoute(
        "DELETE", "/api/organisations/{organisation_id}/invites/{invite_id}", OWNER, _pending_invite
    ),
    ScopedRoute(
        "POST",
        "/api/organisations/{organisation_id}/invites/{invite_id}/renew",
        OWNER,
        _pending_invite,
    ),
    ScopedRoute("GET", "/api/organisations/{organisation_id}/members", OWNER),
    ScopedRoute(
        "PATCH", "/api/organisations/{organisation_id}/members/{member_id}", OWNER, _an_editor
    ),
    ScopedRoute(
        "DELETE", "/api/organisations/{organisation_id}/members/{member_id}", OWNER, _an_editor
    ),
    ScopedRoute("POST", "/api/organisations/{organisation_id}/leave", EDITOR, _another_owner),
]
OWNER_ONLY_ROUTES = [route for route in ORGANISATION_SCOPED_ROUTES if route.role is OWNER]


async def _call(
    client: httpx.AsyncClient, route: ScopedRoute, organisation_id: str, prepared: Prepared
) -> httpx.Response:
    params, body = prepared
    path = route.path.format(organisation_id=organisation_id, **params)
    return await client.request(route.method, path, json=body)


@pytest.mark.parametrize("route", ORGANISATION_SCOPED_ROUTES, ids=str)
async def test_another_tenants_resources_are_not_found(
    route: ScopedRoute, tenant_factory: TenantFactory, member_factory: MemberFactory
) -> None:
    owner, outsider = await tenant_factory(), await tenant_factory()
    prepared = await route.prepare(owner, member_factory)

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
    route: ScopedRoute,
    owner: SignedUpMember,
    client: httpx.AsyncClient,
    member_factory: MemberFactory,
) -> None:
    prepared = await route.prepare(owner, member_factory)

    response = await _call(client, route, owner.organisation_id, prepared)

    assert response.status_code == 401


@pytest.mark.parametrize("route", OWNER_ONLY_ROUTES, ids=str)
async def test_editors_are_refused_owner_only_routes(
    route: ScopedRoute, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    prepared = await route.prepare(owner, member_factory)
    editor = await member_factory(owner, "editor")

    refused = await _call(editor.client, route, owner.organisation_id, prepared)
    allowed = await _call(owner.client, route, owner.organisation_id, prepared)

    assert (refused.status_code, refused.json()) == (403, {"detail": "Only Owners can do this"})
    assert allowed.status_code < 400, allowed.text


@pytest.mark.parametrize(
    "route", [r for r in ORGANISATION_SCOPED_ROUTES if r.role is EDITOR], ids=str
)
async def test_editors_reach_routes_open_to_every_member(
    route: ScopedRoute, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    prepared = await route.prepare(owner, member_factory)
    editor = await member_factory(owner, "editor")

    response = await _call(editor.client, route, owner.organisation_id, prepared)

    assert response.status_code < 400, response.text


def _policies(dependant: Dependant) -> list[RequireRole]:
    found = [d.call for d in dependant.dependencies if isinstance(d.call, RequireRole)]
    return found + [p for d in dependant.dependencies for p in _policies(d)]


def test_each_organisation_scoped_route_declares_its_role_with_one_policy() -> None:
    """The listed role is the one the route's single RequireRole dependency enforces."""
    listed = {(r.method, r.path): r.role for r in ORGANISATION_SCOPED_ROUTES}

    declared = {
        (method, route.path): [policy.role for policy in _policies(route.dependant)]
        for router in ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute) and "{organisation_id}" in route.path
        for method in route.methods or ()
    }

    assert declared == {key: [role] for key, role in listed.items()}


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
