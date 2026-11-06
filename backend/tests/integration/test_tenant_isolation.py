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
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.core.db import Base
from app.main import ROUTERS, create_app
from app.tenancy.models import PLATFORM_TABLES, Role
from app.tenancy.policy import RequireRole
from tests import documents, theme_images
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory, join_organisation

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


async def _new_credential_body(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    return {}, {
        "name": f"Isolation {uuid.uuid4().hex[:12]}",
        "provider": "openai",
        "api_key": "sk-isolation-test-only-0000",
    }


async def _a_credential(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    _, body = await _new_credential_body(owner, add_member)
    response = await owner.client.post(
        f"/api/organisations/{owner.organisation_id}/credentials", json=body
    )
    assert response.status_code == 201, response.text
    return {"credential_id": response.json()["id"]}, {"api_key": "sk-isolation-rotated-0001"}


async def _new_bedrock_body(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    return {}, {
        "name": f"Isolation {uuid.uuid4().hex[:12]}",
        "auth_kind": "aws_role",
        "role_arn": "arn:aws:iam::111122223333:role/IsolationTest",
        "region": "us-east-1",
    }


_CREDENTIAL = "/api/organisations/{organisation_id}/credentials/{credential_id}"


async def _a_credential_to_list(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    params, _ = await _a_credential(owner, add_member)
    return params | {"capability": "chat"}, None


async def _a_chat_model_choice(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    params, _ = await _a_credential(owner, add_member)
    return {}, {"credential_id": params["credential_id"], "model": "gpt-4.1"}


async def _a_price_override(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    params, _ = await _a_credential(owner, add_member)
    return params, {"model": "gpt-4.1", "input": "1.5"}


async def _a_theme(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    theme = (await owner.client.get(f"/api/organisations/{owner.organisation_id}/theme")).json()
    for key in ("updated_at", "logo", "avatar"):
        del theme[key]
    theme["radius"] = 3
    return {}, theme


THEME_IMAGE = "/api/organisations/{organisation_id}/theme/images/{kind}"


async def _a_theme_image_to_start(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    return {"kind": "logo"}, {"filename": "logo.png", "size_bytes": 10}


async def _an_uploaded_theme_image(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    ticket = await theme_images.uploaded_ticket(owner, "logo", theme_images.png())
    return {"kind": "logo"}, {"upload_id": ticket["upload_id"]}


async def _a_theme_image(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    await theme_images.upload(owner, "avatar", theme_images.png())
    return {"kind": "avatar"}, None


async def _new_project_body(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    return {}, {"name": f"Isolation {uuid.uuid4().hex[:8]}", "description": "Scoped"}


async def _make_project(owner: SignedUpMember, *, archived: bool = False) -> str:
    """Creates a Project in the Owner's Organisation through the API; returns its ID."""
    _, body = await _new_project_body(owner, _no_members)
    created = await owner.client.post(
        f"/api/organisations/{owner.organisation_id}/projects", json=body
    )
    assert created.status_code == 201, created.text
    project_id: str = created.json()["id"]
    if archived:
        response = await owner.client.post(
            f"/api/organisations/{owner.organisation_id}/projects/{project_id}/archive"
        )
        assert response.status_code == 200, response.text
    return project_id


async def _no_members(owner: SignedUpMember, role: str) -> SignedUpMember:
    raise AssertionError("This preparation adds no Members")


async def _a_project(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    return {"project_id": await _make_project(owner)}, None


async def _a_project_to_rename(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    return {"project_id": await _make_project(owner)}, {"name": "Renamed"}


async def _instructions_to_save(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    return {"project_id": await _make_project(owner)}, {"markdown": "# Rules"}


async def _instructions_to_publish(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    project_id = await _make_project(owner)
    saved = await owner.client.put(
        f"/api/organisations/{owner.organisation_id}/projects/{project_id}/instructions",
        json={"markdown": "# Rules"},
    )
    assert saved.status_code == 200, saved.text
    return {"project_id": project_id}, {"note": "First rules"}


async def _instructions_to_revert(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    project_id = await _make_project(owner)
    path = f"/api/organisations/{owner.organisation_id}/projects/{project_id}/instructions"
    for markdown in ("# Rules", "# Newer rules"):
        saved = await owner.client.put(path, json={"markdown": markdown})
        assert saved.status_code == 200, saved.text
        published = await owner.client.post(f"{path}/versions", json={"note": markdown})
        assert published.status_code == 201, published.text
    return {"project_id": project_id}, None


async def _an_archived_project(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    return {"project_id": await _make_project(owner, archived=True)}, None


PROJECTS = "/api/organisations/{organisation_id}/projects"


async def _an_upload_to_start(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    return {"project_id": await _make_project(owner)}, {"filename": "a.md", "size_bytes": 3}


async def _an_uploaded_file(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    project_id = await _make_project(owner)
    started = await documents.start_upload(owner, project_id, "a.md", 3)
    ticket = started.json()
    await documents.put_to_memory_store(
        documents.app_of(owner), ticket["url"], b"abc", ticket["content_type"]
    )
    return {"project_id": project_id}, {"upload_id": ticket["upload_id"]}


async def _a_document(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    project_id = await _make_project(owner)
    document = await documents.upload(documents.app_of(owner), owner, project_id, "a.md", b"abc")
    return {"project_id": project_id, "document_id": document["id"]}, None


async def _a_failed_document(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    project_id = await _make_project(owner)
    app = documents.app_of(owner)
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")
    document = await documents.upload(app, owner, project_id, "a.md", b"abc")
    app.state.ingestion.converter.failure = None
    return {"project_id": project_id, "document_id": document["id"]}, None


async def _a_new_quota(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    return {"project_id": await _make_project(owner)}, {"document_quota": 10}


async def _an_embedding_model_choice(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    return {"project_id": await _make_project(owner)}, {"model_id": "multilingual-e5-small"}


async def _a_probe(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    return {"project_id": await _make_project(owner)}, {"query": "annual leave"}


async def _a_document_and_its_next_edition(
    owner: SignedUpMember, add_member: MemberFactory
) -> Prepared:
    path, _ = await _a_document(owner, add_member)
    started = await documents.start_upload(owner, path["project_id"], "b.md", 3)
    ticket = started.json()
    await documents.put_to_memory_store(
        documents.app_of(owner), ticket["url"], b"xyz", ticket["content_type"]
    )
    return path, {"upload_id": ticket["upload_id"]}


async def _a_new_tag(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    return {"project_id": await _make_project(owner)}, {"name": f"Tag {uuid.uuid4().hex[:8]}"}


async def _make_tag(owner: SignedUpMember, project_id: str) -> str:
    response = await owner.client.post(
        f"{documents.project_path(owner, project_id)}/tags", json={"name": "Isolation"}
    )
    assert response.status_code == 201, response.text
    tag_id: str = response.json()["id"]
    return tag_id


async def _a_tag(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    project_id = await _make_project(owner)
    tag_id = await _make_tag(owner, project_id)
    return {"project_id": project_id, "tag_id": tag_id}, {"name": "Renamed"}


async def _a_document_and_tag(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    params, _ = await _a_document(owner, add_member)
    tag_id = await _make_tag(owner, params["project_id"])
    return params, {"tag_ids": [tag_id]}


async def _documents_to_bulk_tag(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    params, body = await _a_document_and_tag(owner, add_member)
    assert body is not None
    return {"project_id": params["project_id"]}, {
        "document_ids": [params["document_id"]],
        "add": body["tag_ids"],
    }


TAG = PROJECTS + "/{project_id}/tags/{tag_id}"


async def _new_agent_body(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    return {"project_id": await _make_project(owner)}, {"name": "Isolation Agent"}


async def _an_agent(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    params, body = await _new_agent_body(owner, add_member)
    created = await owner.client.post(
        PROJECTS.format(organisation_id=owner.organisation_id) + f"/{params['project_id']}/agents",
        json=body,
    )
    assert created.status_code == 201, created.text
    return params | {"agent_id": created.json()["id"]}, None


async def _an_agent_draft(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    params, _ = await _an_agent(owner, add_member)
    return params, {"retrieval": {"top_k": 3}}


async def _a_playground_conversation(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    params, _ = await _an_agent(owner, add_member)
    started = await owner.client.post(
        _AGENT.format(organisation_id=owner.organisation_id, **params) + "/playground/conversations"
    )
    assert started.status_code == 201, started.text
    return params | {"conversation_id": started.json()["id"]}, None


async def _a_playground_question(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    # Answering needs a Default Model; the gateway's fake chat model answers.
    params, body = await _a_chat_model_choice(owner, add_member)
    response = await owner.client.put(
        f"/api/organisations/{owner.organisation_id}/default-model", json=body
    )
    assert response.status_code == 200, response.text
    params, _ = await _a_playground_conversation(owner, add_member)
    return params, {"content": "Hello?"}


async def _a_playground_answer(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    params, body = await _a_playground_question(owner, add_member)
    asked = await owner.client.post(
        _CONVERSATION.format(organisation_id=owner.organisation_id, **params) + "/messages",
        json=body,
    )
    assert asked.status_code == 200, asked.text
    conversation = await owner.client.get(
        _CONVERSATION.format(organisation_id=owner.organisation_id, **params)
    )
    return params | {"message_id": conversation.json()["messages"][-1]["id"]}, None


_AGENT = PROJECTS + "/{project_id}/agents/{agent_id}"
_CONVERSATION = _AGENT + "/playground/conversations/{conversation_id}"


# Routes that act on one Project. They are also checked at the Project level below.
PROJECT_SCOPED_ROUTES = [
    ScopedRoute("GET", PROJECTS + "/{project_id}", EDITOR, _a_project),
    ScopedRoute("PATCH", PROJECTS + "/{project_id}", EDITOR, _a_project_to_rename),
    ScopedRoute("POST", PROJECTS + "/{project_id}/archive", EDITOR, _a_project),
    ScopedRoute("POST", PROJECTS + "/{project_id}/restore", OWNER, _an_archived_project),
    ScopedRoute("GET", PROJECTS + "/{project_id}/instructions", EDITOR, _a_project),
    ScopedRoute("PUT", PROJECTS + "/{project_id}/instructions", EDITOR, _instructions_to_save),
    ScopedRoute("GET", PROJECTS + "/{project_id}/instructions/versions", EDITOR, _a_project),
    ScopedRoute(
        "POST", PROJECTS + "/{project_id}/instructions/versions", EDITOR, _instructions_to_publish
    ),
    ScopedRoute(
        "POST", PROJECTS + "/{project_id}/instructions/revert", EDITOR, _instructions_to_revert
    ),
    ScopedRoute("POST", PROJECTS + "/{project_id}/uploads", EDITOR, _an_upload_to_start),
    ScopedRoute("POST", PROJECTS + "/{project_id}/documents", EDITOR, _an_uploaded_file),
    ScopedRoute("GET", PROJECTS + "/{project_id}/documents", EDITOR, _a_project),
    ScopedRoute("GET", PROJECTS + "/{project_id}/documents/statuses", EDITOR, _a_project),
    ScopedRoute("GET", PROJECTS + "/{project_id}/documents/{document_id}", EDITOR, _a_document),
    ScopedRoute(
        "GET", PROJECTS + "/{project_id}/documents/{document_id}/download", EDITOR, _a_document
    ),
    ScopedRoute(
        "GET", PROJECTS + "/{project_id}/documents/{document_id}/chunks", EDITOR, _a_document
    ),
    ScopedRoute("GET", PROJECTS + "/{project_id}/uploads/limits", EDITOR, _a_project),
    ScopedRoute("PUT", PROJECTS + "/{project_id}/document-quota", OWNER, _a_new_quota),
    ScopedRoute(
        "POST",
        PROJECTS + "/{project_id}/documents/{document_id}/retry",
        EDITOR,
        _a_failed_document,
    ),
    ScopedRoute(
        "POST", PROJECTS + "/{project_id}/documents/{document_id}/retry", EDITOR, _a_document
    ),
    ScopedRoute(
        "PUT", PROJECTS + "/{project_id}/embedding-model", EDITOR, _an_embedding_model_choice
    ),
    ScopedRoute("POST", PROJECTS + "/{project_id}/retrieval-probe", EDITOR, _a_probe),
    ScopedRoute("DELETE", PROJECTS + "/{project_id}/documents/{document_id}", EDITOR, _a_document),
    ScopedRoute(
        "POST",
        PROJECTS + "/{project_id}/documents/{document_id}/editions",
        EDITOR,
        _a_document_and_its_next_edition,
    ),
    ScopedRoute("GET", PROJECTS + "/{project_id}/tags", EDITOR, _a_project),
    ScopedRoute("POST", PROJECTS + "/{project_id}/tags", EDITOR, _a_new_tag),
    ScopedRoute("PATCH", TAG, EDITOR, _a_tag),
    ScopedRoute("DELETE", TAG, EDITOR, _a_tag),
    ScopedRoute(
        "PUT",
        PROJECTS + "/{project_id}/documents/{document_id}/tags",
        EDITOR,
        _a_document_and_tag,
    ),
    ScopedRoute("POST", PROJECTS + "/{project_id}/documents/tags", EDITOR, _documents_to_bulk_tag),
    ScopedRoute("GET", PROJECTS + "/{project_id}/agents", EDITOR, _a_project),
    ScopedRoute("POST", PROJECTS + "/{project_id}/agents", EDITOR, _new_agent_body),
    ScopedRoute("GET", _AGENT, EDITOR, _an_agent),
    ScopedRoute("PUT", _AGENT + "/draft", EDITOR, _an_agent_draft),
    ScopedRoute("POST", _AGENT + "/playground/conversations", EDITOR, _an_agent),
    ScopedRoute("GET", _CONVERSATION, EDITOR, _a_playground_conversation),
    ScopedRoute("POST", _CONVERSATION + "/messages", EDITOR, _a_playground_question),
    ScopedRoute(
        "GET", _CONVERSATION + "/messages/{message_id}/trace", EDITOR, _a_playground_answer
    ),
]


async def _policy_left_off(owner: SignedUpMember, add_member: MemberFactory) -> Prepared:
    # Leaving the policy off needs no MFA, so any Owner can call it.
    return {}, {"require_mfa": False}


ORGANISATION_SCOPED_ROUTES = [
    ScopedRoute("GET", PROJECTS, EDITOR),
    ScopedRoute("POST", PROJECTS, EDITOR, _new_project_body),
    *PROJECT_SCOPED_ROUTES,
    ScopedRoute("GET", "/api/organisations/{organisation_id}", EDITOR),
    ScopedRoute("PUT", "/api/organisations/{organisation_id}/mfa-policy", OWNER, _policy_left_off),
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
    ScopedRoute("GET", "/api/organisations/{organisation_id}/credentials", EDITOR),
    ScopedRoute(
        "POST", "/api/organisations/{organisation_id}/credentials", OWNER, _new_credential_body
    ),
    ScopedRoute(
        "POST", "/api/organisations/{organisation_id}/credentials/bedrock", OWNER, _new_bedrock_body
    ),
    ScopedRoute("GET", "/api/organisations/{organisation_id}/bedrock-setup", OWNER),
    ScopedRoute("GET", _CREDENTIAL, EDITOR, _a_credential),
    ScopedRoute("POST", f"{_CREDENTIAL}/check", OWNER, _a_credential),
    ScopedRoute("POST", f"{_CREDENTIAL}/rotate", OWNER, _a_credential),
    ScopedRoute("DELETE", _CREDENTIAL, OWNER, _a_credential),
    ScopedRoute("GET", f"{_CREDENTIAL}/models/{{capability}}", EDITOR, _a_credential_to_list),
    ScopedRoute("GET", f"{_CREDENTIAL}/prices", EDITOR, _a_credential),
    ScopedRoute("PUT", f"{_CREDENTIAL}/prices", OWNER, _a_price_override),
    ScopedRoute("GET", "/api/organisations/{organisation_id}/default-model", EDITOR),
    ScopedRoute(
        "PUT", "/api/organisations/{organisation_id}/default-model", OWNER, _a_chat_model_choice
    ),
    ScopedRoute("GET", "/api/organisations/{organisation_id}/embedding-models", EDITOR),
    ScopedRoute("GET", "/api/organisations/{organisation_id}/theme", EDITOR),
    ScopedRoute("PUT", "/api/organisations/{organisation_id}/theme", OWNER, _a_theme),
    ScopedRoute("POST", THEME_IMAGE + "/uploads", OWNER, _a_theme_image_to_start),
    ScopedRoute("PUT", THEME_IMAGE, OWNER, _an_uploaded_theme_image),
    ScopedRoute("DELETE", THEME_IMAGE, OWNER, _a_theme_image),
    ScopedRoute("GET", THEME_IMAGE, EDITOR, _a_theme_image),
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
    """Whether the path names a resource by ID. ``{kind}`` (a Theme image) or ``{capability}``
    only choose among things every Organisation has."""
    return "_id}" in route.path.replace("{organisation_id}", "")


@pytest.mark.parametrize("route", ORGANISATION_SCOPED_ROUTES, ids=str)
@pytest.mark.parametrize("active", ["own", "other"])
async def test_a_member_of_two_organisations_cannot_reach_a_third(
    route: ScopedRoute,
    active: str,
    two_organisations: TwoOrganisations,
    tenant_factory: TenantFactory,
    member_factory: MemberFactory,
) -> None:
    member, other = two_organisations.member, two_organisations.other
    await _switch(member, member.organisation_id if active == "own" else other.organisation_id)
    third = await tenant_factory()
    prepared = await route.prepare(third, member_factory)

    response = await _call(member.client, route, third.organisation_id, prepared)

    assert (response.status_code, response.json()) == (404, {"detail": "Not found"})


@pytest.mark.parametrize(
    "route", [r for r in ORGANISATION_SCOPED_ROUTES if _has_resource(r)], ids=str
)
async def test_one_organisations_resources_are_not_found_through_the_members_other_organisation(
    route: ScopedRoute, two_organisations: TwoOrganisations, member_factory: MemberFactory
) -> None:
    member, other = two_organisations.member, two_organisations.other
    # The resource belongs to the other Organisation, which is also the active one.
    prepared = await route.prepare(other, member_factory)
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


# Project-level isolation. Every route that acts on one Project finds it only inside the
# Organisation in its path, even for a Member who belongs to both Organisations, and an
# unknown Project answers exactly as another Organisation's does.


@pytest.mark.parametrize("route", PROJECT_SCOPED_ROUTES, ids=str)
async def test_a_project_is_not_found_through_another_organisation_of_the_same_member(
    route: ScopedRoute, two_organisations: TwoOrganisations, member_factory: MemberFactory
) -> None:
    member, other = two_organisations.member, two_organisations.other
    # The Project belongs to ``member``'s own Organisation; they are an Owner of both.
    prepared = await route.prepare(member, member_factory)
    params, body = prepared
    unknown_project = {**params, "project_id": str(uuid.uuid4())}

    crossed = await _call(member.client, route, other.organisation_id, prepared)
    unknown = await _call(member.client, route, other.organisation_id, (unknown_project, body))
    through_its_own = await _call(member.client, route, member.organisation_id, prepared)

    assert (crossed.status_code, crossed.json()) == (404, {"detail": "Not found"})
    assert (unknown.status_code, unknown.json()) == (crossed.status_code, crossed.json())
    assert through_its_own.status_code < 400, through_its_own.text


async def test_each_organisation_lists_only_its_own_projects_for_a_member_of_both(
    two_organisations: TwoOrganisations,
) -> None:
    member, other = two_organisations.member, two_organisations.other
    own = await _make_project(member)
    others = await _make_project(other)
    own_archived = await _make_project(member, archived=True)
    others_archived = await _make_project(other, archived=True)

    seen = {}
    for organisation_id in (member.organisation_id, other.organisation_id):
        path = PROJECTS.format(organisation_id=organisation_id)
        active = (await member.client.get(path)).json()
        archived = (await member.client.get(path, params={"archived": "true"})).json()
        seen[organisation_id] = ({p["id"] for p in active}, {p["id"] for p in archived})

    assert seen == {
        member.organisation_id: ({own}, {own_archived}),
        other.organisation_id: ({others}, {others_archived}),
    }


def test_every_project_route_is_in_the_project_isolation_test() -> None:
    """New routes under a Project must be added to PROJECT_SCOPED_ROUTES."""
    listed = {(r.method, r.path) for r in PROJECT_SCOPED_ROUTES}

    found = {
        (method.upper(), path)
        for path, operations in create_app().openapi()["paths"].items()
        if "{project_id}" in path
        for method in operations
    }

    assert found == listed
