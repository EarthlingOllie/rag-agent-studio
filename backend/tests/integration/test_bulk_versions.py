"""API seam: bulk publish, bulk revert and the Instructions rollout. An Editor rolls a Project
Instructions Version out to several Agents at once (from each Agent's Live config, never its
Draft), reverts several Agents at once, sees which Agents are behind the Current Instructions,
and is offered a bulk revert after reverting the Instructions. Everything is observed through
the API (Agents, Versions, Live History, Audit Events) and, for what Visitors get, through the
serving module with the echoing ``FunctionModel``."""

import json
import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app import audit
from app.agents.bulk import NEVER_PUBLISHED, UNEXPECTED_FAILURE
from app.agents.versions_api import NOTHING_TO_REVERT, REVERT_TARGET_INVALID
from tests.agents import FULL_DEFAULT_DRAFT, agents_path, create_agent, save_draft
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project, project_path
from tests.integration.test_agent_archive import archive as archive_agent
from tests.integration.test_agent_revert import reverted
from tests.integration.test_agent_versions import (
    agent,
    knowledgeable_project,
    live_history,
    published,
    serve,
    versions,
)
from tests.integration.test_project_instructions_versions import published as instructions
from tests.integration.test_project_instructions_versions import revert as revert_instructions
from tests.integration.test_projects import archive as archive_project
from tests.integration.test_provider_credentials import (
    OPENAI_KEY,
    added,
    audit_events,
    credentials_path,
)

AGENT_ARCHIVED = "This Agent is archived. An Owner can restore it."
NOT_FOUND = "Not found."


async def bulk_publish(
    member: SignedUpMember, project_id: str, agent_ids: list[str], version_id: str, **body: Any
) -> httpx.Response:
    return await member.client.post(
        agents_path(member, project_id, "bulk-publish"),
        json={"agent_ids": agent_ids, "instructions_version_id": version_id, **body},
    )


async def bulk_published(
    member: SignedUpMember, project_id: str, agent_ids: list[str], version_id: str, **body: Any
) -> dict[str, Any]:
    response = await bulk_publish(member, project_id, agent_ids, version_id, **body)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


async def bulk_revert(
    member: SignedUpMember, project_id: str, agent_ids: list[str]
) -> httpx.Response:
    return await member.client.post(
        agents_path(member, project_id, "bulk-revert"), json={"agent_ids": agent_ids}
    )


async def bulk_reverted(
    member: SignedUpMember, project_id: str, agent_ids: list[str]
) -> dict[str, Any]:
    response = await bulk_revert(member, project_id, agent_ids)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


async def rollout(member: SignedUpMember, project_id: str) -> dict[str, Any]:
    response = await member.client.get(f"{project_path(member, project_id)}/instructions/rollout")
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def outcomes(result: dict[str, Any]) -> list[tuple[str, str, str | None]]:
    """(name, status, reason) per Agent, in request order."""
    return [(r["name"], r["status"], r["reason"]) for r in result["results"]]


async def named_agents(owner: SignedUpMember, project_id: str, *names: str) -> list[str]:
    return [(await create_agent(owner, project_id, name))["id"] for name in names]


# Bulk publish


