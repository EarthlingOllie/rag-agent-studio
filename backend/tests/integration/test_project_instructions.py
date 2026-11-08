"""API seam: an Editor writes a Project's Instructions, the one markdown Draft every Agent in
the Project follows. Everything is observed through the API, including the Audit Events."""

import uuid

import pytest

from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project, project_path
from tests.integration.test_provider_credentials import audit_events

INSTRUCTIONS = (
    "# House rules\n\n"
    "- Answer in **British English**.\n"
    "- Never quote salaries.\n\n"
    "```\nescalate: hr@example.com\n```\n"
)


def instructions_path(member: SignedUpMember, project_id: str) -> str:
    return f"{project_path(member, project_id)}/instructions"


async def test_a_new_projects_instructions_are_empty(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)

    response = await owner.client.get(instructions_path(owner, project_id))

    assert response.status_code == 200, response.text
    assert response.json()["markdown"] == ""


async def test_an_editor_saves_the_instructions_and_they_read_back_exactly(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(editor)

    saved = await editor.client.put(
        instructions_path(editor, project_id), json={"markdown": INSTRUCTIONS}
    )

    assert saved.status_code == 200, saved.text
    assert saved.json()["markdown"] == INSTRUCTIONS
    fetched = await owner.client.get(instructions_path(owner, project_id))
    assert fetched.json()["markdown"] == INSTRUCTIONS


async def test_instructions_edits_are_recorded_as_audit_events(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(editor)
    path = instructions_path(editor, project_id)

    await editor.client.put(path, json={"markdown": "Be kind."})
    await editor.client.put(path, json={"markdown": INSTRUCTIONS})
    # Saving the same text again changes nothing, so nothing is recorded.
    await editor.client.put(path, json={"markdown": INSTRUCTIONS})

    events = await audit_events(owner, "project.instructions_updated")
    # Newest first.
    assert [(e["before"], e["after"]) for e in events] == [
        ({"instructions": "Be kind."}, {"instructions": INSTRUCTIONS}),
        ({"instructions": ""}, {"instructions": "Be kind."}),
    ]
    assert {e["actor"]["id"] for e in events} == {editor.member_id}
    assert {(e["target"]["type"], e["target"]["id"]) for e in events} == {("project", project_id)}


async def test_instructions_can_be_cleared(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    path = instructions_path(owner, project_id)
    await owner.client.put(path, json={"markdown": INSTRUCTIONS})

    cleared = await owner.client.put(path, json={"markdown": ""})

    assert cleared.json()["markdown"] == ""


@pytest.mark.parametrize("body", [{"markdown": "x" * 20_001}, {}, {"markdown": 3}])
async def test_invalid_instructions_are_refused(
    owner: SignedUpMember, body: dict[str, object]
) -> None:
    project_id = await create_project(owner)

    response = await owner.client.put(instructions_path(owner, project_id), json=body)

    assert response.status_code == 422


async def test_an_archived_projects_instructions_are_read_only(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    path = instructions_path(owner, project_id)
    await owner.client.put(path, json={"markdown": INSTRUCTIONS})
    archived = await owner.client.post(f"{project_path(owner, project_id)}/archive")
    assert archived.status_code == 200, archived.text

    saved = await owner.client.put(path, json={"markdown": "Changed"})

    assert saved.status_code == 409
    assert saved.json() == {"detail": "This Project is archived. An Owner can restore it."}
    assert (await owner.client.get(path)).json()["markdown"] == INSTRUCTIONS


async def test_instructions_are_not_found_outside_their_organisation(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    project_id = await create_project(owner)
    stranger = await tenant_factory()
    missing = str(uuid.uuid4())

    for member, path in [
        (owner, instructions_path(owner, missing)),
        (stranger, instructions_path(stranger, project_id)),
    ]:
        read = await member.client.get(path)
        written = await member.client.put(path, json={"markdown": "Mine now"})
        assert (read.status_code, written.status_code) == (404, 404), path
        assert read.json() == {"detail": "Not found"}
    # The stranger can't reach the Owner's Organisation at all.
    response = await stranger.client.get(instructions_path(owner, project_id))
    assert response.status_code == 404
    assert (await owner.client.get(instructions_path(owner, project_id))).json()["markdown"] == ""
