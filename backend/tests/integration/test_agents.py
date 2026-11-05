"""API seam: an Editor creates Agents in a Project and saves an Agent's Draft (its AgentConfig).
Everything is observed through the API."""

import re
import uuid

import pytest

from tests.agents import agents_path, create_agent, save_draft
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project, project_path
from tests.integration.test_provider_credentials import audit_events

DEFAULT_DRAFT = {"behaviour": {"system_prompt": ""}, "retrieval": {"top_k": 5}}


async def test_an_editor_creates_an_agent_with_a_public_id_and_a_default_draft(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(editor)

    agent = await create_agent(editor, project_id, "  HR helper  ")

    assert agent["name"] == "HR helper"
    assert agent["project_id"] == project_id
    assert agent["archived_at"] is None
    assert agent["draft"] == DEFAULT_DRAFT
    # Unguessable: a prefix and 24 URL-safe characters (144 random bits), different every time.
    assert re.fullmatch(r"agt_[A-Za-z0-9_-]{24}", agent["public_id"])
    other = await create_agent(editor, project_id, "FAQ")
    assert other["public_id"] != agent["public_id"]
    fetched = await editor.client.get(agents_path(editor, project_id, agent["id"]))
    assert fetched.json() == agent
    # Newest first.
    event = (await audit_events(owner, "agent.created"))[-1]
    assert event["actor"]["id"] == editor.member_id
    assert event["target"] == {"type": "agent", "id": agent["id"]}
    assert event["after"] == {"name": "HR helper", "project_id": project_id}


async def test_a_project_lists_its_agents_and_counts_them(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    other_project_id = await create_project(owner, "Sales")
    first = await create_agent(owner, project_id, "HR helper")
    second = await create_agent(owner, project_id, "Benefits FAQ")
    await create_agent(owner, other_project_id, "Sales helper")

    listed = await owner.client.get(agents_path(owner, project_id))

    assert [agent["id"] for agent in listed.json()] == [first["id"], second["id"]]
    project = await owner.client.get(project_path(owner, project_id))
    assert project.json()["agent_count"] == 2
    projects = await owner.client.get(f"/api/organisations/{owner.organisation_id}/projects")
    assert {p["name"]: p["agent_count"] for p in projects.json()} == {"Handbook": 2, "Sales": 1}


async def test_the_draft_is_saved_and_read_back_exactly(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)
    draft = {
        "behaviour": {"system_prompt": "# Role\n\nAnswer **briefly**.\n\n- Cite the handbook\n"},
        "retrieval": {"top_k": 3},
    }

    saved = await save_draft(owner, project_id, agent["id"], draft)

    assert saved.status_code == 200, saved.text
    assert saved.json()["draft"] == draft
    assert saved.json()["draft_updated_at"] >= agent["draft_updated_at"]
    fetched = await owner.client.get(agents_path(owner, project_id, agent["id"]))
    assert fetched.json()["draft"] == draft


@pytest.mark.parametrize(
    "draft",
    [
        {"retrieval": {"top_k": 0}},
        {"retrieval": {"top_k": 21}},
        {"behaviour": {"system_prompt": "x" * 20_001}},
        {"behaviour": {"system_prompt": "Hi", "temperature": 2}},
        {"unknown_group": {}},
    ],
)
async def test_an_invalid_draft_is_refused(owner: SignedUpMember, draft: dict[str, object]) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)

    refused = await save_draft(owner, project_id, agent["id"], draft)

    assert refused.status_code == 422
    fetched = await owner.client.get(agents_path(owner, project_id, agent["id"]))
    assert fetched.json()["draft"] == DEFAULT_DRAFT


async def test_a_partial_draft_takes_defaults_for_the_rest(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)

    saved = await save_draft(owner, project_id, agent["id"], {"retrieval": {"top_k": 8}})

    assert saved.json()["draft"] == {"behaviour": {"system_prompt": ""}, "retrieval": {"top_k": 8}}


@pytest.mark.parametrize("name", ["", "   ", "x" * 201])
async def test_an_agent_needs_a_name(owner: SignedUpMember, name: str) -> None:
    project_id = await create_project(owner)

    response = await owner.client.post(agents_path(owner, project_id), json={"name": name})

    assert response.status_code == 422


async def test_agents_are_not_found_outside_their_project_and_organisation(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    project_id = await create_project(owner)
    other_project_id = await create_project(owner, "Sales")
    agent = await create_agent(owner, project_id)
    stranger = await tenant_factory()
    stranger_project = await create_project(stranger)
    missing = str(uuid.uuid4())

    for member, path in [
        (owner, agents_path(owner, other_project_id, agent["id"])),
        (owner, agents_path(owner, project_id, missing)),
        (owner, agents_path(owner, missing)),
        (stranger, agents_path(stranger, stranger_project, agent["id"])),
    ]:
        response = await member.client.get(path)
        assert response.status_code == 404, path
        assert response.json() == {"detail": "Not found"}
    for path in [agents_path(owner, missing), agents_path(owner, project_id, missing, "draft")]:
        method = "POST" if path.endswith("agents") else "PUT"
        body = {"name": "x"} if method == "POST" else DEFAULT_DRAFT
        response = await owner.client.request(method, path, json=body)
        assert response.status_code == 404, path
    # Another Organisation's member can't reach the Owner's Project at all.
    response = await stranger.client.get(agents_path(owner, project_id))
    assert response.status_code == 404


async def test_an_archived_projects_agents_cant_be_created_or_changed(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent = await create_agent(owner, project_id)
    archived = await owner.client.post(f"{project_path(owner, project_id)}/archive")
    assert archived.status_code == 200, archived.text

    created = await owner.client.post(agents_path(owner, project_id), json={"name": "FAQ"})
    saved = await save_draft(owner, project_id, agent["id"], DEFAULT_DRAFT)

    assert (created.status_code, saved.status_code) == (409, 409)
    assert created.json() == {"detail": "This Project is archived. An Owner can restore it."}
    # Still readable, so the Project page can show them.
    listed = await owner.client.get(agents_path(owner, project_id))
    assert [a["id"] for a in listed.json()] == [agent["id"]]