async def test_bulk_publish_builds_from_the_live_config_and_the_chosen_instructions(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    """The Draft's edits are not shipped: the new Version is the Live config plus the chosen
    Instructions, and a Visitor gets exactly that (echoing ``FunctionModel``)."""
    editor = await member_factory(owner, "editor")
    project_id = await knowledgeable_project(app, owner)
    created = await create_agent(owner, project_id, "HR helper")
    agent_id = created["id"]
    await instructions(owner, project_id, "First rules.", "Rules")
    await save_draft(owner, project_id, agent_id, {"behaviour": {"system_prompt": "Live prompt."}})
    first = await published(owner, project_id, agent_id)
    await save_draft(owner, project_id, agent_id, {"behaviour": {"system_prompt": "Unreviewed."}})
    second_rules = await instructions(owner, project_id, "Second rules.", "Stricter")

    result = await bulk_published(
        editor, project_id, [agent_id], second_rules["id"], note="Roll out v2"
    )

    uuid.UUID(result["bulk_operation_id"])
    [outcome] = result["results"]
    listed = await versions(owner, project_id, agent_id)
    newest = listed["versions"][0]
    assert outcome == {
        "agent_id": agent_id,
        "name": "HR helper",
        "status": "succeeded",
        "reason": None,
        "live_version": {"id": newest["id"], "number": 2},
        "instructions_version": {"id": second_rules["id"], "number": 2},
    }
    assert listed["live_version_id"] == newest["id"]
    assert newest["config"] == first["config"]
    assert newest["config"]["behaviour"]["system_prompt"] == "Live prompt."
    assert (newest["note"], newest["author"]) == (
        "Roll out v2",
        {"id": editor.member_id, "name": editor.name},
    )
    reply, attribution = await serve(app, created["public_id"], "How much leave?")
    assert [part[2] for part in json.loads(reply)[1:3]] == ["Second rules.", "Live prompt."]
    assert attribution["agent_version_id"] == newest["id"]
    # The Draft keeps its unpublished edits.
    draft = (await agent(owner, project_id, agent_id))["draft"]
    assert draft["behaviour"]["system_prompt"] == "Unreviewed."


async def test_bulk_publish_names_the_instructions_version_when_no_note_is_given(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    [agent_id] = await named_agents(owner, project_id, "HR helper")
    await published(owner, project_id, agent_id)
    rules = await instructions(owner, project_id, "Rules.", "Rules")

    await bulk_published(owner, project_id, [agent_id], rules["id"])

    assert (await versions(owner, project_id, agent_id))["versions"][0]["note"] == (
        "Bulk published with Instructions v1"
    )


async def test_bulk_publish_skips_never_published_agents_and_ones_already_on_the_version(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    live, never, current = await named_agents(owner, project_id, "Live", "Never", "Current")
    await published(owner, project_id, live)
    rules = await instructions(owner, project_id, "Rules.", "Rules")
    await published(owner, project_id, current)

    result = await bulk_published(owner, project_id, [live, never, current], rules["id"])

    assert outcomes(result) == [
        ("Live", "succeeded", None),
        ("Never", "skipped", NEVER_PUBLISHED),
        ("Current", "skipped", "Already Live with Instructions v1."),
    ]
    # A skipped Agent is left exactly as it was: no first Version, nothing new.
    assert (await agent(owner, project_id, never))["live_version"] is None
    assert (await versions(owner, project_id, never))["versions"] == []
    assert len((await versions(owner, project_id, current))["versions"]) == 1


async def test_bulk_results_report_agents_that_failed_and_why(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    outsider = await tenant_factory()
    elsewhere = await create_agent(outsider, await create_project(outsider))
    project_id = await create_project(owner)
    other_project = await create_project(owner)
    in_other_project = await create_agent(owner, other_project)
    live, gone = await named_agents(owner, project_id, "Live", "Gone")
    for agent_id in (live, gone):
        await published(owner, project_id, agent_id)
    rules = await instructions(owner, project_id, "Rules.", "Rules")
    archived = await archive_agent(owner, project_id, gone)
    assert archived.status_code == 200, archived.text
    unknown = str(uuid.uuid4())

    result = await bulk_published(
        owner,
        project_id,
        [gone, elsewhere["id"], in_other_project["id"], unknown, live, live],
        rules["id"],
    )

    # Another Organisation's or Project's Agent is as unknown as one that doesn't exist, and a
    # repeated ID is processed once.
    assert outcomes(result) == [
        ("Gone", "failed", AGENT_ARCHIVED),
        (None, "failed", NOT_FOUND),
        (None, "failed", NOT_FOUND),
        (None, "failed", NOT_FOUND),
        ("Live", "succeeded", None),
    ]
    assert [r["agent_id"] for r in result["results"]] == [
        gone,
        elsewhere["id"],
        in_other_project["id"],
        unknown,
        live,
    ]
    assert (await agent(outsider, elsewhere["project_id"], elsewhere["id"]))["live_version"] is None


async def test_a_failure_on_one_agent_leaves_the_others_committed(
    owner: SignedUpMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each Agent is processed in its own transaction: a forced failure part-way through one
    Agent's publish (after its Version is written) rolls back only that Agent."""
    project_id = await create_project(owner)
    first, broken, last = await named_agents(owner, project_id, "First", "Broken", "Last")
    before = {
        agent_id: await published(owner, project_id, agent_id) for agent_id in (first, broken, last)
    }
    rules = await instructions(owner, project_id, "Rules.", "Rules")
    record = audit.record

    async def failing_for_broken(*args: Any, **kwargs: Any) -> None:
        if kwargs["target"] == audit.AuditTarget("agent", uuid.UUID(broken)):
            raise RuntimeError("Forced failure")
        await record(*args, **kwargs)

    monkeypatch.setattr(audit, "record", failing_for_broken)

    result = await bulk_published(owner, project_id, [first, broken, last], rules["id"])
    monkeypatch.setattr(audit, "record", record)

    assert outcomes(result) == [
        ("First", "succeeded", None),
        ("Broken", "failed", UNEXPECTED_FAILURE),
        ("Last", "succeeded", None),
    ]
    for agent_id in (first, last):
        assert (await agent(owner, project_id, agent_id))["live_version"]["number"] == 2
    assert (await agent(owner, project_id, broken))["live_version"] == {
        "id": before[broken]["id"],
        "number": 1,
    }
    assert [v["number"] for v in (await versions(owner, project_id, broken))["versions"]] == [1]
    assert [e["action"] for e in await live_history(owner, project_id, broken)] == ["publish"]
    bulk_events = await audit_events(owner, "agent.bulk_published")
    assert {e["target"]["id"] for e in bulk_events} == {first, last}


async def test_bulk_publish_is_refused_for_an_unknown_instructions_version_or_an_archived_project(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    outsider = await tenant_factory()
    project_id = await create_project(owner)
    elsewhere = await create_project(owner)
    others = await instructions(owner, elsewhere, "Other rules.", "Other")
    outsiders = await instructions(outsider, await create_project(outsider), "Theirs.", "Theirs")
    [agent_id] = await named_agents(owner, project_id, "HR helper")
    await published(owner, project_id, agent_id)

    for version_id in (others["id"], outsiders["id"], str(uuid.uuid4())):
        response = await bulk_publish(owner, project_id, [agent_id], version_id)
        assert response.status_code == 422, response.text
        assert response.json() == {
            "detail": "That Instructions Version isn't one of this Project's."
        }
    rules = await instructions(owner, project_id, "Rules.", "Rules")
    assert (await archive_project(owner, project_id)).status_code == 200
    archived = await bulk_publish(owner, project_id, [agent_id], rules["id"])
    assert archived.status_code == 409
    assert [v["number"] for v in (await versions(owner, project_id, agent_id))["versions"]] == [1]
    assert await audit_events(owner, "agent.bulk_published") == []


@pytest.mark.parametrize(
    "body",
    [
        {"agent_ids": []},
        {"agent_ids": [str(uuid.uuid4())] * 201},
        {"agent_ids": ["not-a-uuid"]},
        {"agent_ids": [str(uuid.uuid4())], "note": " "},
        {"agent_ids": [str(uuid.uuid4())], "note": "x" * 501},
    ],
)
async def test_bulk_publish_needs_one_to_200_agents_and_a_short_note(
    owner: SignedUpMember, body: dict[str, Any]
) -> None:
    project_id = await create_project(owner)
    rules = await instructions(owner, project_id, "Rules.", "Rules")

    response = await owner.client.post(
        agents_path(owner, project_id, "bulk-publish"),
        json={"instructions_version_id": rules["id"], **body},
    )

    assert response.status_code == 422


async def test_bulk_routes_are_not_found_for_an_unknown_project(owner: SignedUpMember) -> None:
    project_id = str(uuid.uuid4())

    published_ = await bulk_publish(owner, project_id, [str(uuid.uuid4())], str(uuid.uuid4()))
    reverted_ = await bulk_revert(owner, project_id, [str(uuid.uuid4())])
    summary = await owner.client.get(f"{project_path(owner, project_id)}/instructions/rollout")

    for response in (published_, reverted_, summary):
        assert (response.status_code, response.json()) == (404, {"detail": "Not found"})


# Bulk revert


async def test_bulk_revert_steps_each_agent_back_along_its_live_history(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    rules_v1 = await instructions(owner, project_id, "First rules.", "Rules")
    a, b, never, single = await named_agents(owner, project_id, "A", "B", "Never", "Single")
    for agent_id in (a, b, single):
        await published(owner, project_id, agent_id)
    rules_v2 = await instructions(owner, project_id, "Second rules.", "Stricter")
    await bulk_published(owner, project_id, [a, b], rules_v2["id"])
    await published(owner, project_id, b)

    result = await bulk_reverted(editor, project_id, [a, b, never, single])

    assert outcomes(result) == [
        ("A", "succeeded", None),
        ("B", "succeeded", None),
        ("Never", "skipped", NOTHING_TO_REVERT),
        ("Single", "skipped", NOTHING_TO_REVERT),
    ]
    [a_out, b_out, *_] = result["results"]
    assert (a_out["live_version"]["number"], a_out["instructions_version"]) == (
        1,
        {"id": rules_v1["id"], "number": 1},
    )
    assert (b_out["live_version"]["number"], b_out["instructions_version"]) == (
        2,
        {"id": rules_v2["id"], "number": 2},
    )
    # Bulk reverting again keeps walking back: B was bulk published from v1.
    again = await bulk_reverted(editor, project_id, [b])
    assert again["results"][0]["live_version"]["number"] == 1
    # Reverting adds no Version.
    assert [v["number"] for v in (await versions(owner, project_id, a))["versions"]] == [2, 1]


async def test_bulk_revert_reports_failures_per_agent(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    live, gone, stale = await named_agents(owner, project_id, "Live", "Gone", "Stale")
    for agent_id in (live, gone):
        await published(owner, project_id, agent_id)
        await published(owner, project_id, agent_id)
    assert (await archive_agent(owner, project_id, gone)).status_code == 200
    # Stale's earlier Version uses a credential that has since been deleted.
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY)
    model = {"credential_id": openai["id"], "model": "gpt-4.1"}
    await save_draft(owner, project_id, stale, {"behaviour": {"model": model}})
    await published(owner, project_id, stale)
    await save_draft(owner, project_id, stale, FULL_DEFAULT_DRAFT)
    await published(owner, project_id, stale)
    deleted = await owner.client.delete(credentials_path(owner.organisation_id, openai["id"]))
    assert deleted.status_code == 204, deleted.text

    result = await bulk_reverted(owner, project_id, [gone, str(uuid.uuid4()), stale, live])

    assert outcomes(result) == [
        ("Gone", "failed", AGENT_ARCHIVED),
        (None, "failed", NOT_FOUND),
        ("Stale", "failed", REVERT_TARGET_INVALID),
        ("Live", "succeeded", None),
    ]
    assert (await agent(owner, project_id, stale))["live_version"]["number"] == 2
    assert (await archive_project(owner, project_id)).status_code == 200
    assert (await bulk_revert(owner, project_id, [live])).status_code == 409


# The bulk operation ID on the Live History and the Audit log


async def test_the_bulk_operation_id_is_recorded_on_the_live_history_and_audit_events(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    rules_v1 = await instructions(owner, project_id, "First rules.", "Rules")
    a, b, never = await named_agents(owner, project_id, "A", "B", "Never")
    first = {agent_id: await published(owner, project_id, agent_id) for agent_id in (a, b)}
    rules_v2 = await instructions(owner, project_id, "Second rules.", "Stricter")

    publish_result = await bulk_published(editor, project_id, [a, b, never], rules_v2["id"])
    revert_result = await bulk_reverted(owner, project_id, [a, b])

    publish_id = publish_result["bulk_operation_id"]
    revert_id = revert_result["bulk_operation_id"]
    assert publish_id != revert_id
    second = {r["agent_id"]: r["live_version"] for r in publish_result["results"][:2]}
    for agent_id in (a, b):
        history = await live_history(owner, project_id, agent_id)
        assert [
            (
                e["action"],
                e["from_version"],
                e["to_version"],
                e["actor"]["id"],
                e["bulk_operation_id"],
            )
            for e in history[:2]
        ] == [
            (
                "bulk_revert",
                second[agent_id],
                {"id": first[agent_id]["id"], "number": 1},
                owner.member_id,
                revert_id,
            ),
            (
                "bulk_publish",
                {"id": first[agent_id]["id"], "number": 1},
                second[agent_id],
                editor.member_id,
                publish_id,
            ),
        ]

    v1 = {"version_id": rules_v1["id"], "number": 1}
    v2 = {"version_id": rules_v2["id"], "number": 2}

    def summary(version: dict[str, Any]) -> dict[str, Any]:
        return {"version_id": version["id"], "number": version["number"]}

    published_events = await audit_events(owner, "agent.bulk_published")
    assert [(e["actor"]["id"], e["target"], e["before"], e["after"]) for e in published_events] == [
        (
            editor.member_id,
            {"type": "agent", "id": agent_id},
            {"live_version": summary(first[agent_id])},
            {
                "live_version": {
                    **summary(second[agent_id]),
                    "note": "Bulk published with Instructions v2",
                    "instructions_version": v2,
                },
                "bulk_operation_id": publish_id,
            },
        )
        for agent_id in (b, a)
    ]
    reverted_events = await audit_events(owner, "agent.bulk_reverted")
    assert [(e["target"], e["before"], e["after"]) for e in reverted_events] == [
        (
            {"type": "agent", "id": agent_id},
            {"live_version": summary(second[agent_id])},
            {
                "live_version": {**summary(first[agent_id]), "instructions_version": v1},
                "bulk_operation_id": revert_id,
            },
        )
        for agent_id in (b, a)
    ]
    # One event per bulk action sums it up on the Project.
    [publish_summary] = await audit_events(owner, "project.agents_bulk_published")
    assert (publish_summary["actor"]["id"], publish_summary["target"]) == (
        editor.member_id,
        {"type": "project", "id": project_id},
    )
    assert publish_summary["after"] == {
        "bulk_operation_id": publish_id,
        "instructions_version": v2,
        "succeeded": 2,
        "skipped": 1,
        "failed": 0,
    }
    [revert_summary] = await audit_events(owner, "project.agents_bulk_reverted")
    assert revert_summary["after"] == {
        "bulk_operation_id": revert_id,
        "succeeded": 2,
        "skipped": 0,
        "failed": 0,
    }


# The Instructions rollout: which Agents are behind


async def test_the_rollout_shows_each_agents_pinned_instructions_and_how_many_are_behind(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    empty = await rollout(owner, project_id)
    assert empty == {"current_version": None, "behind": 0, "agents": []}
    ahead, behind, drafty, _never, none, gone = await named_agents(
        owner, project_id, "Ahead", "Behind", "Drafty", "Never", "None", "Gone"
    )
    await published(owner, project_id, none)
    rules_v1 = await instructions(owner, project_id, "First rules.", "Rules")
    for agent_id in (ahead, behind, drafty, gone):
        await published(owner, project_id, agent_id)
    await save_draft(owner, project_id, drafty, {"behaviour": {"system_prompt": "Edited."}})
    await archive_agent(owner, project_id, gone)
    rules_v2 = await instructions(owner, project_id, "Second rules.", "Stricter")
    await bulk_published(owner, project_id, [ahead], rules_v2["id"])

    found = await rollout(owner, project_id)

    v1 = {"id": rules_v1["id"], "number": 1}
    assert found["current_version"] == {"id": rules_v2["id"], "number": 2}
    assert found["behind"] == 3
    assert [
        (
            a["name"],
            a["live_version"] and a["live_version"]["number"],
            a["instructions_version"],
            a["has_draft_changes"],
            a["behind"],
        )
        for a in found["agents"]
    ] == [
        ("Ahead", 2, {"id": rules_v2["id"], "number": 2}, False, False),
        ("Behind", 1, v1, False, True),
        ("Drafty", 1, v1, True, True),
        ("Never", None, None, False, False),
        ("None", 1, None, False, True),
    ]
    assert found["agents"][0]["id"] == ahead


async def test_an_archived_projects_rollout_can_still_be_read(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    await instructions(owner, project_id, "Rules.", "Rules")
    assert (await archive_project(owner, project_id)).status_code == 200

    assert (await rollout(owner, project_id))["current_version"]["number"] == 1


# Reverting Instructions offers a bulk revert


async def test_reverting_instructions_returns_the_agents_pinned_to_the_reverted_version(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    await instructions(owner, project_id, "First rules.", "Rules")
    adopted, held, gone = await named_agents(owner, project_id, "Adopted", "Held", "Gone")
    for agent_id in (adopted, held, gone):
        await published(owner, project_id, agent_id)
    rules_v2 = await instructions(owner, project_id, "Second rules.", "Stricter")
    result = await bulk_published(owner, project_id, [adopted, gone], rules_v2["id"])
    await archive_agent(owner, project_id, gone)

    response = await revert_instructions(owner, project_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["number"] == 1
    assert body["reverted_from"] == {"id": rules_v2["id"], "number": 2}
    assert body["bulk_revert_candidates"] == [
        {"id": adopted, "name": "Adopted", "live_version": result["results"][0]["live_version"]}
    ]
    # Taking the offer puts the Agent back on the Instructions it ran with before.
    reverted_ = await bulk_reverted(
        owner, project_id, [c["id"] for c in body["bulk_revert_candidates"]]
    )
    assert reverted_["results"][0]["instructions_version"]["number"] == 1
    assert (await rollout(owner, project_id))["behind"] == 0


async def test_a_single_revert_after_a_bulk_publish_follows_it_back(owner: SignedUpMember) -> None:
    """The revert rule follows bulk publishes like publishes."""
    project_id = await create_project(owner)
    [agent_id] = await named_agents(owner, project_id, "HR helper")
    first = await published(owner, project_id, agent_id, instructions_version_id=None)
    rules = await instructions(owner, project_id, "Rules.", "Rules")
    await bulk_published(owner, project_id, [agent_id], rules["id"])

    assert (await reverted(owner, project_id, agent_id))["id"] == first["id"]
