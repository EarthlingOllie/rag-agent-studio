"""API seam: an Editor changes an Agent's Retrieval Mode and Search limit in its Draft. The
change shows in the Draft's diff against the Live Version, and each Draft change of either
setting is an Audit Event (``agent.retrieval_mode_changed``) with the values before and after;
a save that leaves both alone, or is refused, records none."""

from tests.agents import FULL_DEFAULT_DRAFT, create_agent, save_draft
from tests.conftest import MemberFactory, SignedUpMember
from tests.documents import create_project
from tests.integration.test_agent_diffs import diffed
from tests.integration.test_agent_draft_management import discard
from tests.integration.test_agent_versions import published
from tests.integration.test_provider_credentials import audit_events

CHANGED = "agent.retrieval_mode_changed"


async def test_the_retrieval_mode_and_search_limit_show_in_the_draft_diff(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await save_draft(owner, project_id, agent_id, {"retrieval": {"mode": "automatic"}})
    await published(owner, project_id, agent_id)
    await save_draft(
        owner, project_id, agent_id, {"retrieval": {"mode": "agentic", "search_limit": 5}}
    )

    body = await diffed(owner, project_id, agent_id, "live", "draft")

    assert [(c["path"], c["before"], c["after"]) for c in body["changes"]] == [
        ("retrieval.mode", "automatic", "agentic"),
        ("retrieval.search_limit", 3, 5),
    ]


async def test_changing_the_retrieval_mode_and_search_limit_is_audited(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]

    first = await save_draft(editor, project_id, agent_id, {"retrieval": {"mode": "agentic"}})
    second = await save_draft(
        editor, project_id, agent_id, {"retrieval": {"mode": "agentic", "search_limit": 2}}
    )
    third = await save_draft(
        editor, project_id, agent_id, {"retrieval": {"mode": "automatic", "search_limit": 4}}
    )

    assert [r.status_code for r in (first, second, third)] == [200, 200, 200]
    events = await audit_events(owner, CHANGED)
    # Newest first.
    assert [(e["actor"]["id"], e["target"], e["before"], e["after"]) for e in events] == [
        (
            editor.member_id,
            {"type": "agent", "id": agent_id},
            {"retrieval_mode": "agentic", "search_limit": 2},
            {"retrieval_mode": "automatic", "search_limit": 4},
        ),
        (
            editor.member_id,
            {"type": "agent", "id": agent_id},
            {"search_limit": 3},
            {"search_limit": 2},
        ),
        (
            editor.member_id,
            {"type": "agent", "id": agent_id},
            {"retrieval_mode": "automatic"},
            {"retrieval_mode": "agentic"},
        ),
    ]


async def test_a_draft_save_that_leaves_retrieval_mode_alone_is_not_audited(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]

    saved = await save_draft(owner, project_id, agent_id, {"retrieval": {"top_k": 8}})
    refused = await save_draft(
        owner, project_id, agent_id, {"retrieval": {"mode": "agentic", "search_limit": 6}}
    )

    assert saved.status_code == 200, saved.text
    assert refused.status_code == 422, refused.text
    assert await audit_events(owner, CHANGED) == []


async def test_discarding_the_draft_back_to_another_mode_is_audited(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    await published(owner, project_id, agent_id)
    await save_draft(owner, project_id, agent_id, {"retrieval": {"mode": "agentic"}})

    response = await discard(owner, project_id, agent_id)

    assert response.status_code == 200, response.text
    assert response.json()["draft"]["retrieval"] == FULL_DEFAULT_DRAFT["retrieval"]
    events = await audit_events(owner, CHANGED)
    assert [(e["before"], e["after"]) for e in events] == [
        ({"retrieval_mode": "agentic"}, {"retrieval_mode": "automatic"}),
        ({"retrieval_mode": "automatic"}, {"retrieval_mode": "agentic"}),
    ]
