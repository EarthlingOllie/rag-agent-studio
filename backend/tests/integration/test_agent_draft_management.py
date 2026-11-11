"""API seam: managing an Agent's Draft. The Agent says when its Draft has unpublished changes;
an Editor can discard the Draft back to the Live Version or start it from any Version; and a
save made on a Draft someone else has since changed is refused with 409 and the latest Draft,
so nobody silently overwrites a colleague's edits."""

from typing import Any

import httpx
import pytest

from tests.agents import FULL_DEFAULT_DRAFT, agents_path, create_agent, save_draft
from tests.conftest import MemberFactory, SignedUpMember
from tests.documents import create_project
from tests.integration.test_agent_archive import archive as archive_agent
from tests.integration.test_agent_versions import agent, number, published
from tests.integration.test_projects import archive as archive_project
from tests.integration.test_provider_credentials import (
    OPENAI_KEY,
    added,
    audit_events,
    credentials_path,
)

STALE = (
    "Someone else saved this Draft after you opened it. Load their changes, or save yours over "
    "them."
)


async def save(
    member: SignedUpMember,
    project_id: str,
    agent_id: str,
    draft: dict[str, Any],
    base_revision: int,
) -> httpx.Response:
    return await member.client.put(
        agents_path(member, project_id, agent_id, "draft"),
        params={"base_revision": base_revision},
        json=draft,
    )


async def discard(
    member: SignedUpMember, project_id: str, agent_id: str, **params: Any
) -> httpx.Response:
    return await member.client.post(
        agents_path(member, project_id, agent_id, "draft", "discard"), params=params
    )


async def start_from(
    member: SignedUpMember, project_id: str, agent_id: str, version_id: str, **params: Any
) -> httpx.Response:
    return await member.client.post(
        agents_path(member, project_id, agent_id, "draft", "from-version"),
        params=params,
        json={"version_id": version_id},
    )


def prompt(draft: str) -> dict[str, Any]:
    return {"behaviour": {"system_prompt": draft}}


# Unpublished changes


