"""API seam: an archived Agent's Operational Settings, and those of an Agent in an archived
Project, can be read but not changed, like every other write to an archived Agent (AGT-F4)."""

from typing import Any

import pytest

from tests.agents import create_agent
from tests.conftest import MemberFactory, SignedUpMember
from tests.documents import create_project
from tests.integration.test_agent_archive import archive as archive_agent
from tests.integration.test_agent_archive import restore as restore_agent
from tests.integration.test_bedrock_credentials import audit_events
from tests.integration.test_embed import settings_path
from tests.integration.test_projects import archive as archive_project

CHANGED = "agent.operational_settings_changed"
AGENT_ARCHIVED = "This Agent is archived. An Owner can restore it."


@pytest.mark.parametrize("archived", ["agent", "project"])
async def test_an_editor_cant_change_the_operational_settings_of_an_archived_agent(
    owner: SignedUpMember, member_factory: MemberFactory, archived: str
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    agent: dict[str, Any] = await create_agent(owner, project_id)
    path = settings_path(owner, project_id, agent["id"])
    before = (await owner.client.get(path)).json()
    if archived == "agent":
        assert (await archive_agent(owner, project_id, agent["id"])).status_code == 200
    else:
        assert (await archive_project(owner, project_id)).status_code == 200

    response = await editor.client.patch(
        settings_path(editor, project_id, agent["id"]),
        json={"allowed_origins": ["https://evil.example"], "unavailable_text": "Gone."},
    )

    assert response.status_code == 409, response.text
    if archived == "agent":
        assert response.json()["detail"] == AGENT_ARCHIVED
    read = await editor.client.get(settings_path(editor, project_id, agent["id"]))
    assert read.status_code == 200, read.text
    assert read.json() == before
    assert await audit_events(owner, CHANGED) == []


async def test_a_restored_agent_keeps_the_settings_it_had_when_archived(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent: dict[str, Any] = await create_agent(owner, project_id)
    path = settings_path(owner, project_id, agent["id"])
    before = (await owner.client.get(path)).json()
    await archive_agent(owner, project_id, agent["id"])
    await owner.client.patch(path, json={"allowed_origins": ["https://evil.example"]})

    assert (await restore_agent(owner, project_id, agent["id"])).status_code == 200

    assert (await owner.client.get(path)).json() == before
