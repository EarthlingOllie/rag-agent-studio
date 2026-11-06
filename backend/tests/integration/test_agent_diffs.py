"""API seam: diffs of an Agent's configuration. An Editor compares any two Versions, or the
Draft with the Live Version, as a structural diff of every AgentConfig field with a line diff
for markdown, plus the change of pinned Project Instructions between Versions."""

import uuid
from typing import Any

import httpx

from tests.agents import agents_path, create_agent, save_draft
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.documents import create_project
from tests.integration.test_agent_versions import number, published
from tests.integration.test_project_instructions_versions import published as instructions


async def diff(
    member: SignedUpMember, project_id: str, agent_id: str, source: str, target: str
) -> httpx.Response:
    return await member.client.get(
        agents_path(member, project_id, agent_id, "diff"),
        params={"from": source, "to": target},
    )


async def diffed(
    member: SignedUpMember, project_id: str, agent_id: str, source: str, target: str
) -> dict[str, Any]:
    response = await diff(member, project_id, agent_id, source, target)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_the_draft_compared_with_the_live_version(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await save_draft(
        owner,
        project_id,
        agent_id,
        {"behaviour": {"system_prompt": "# Role\nHelp with HR."}, "retrieval": {"top_k": 5}},
    )
    live = await published(owner, project_id, agent_id)
    await save_draft(
        owner,
        project_id,
        agent_id,
        {
            "behaviour": {"system_prompt": "# Role\nHelp with HR and IT."},
            "retrieval": {"top_k": 8},
            "experience": {"starter_questions": ["Holidays?"]},
        },
    )

    body = await diffed(editor, project_id, agent_id, "live", "draft")

    assert body["from"] == {"kind": "version", "version": number(live)}
    assert body["to"] == {"kind": "draft", "version": None}
    assert body["changes"] == [
        {
            "path": "behaviour.system_prompt",
            "before": "# Role\nHelp with HR.",
            "after": "# Role\nHelp with HR and IT.",
            "added": None,
            "removed": None,
            "lines": [
                {"op": "equal", "text": "# Role"},
                {"op": "delete", "text": "Help with HR."},
                {"op": "insert", "text": "Help with HR and IT."},
            ],
        },
        {
            "path": "retrieval.top_k",
            "before": 5,
            "after": 8,
            "added": None,
            "removed": None,
            "lines": None,
        },
        {
            "path": "experience.starter_questions",
            "before": [],
            "after": ["Holidays?"],
            "added": ["Holidays?"],
            "removed": [],
            "lines": None,
        },
    ]
    # The Draft pins no Instructions until it is published.
    assert body["instructions"] is None


async def test_an_unchanged_draft_has_no_changes(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await published(owner, project_id, agent_id)

    body = await diffed(owner, project_id, agent_id, "draft", "live")

    assert body["changes"] == []
    assert body["from"]["kind"] == "draft"


async def test_two_versions_compared_with_their_pinned_instructions(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    first_rules = await instructions(owner, project_id, "Be kind.\nCite sources.", "v1")
    v1 = await published(owner, project_id, agent_id)
    second_rules = await instructions(owner, project_id, "Be kind.\nAlways cite sources.", "v2")
    await save_draft(owner, project_id, agent_id, {"behaviour": {"temperature": 0.1}})
    v2 = await published(owner, project_id, agent_id)

    body = await diffed(owner, project_id, agent_id, v1["id"], v2["id"])

    assert body["from"] == {"kind": "version", "version": number(v1)}
    assert body["to"] == {"kind": "version", "version": number(v2)}
    assert [(c["path"], c["before"], c["after"]) for c in body["changes"]] == [
        ("behaviour.temperature", 0.7, 0.1)
    ]
    assert body["instructions"] == {
        "before": number(first_rules),
        "after": number(second_rules),
        "lines": [
            {"op": "equal", "text": "Be kind."},
            {"op": "delete", "text": "Cite sources."},
            {"op": "insert", "text": "Always cite sources."},
        ],
    }
    # Backwards, the same changes the other way round.
    backwards = await diffed(owner, project_id, agent_id, v2["id"], v1["id"])
    assert [(c["path"], c["before"], c["after"]) for c in backwards["changes"]] == [
        ("behaviour.temperature", 0.1, 0.7)
    ]
    assert backwards["instructions"]["before"] == number(second_rules)


async def test_versions_pinning_the_same_instructions_show_no_instructions_change(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await instructions(owner, project_id, "Be kind.", "v1")
    v1 = await published(owner, project_id, agent_id)
    v2 = await published(owner, project_id, agent_id)

    body = await diffed(owner, project_id, agent_id, v1["id"], v2["id"])

    assert body == {**body, "changes": [], "instructions": None}


async def test_pinning_instructions_for_the_first_time_shows_their_whole_text(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    v1 = await published(owner, project_id, agent_id)
    rules = await instructions(owner, project_id, "Be kind.", "v1")
    v2 = await published(owner, project_id, agent_id)

    body = await diffed(owner, project_id, agent_id, v1["id"], v2["id"])

    assert body["instructions"] == {
        "before": None,
        "after": number(rules),
        "lines": [{"op": "insert", "text": "Be kind."}],
    }


async def test_comparing_with_the_live_version_of_an_agent_that_is_not_live_is_refused(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]

    for source, target in (("live", "draft"), ("draft", "live")):
        response = await diff(owner, project_id, agent_id, source, target)
        assert response.status_code == 409, response.text
        assert response.json()["detail"] == (
            "This Agent has never been published, so it has no Live Version."
        )
    # The Draft compared with itself needs no Version.
    assert (await diffed(owner, project_id, agent_id, "draft", "draft"))["changes"] == []


async def test_a_version_of_another_agent_or_organisation_is_not_found(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    other_id = (await create_agent(owner, project_id, "Other"))["id"]
    theirs = await published(owner, project_id, other_id)
    mine = await published(owner, project_id, agent_id)
    stranger = await tenant_factory()

    for source, target in ((theirs["id"], "draft"), ("draft", str(uuid.uuid4()))):
        response = await diff(owner, project_id, agent_id, source, target)
        assert response.status_code == 404, response.text
    outside = await stranger.client.get(
        agents_path(owner, project_id, agent_id, "diff"),
        params={"from": mine["id"], "to": "draft"},
    )
    assert outside.status_code == 404, outside.text


async def test_a_side_must_be_draft_live_or_a_version_id(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]

    assert (await diff(owner, project_id, agent_id, "latest", "draft")).status_code == 422
    missing = await owner.client.get(agents_path(owner, project_id, agent_id, "diff"))
    assert missing.status_code == 422
