"""API seam: reverting an Agent. An Editor moves the Agent's Live Version back one step in its
Live History, which restores both its configuration and the Instructions it was pinned to.
Everything is observed through the API, including the Live History and the Audit Events."""

import asyncio
import itertools
import json
import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.agents.versions_api import REVERT_TARGET_INVALID
from app.runtime.prompt import preamble
from tests.agents import (
    FULL_DEFAULT_DRAFT,
    agents_path,
    answer_with,
    create_agent,
    save_draft,
    use_default_model,
)
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project
from tests.integration.test_agent_archive import archive as archive_agent
from tests.integration.test_agent_versions import (
    agent,
    knowledgeable_project,
    live_history,
    number,
    published,
    serve,
    versions,
)
from tests.integration.test_playground import echo
from tests.integration.test_project_instructions_versions import published as instructions
from tests.integration.test_projects import archive as archive_project
from tests.integration.test_provider_credentials import (
    OPENAI_KEY,
    added,
    audit_events,
    credentials_path,
)

NOTHING_TO_REVERT = "There's no earlier Live Version to revert to."


async def revert(member: SignedUpMember, project_id: str, agent_id: str) -> httpx.Response:
    return await member.client.post(agents_path(member, project_id, agent_id, "revert"))


async def reverted(member: SignedUpMember, project_id: str, agent_id: str) -> dict[str, Any]:
    response = await revert(member, project_id, agent_id)
    assert response.status_code == 200, response.text
    version: dict[str, Any] = response.json()
    return version


async def live_number(member: SignedUpMember, project_id: str, agent_id: str) -> int | None:
    live = (await agent(member, project_id, agent_id))["live_version"]
    return None if live is None else int(live["number"])


# The Live History rule. Each case is a sequence of actions (P publishes, R reverts) and the
# Live Version number after each one; "-" marks a revert refused because there's nothing to
# revert to, which leaves Live where it was.
@pytest.mark.parametrize(
    ("actions", "expected"),
    [
        ("R", "-"),
        ("P R", "1 -"),
        ("P P R", "1 2 1"),
        ("P P R R", "1 2 1 -"),
        # publish → revert → revert follows the history back rather than toggling.
        ("P P P R R", "1 2 3 2 1"),
        ("P P P R R R", "1 2 3 2 1 -"),
        # A Version published and then reverted is skipped: v3 went Live from v1.
        ("P P R P R", "1 2 1 3 1"),
        ("P P R P R R", "1 2 1 3 1 -"),
        ("P P P R P R R", "1 2 3 2 4 2 1"),
        ("P P P R R P P R R R", "1 2 3 2 1 4 5 4 1 -"),
    ],
)
async def test_revert_follows_the_live_history(
    owner: SignedUpMember, actions: str, expected: str
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]

    seen = []
    for action in actions.split():
        if action == "P":
            await published(owner, project_id, agent_id)
            seen.append(str(await live_number(owner, project_id, agent_id)))
            continue
        response = await revert(owner, project_id, agent_id)
        if response.status_code == 409:
            assert response.json()["detail"] == NOTHING_TO_REVERT
            seen.append("-")
        else:
            assert response.status_code == 200, response.text
            assert await live_number(owner, project_id, agent_id) == response.json()["number"]
            seen.append(str(response.json()["number"]))

    assert " ".join(seen) == expected
    # Every publish and every revert that happened is in the Live History, in order.
    history = await live_history(owner, project_id, agent_id)
    moves = [a for a, e in zip(actions.split(), expected.split(), strict=True) if e != "-"]
    assert [e["action"] for e in reversed(history)] == [
        "publish" if a == "P" else "revert" for a in moves
    ]
    for newer, older in itertools.pairwise(history):
        assert newer["from_version"] == older["to_version"]


# What a revert restores


