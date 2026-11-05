"""Cross-tenant isolation, shared by every spec.

Every Organisation-scoped route is listed in ``ORGANISATION_SCOPED_ROUTES``. For each one, a
Member of another Organisation gets the same 404 as for an Organisation that doesn't exist,
and a guard test fails when a new Organisation-scoped route is added without being listed.

To extend: add a ``ScopedRoute`` with the method and path (``{organisation_id}`` is filled in)
and, if the route needs a body or resources inside the Organisation, a ``prepare`` coroutine
that creates them as the owning Member and returns the path parameters and body to use.
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
from tests.conftest import SignedUpMember, TenantFactory

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


ORGANISATION_SCOPED_ROUTES = [
    ScopedRoute("GET", "/api/organisations/{organisation_id}"),
    ScopedRoute("GET", "/api/organisations/{organisation_id}/audit-events"),
    ScopedRoute("GET", "/api/organisations/{organisation_id}/audit-events/facets"),
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

    own = await _call(owner.client, route, owner.organisation_id, prepared)
    other = await _call(outsider.client, route, owner.organisation_id, prepared)
    missing = await _call(outsider.client, route, str(uuid.uuid4()), prepared)

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