async def test_the_agent_says_when_its_draft_has_unpublished_changes(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    # Never published: not live, and nothing to compare with.
    assert (await agent(owner, project_id, agent_id))["has_unpublished_changes"] is False

    await published(owner, project_id, agent_id)
    assert (await agent(owner, project_id, agent_id))["has_unpublished_changes"] is False

    edited = await save_draft(owner, project_id, agent_id, prompt("New"))
    assert edited.json()["has_unpublished_changes"] is True
    listed = await owner.client.get(agents_path(owner, project_id))
    assert [a["has_unpublished_changes"] for a in listed.json()] == [True]

    # Editing it back to the Live configuration leaves nothing unpublished.
    back = await save_draft(owner, project_id, agent_id, FULL_DEFAULT_DRAFT)
    assert back.json()["has_unpublished_changes"] is False
    await save_draft(owner, project_id, agent_id, prompt("Newer"))
    await published(owner, project_id, agent_id)
    assert (await agent(owner, project_id, agent_id))["has_unpublished_changes"] is False


# Stale saves


async def test_each_save_moves_the_draft_to_its_next_revision(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    created = await create_agent(owner, project_id)
    assert created["draft_revision"] == 1

    first = await save(owner, project_id, created["id"], prompt("One"), base_revision=1)
    assert first.status_code == 200, first.text
    second = await save(owner, project_id, created["id"], prompt("Two"), base_revision=2)
    assert second.status_code == 200, second.text

    assert [first.json()["draft_revision"], second.json()["draft_revision"]] == [2, 3]
    assert (await agent(owner, project_id, created["id"]))["draft_revision"] == 3


async def test_saving_a_stale_draft_is_refused_with_the_latest_draft(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    # Both open revision 1; the Editor saves first.
    theirs = await save(editor, project_id, agent_id, prompt("Theirs"), base_revision=1)
    assert theirs.status_code == 200, theirs.text

    mine = await save(owner, project_id, agent_id, prompt("Mine"), base_revision=1)

    assert mine.status_code == 409, mine.text
    body = mine.json()
    assert body["detail"] == STALE
    assert body["latest"] == theirs.json()
    assert body["latest"]["draft"]["behaviour"]["system_prompt"] == "Theirs"
    current = await agent(owner, project_id, agent_id)
    assert current["draft"]["behaviour"]["system_prompt"] == "Theirs"
    # Saving over theirs on purpose names the latest revision.
    over = await save(owner, project_id, agent_id, prompt("Mine"), base_revision=2)
    assert over.status_code == 200, over.text
    assert over.json()["draft"]["behaviour"]["system_prompt"] == "Mine"


async def test_a_stale_save_is_refused_before_its_settings_are_checked(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await save(owner, project_id, agent_id, prompt("Theirs"), base_revision=1)
    unknown_tag = {"retrieval": {"tag_ids": ["00000000-0000-0000-0000-000000000000"]}}

    stale = await save(owner, project_id, agent_id, unknown_tag, base_revision=1)

    assert stale.status_code == 409, stale.text
    assert (await save(owner, project_id, agent_id, unknown_tag, 2)).status_code == 422


async def test_a_save_without_a_base_revision_replaces_the_draft(owner: SignedUpMember) -> None:
    """Callers that don't track revisions, such as the seed, still save; the Studio always
    sends the revision it edited."""
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await save(owner, project_id, agent_id, prompt("One"), base_revision=1)

    response = await save_draft(owner, project_id, agent_id, prompt("Two"))

    assert response.status_code == 200, response.text
    assert response.json()["draft_revision"] == 3


# Discarding the Draft


async def test_discarding_the_draft_restores_the_live_configuration(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await save_draft(owner, project_id, agent_id, prompt("Live"))
    live = await published(owner, project_id, agent_id)
    edited = await save_draft(owner, project_id, agent_id, prompt("Experiment"))
    revision = edited.json()["draft_revision"]

    response = await discard(editor, project_id, agent_id, base_revision=revision)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["draft"] == live["config"]
    assert body["has_unpublished_changes"] is False
    assert body["draft_revision"] == revision + 1
    assert body["live_version"] == number(live)
    events = await audit_events(owner, "agent.draft_discarded")
    assert [(e["actor"]["id"], e["target"], e["before"], e["after"]) for e in events] == [
        (
            editor.member_id,
            {"type": "agent", "id": agent_id},
            {"draft_revision": revision},
            {"draft_revision": revision + 1, "version": {"version_id": live["id"], "number": 1}},
        )
    ]


async def test_an_agent_that_is_not_live_has_no_draft_to_discard(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await save_draft(owner, project_id, agent_id, prompt("Work in progress"))

    response = await discard(owner, project_id, agent_id)

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == (
        "This Agent has never been published, so it has no Live Version."
    )
    draft = (await agent(owner, project_id, agent_id))["draft"]
    assert draft["behaviour"]["system_prompt"] == "Work in progress"
    assert await audit_events(owner, "agent.draft_discarded") == []


async def test_discarding_a_draft_someone_has_since_changed_is_refused(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await published(owner, project_id, agent_id)
    seen = (await save_draft(owner, project_id, agent_id, prompt("Seen"))).json()
    await save_draft(owner, project_id, agent_id, prompt("Colleague's edit"))

    response = await discard(owner, project_id, agent_id, base_revision=seen["draft_revision"])

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == STALE
    assert response.json()["latest"]["draft"]["behaviour"]["system_prompt"] == "Colleague's edit"


# Starting the Draft from a Version


async def test_starting_the_draft_from_an_earlier_version(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await save_draft(owner, project_id, agent_id, prompt("First"))
    v1 = await published(owner, project_id, agent_id)
    await save_draft(owner, project_id, agent_id, prompt("Second"))
    v2 = await published(owner, project_id, agent_id)
    revision = (await agent(owner, project_id, agent_id))["draft_revision"]

    response = await start_from(editor, project_id, agent_id, v1["id"], base_revision=revision)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["draft"] == v1["config"]
    assert body["draft_revision"] == revision + 1
    # Nothing is published: v2 stays Live, and the Draft now differs from it.
    assert body["live_version"] == number(v2)
    assert body["has_unpublished_changes"] is True
    events = await audit_events(owner, "agent.draft_started_from_version")
    assert [(e["actor"]["id"], e["target"], e["before"], e["after"]) for e in events] == [
        (
            editor.member_id,
            {"type": "agent", "id": agent_id},
            {"draft_revision": revision},
            {"draft_revision": revision + 1, "version": {"version_id": v1["id"], "number": 1}},
        )
    ]


async def test_starting_from_a_version_of_another_agent_is_not_found(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    other = (await create_agent(owner, project_id, "Other"))["id"]
    theirs = await published(owner, project_id, other)

    response = await start_from(owner, project_id, agent_id, theirs["id"])

    assert response.status_code == 404, response.text
    assert (await agent(owner, project_id, agent_id))["draft_revision"] == 1


async def test_starting_from_a_version_someone_has_since_changed_is_refused(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    v1 = await published(owner, project_id, agent_id)
    await save_draft(owner, project_id, agent_id, prompt("Colleague's edit"))

    response = await start_from(owner, project_id, agent_id, v1["id"], base_revision=1)

    assert response.status_code == 409, response.text
    assert response.json()["latest"]["draft_revision"] == 2


async def test_a_version_whose_credential_is_gone_cant_start_the_draft(
    owner: SignedUpMember,
) -> None:
    """A Version keeps the credential it named, but only the Live Version protects it, so an
    older Version's credential may have been deleted. Its settings are checked like a save."""
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY)
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    model = {"credential_id": openai["id"], "model": "gpt-4.1"}
    await save_draft(owner, project_id, agent_id, {"behaviour": {"model": model}})
    v1 = await published(owner, project_id, agent_id)
    await save_draft(owner, project_id, agent_id, FULL_DEFAULT_DRAFT)
    await published(owner, project_id, agent_id)
    assert (
        await owner.client.delete(credentials_path(owner.organisation_id, openai["id"]))
    ).status_code == 204

    response = await start_from(owner, project_id, agent_id, v1["id"])

    assert response.status_code == 422, response.text
    assert [error["loc"] for error in response.json()["detail"]] == [
        ["body", "behaviour", "model", "credential_id"]
    ]
    assert (await agent(owner, project_id, agent_id))["draft"] == FULL_DEFAULT_DRAFT


@pytest.mark.parametrize("archived", ["agent", "project"])
async def test_an_archived_agents_draft_cant_be_discarded_or_started_from_a_version(
    owner: SignedUpMember, archived: str
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    v1 = await published(owner, project_id, agent_id)
    if archived == "agent":
        await archive_agent(owner, project_id, agent_id)
    else:
        await archive_project(owner, project_id)

    for response in (
        await discard(owner, project_id, agent_id),
        await start_from(owner, project_id, agent_id, v1["id"]),
    ):
        assert response.status_code == 409, response.text


async def test_draft_actions_on_an_unknown_agent_are_not_found(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    missing = "00000000-0000-0000-0000-000000000000"

    assert (await discard(owner, project_id, missing)).status_code == 404
    assert (await start_from(owner, project_id, missing, missing)).status_code == 404