async def test_revert_restores_the_earlier_config_and_its_pinned_instructions(
    app: FastAPI, owner: SignedUpMember
) -> None:
    """Driven through the serving module (the runtime contract spec 06 serves through) with the
    echoing ``FunctionModel``: the earlier prompt, model and pinned Instructions reach the model
    again, and the Draft is left alone."""
    project_id = await knowledgeable_project(app, owner)
    built = answer_with(app, echo)
    credential_id = await use_default_model(owner)
    created = await create_agent(owner, project_id)
    agent_id = created["id"]
    first_rules = await instructions(owner, project_id, "First rules.", "Rules")
    await save_draft(owner, project_id, agent_id, {"behaviour": {"system_prompt": "First prompt."}})
    first = await published(owner, project_id, agent_id)
    await instructions(owner, project_id, "Second rules.", "Newer")
    newer_model = {"credential_id": credential_id, "model": "gpt-4.1"}
    second_draft = {"behaviour": {"system_prompt": "Second prompt.", "model": newer_model}}
    await save_draft(owner, project_id, agent_id, second_draft)
    second = await published(owner, project_id, agent_id)
    reply, attribution = await serve(app, created["public_id"], "How much leave?")
    assert [part[2] for part in json.loads(reply)[1:3]] == ["Second rules.", "Second prompt."]
    assert (attribution["agent_version_id"], built[-1]) == (second["id"], "openai:gpt-4.1")

    back = await reverted(owner, project_id, agent_id)

    assert back == first
    assert back["instructions_version"] == {"id": first_rules["id"], "number": 1}
    reply, attribution = await serve(app, created["public_id"], "How much leave?")
    assert [part[2] for part in json.loads(reply)[:3]] == [
        preamble("{canary}"),
        "First rules.",
        "First prompt.",
    ]
    assert attribution == {
        "config_source": "version",
        "agent_version_id": first["id"],
        "is_playground": False,
    }
    assert built[-1] == "openai:gpt-4.1-mini"
    # The Draft still holds the later edits; only what Visitors are served moved back.
    draft = (await agent(owner, project_id, agent_id))["draft"]
    assert draft["behaviour"]["system_prompt"] == "Second prompt."
    assert draft["behaviour"]["model"] == newer_model


# The Live History and the Audit log


async def test_a_revert_is_written_to_the_live_history(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    first = await published(owner, project_id, agent_id)
    second = await published(owner, project_id, agent_id)

    await reverted(editor, project_id, agent_id)

    history = await live_history(owner, project_id, agent_id)
    assert [
        (e["from_version"], e["to_version"], e["action"], e["actor"], e["bulk_operation_id"])
        for e in history
    ] == [
        (
            number(second),
            number(first),
            "revert",
            {"id": editor.member_id, "name": editor.name},
            None,
        ),
        (
            number(first),
            number(second),
            "publish",
            {"id": owner.member_id, "name": owner.name},
            None,
        ),
        (None, number(first), "publish", {"id": owner.member_id, "name": owner.name}, None),
    ]
    # Reverting adds no Version.
    assert [v["number"] for v in (await versions(owner, project_id, agent_id))["versions"]] == [
        2,
        1,
    ]


async def test_a_revert_is_recorded_as_an_audit_event(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    pinned = await instructions(owner, project_id, "Be kind.", "Rules")
    first = await published(owner, project_id, agent_id)
    second = await published(owner, project_id, agent_id)
    third = await published(owner, project_id, agent_id, instructions_version_id=None)
    await reverted(owner, project_id, agent_id)

    await reverted(editor, project_id, agent_id)

    events = await audit_events(owner, "agent.reverted")
    target = {"type": "agent", "id": agent_id}
    pinned_v1 = {"version_id": pinned["id"], "number": 1}
    assert [(e["actor"]["id"], e["target"], e["before"], e["after"]) for e in events] == [
        (
            editor.member_id,
            target,
            {"live_version": {"version_id": second["id"], "number": 2}},
            {
                "live_version": {
                    "version_id": first["id"],
                    "number": 1,
                    "instructions_version": pinned_v1,
                }
            },
        ),
        (
            owner.member_id,
            target,
            {"live_version": {"version_id": third["id"], "number": 3}},
            {
                "live_version": {
                    "version_id": second["id"],
                    "number": 2,
                    "instructions_version": pinned_v1,
                }
            },
        ),
    ]


# Refusals


async def test_nothing_to_revert_to_is_refused_and_changes_nothing(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    never_published = (await create_agent(owner, project_id))["id"]
    once = (await create_agent(owner, project_id, "FAQ"))["id"]
    await published(owner, project_id, once)
    before = await live_history(owner, project_id, once)

    responses = [
        await revert(owner, project_id, never_published),
        await revert(owner, project_id, once),
    ]

    assert [(r.status_code, r.json()["detail"]) for r in responses] == [
        (409, NOTHING_TO_REVERT)
    ] * 2
    assert await live_number(owner, project_id, never_published) is None
    assert await live_number(owner, project_id, once) == 1
    assert await live_history(owner, project_id, never_published) == []
    assert await live_history(owner, project_id, once) == before
    assert await audit_events(owner, "agent.reverted") == []


async def test_an_archived_agent_or_project_cannot_be_reverted(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    other_id = (await create_agent(owner, project_id, "FAQ"))["id"]
    for created in (agent_id, other_id):
        await published(owner, project_id, created)
        await published(owner, project_id, created)
    assert (await archive_agent(owner, project_id, agent_id)).status_code == 200

    archived_agent = await revert(owner, project_id, agent_id)
    assert (await archive_project(owner, project_id)).status_code == 200
    archived_project = await revert(owner, project_id, other_id)

    assert archived_agent.status_code == 409
    assert archived_agent.json()["detail"] == "This Agent is archived. An Owner can restore it."
    assert archived_project.status_code == 409
    assert "archived" in archived_project.json()["detail"]
    assert await audit_events(owner, "agent.reverted") == []


async def test_revert_is_not_found_outside_the_organisation(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    stranger = await tenant_factory()
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await published(owner, project_id, agent_id)
    await published(owner, project_id, agent_id)
    stranger_path = f"/api/organisations/{owner.organisation_id}/projects/{project_id}/agents"

    responses = [
        await revert(owner, project_id, str(uuid.uuid4())),
        await owner.client.post(
            f"/api/organisations/{owner.organisation_id}/projects/{uuid.uuid4()}/agents/"
            f"{agent_id}/revert"
        ),
        await stranger.client.post(f"{stranger_path}/{agent_id}/revert"),
    ]

    assert [r.status_code for r in responses] == [404] * len(responses)
    assert await live_number(owner, project_id, agent_id) == 2


async def test_a_version_whose_credential_is_gone_cant_be_made_live_again(
    owner: SignedUpMember,
) -> None:
    """Only the Draft and the Live Version keep their credentials, so an earlier Version's
    credential can be deleted; reverting onto it would serve a configuration that can't run."""
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY)
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    model = {"credential_id": openai["id"], "model": "gpt-4.1"}
    await save_draft(owner, project_id, agent_id, {"behaviour": {"model": model}})
    await published(owner, project_id, agent_id)
    await save_draft(owner, project_id, agent_id, FULL_DEFAULT_DRAFT)
    await published(owner, project_id, agent_id)
    deleted = await owner.client.delete(credentials_path(owner.organisation_id, openai["id"]))
    assert deleted.status_code == 204, deleted.text

    refused = await revert(owner, project_id, agent_id)

    assert refused.status_code == 409
    assert refused.json()["detail"] == REVERT_TARGET_INVALID
    assert await live_number(owner, project_id, agent_id) == 2
    assert await audit_events(owner, "agent.reverted") == []


# Concurrency


async def test_concurrent_reverts_each_step_back_once(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    """Real Postgres, parallel requests: the Agent row lock queues them, so each revert sees the
    Live Version the one before it left and nothing is skipped or repeated."""
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    for _ in range(4):
        await published(owner, project_id, agent_id)

    responses = await asyncio.gather(
        *(revert(member, project_id, agent_id) for member in [owner, editor] * 2)
    )

    assert sorted(r.status_code for r in responses) == [200, 200, 200, 409]
    assert sorted(r.json()["number"] for r in responses if r.status_code == 200) == [1, 2, 3]
    assert await live_number(owner, project_id, agent_id) == 1
    history = await live_history(owner, project_id, agent_id)
    assert [(e["from_version"]["number"], e["to_version"]["number"]) for e in history[:3]] == [
        (2, 1),
        (3, 2),
        (4, 3),
    ]
