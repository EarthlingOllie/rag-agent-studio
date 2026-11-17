"""API seam: applying a Suggestion to the Draft, and deleting one (spec 16, ticket 16-06).

An Editor reads a Suggestion's Diff against the current Draft, each change marked ``clean``
(the Draft still has the base value), ``applied`` (the Draft already has the suggested value)
or ``clash`` (the Draft has changed it some other way), and applies it whole, naming the Draft
revision they reviewed. Clean changes are written in one Draft save; any clash refuses the whole
apply with every clashing path and writes nothing; a stale revision is the Draft editor's own
stale-Draft conflict. Applying never Publishes. A Suggestion made from a Version that is no longer
Live reads as stale and still applies, saying so.

Visitor replies come from a scripted ``FunctionModel`` that cites nothing, so the fake judge
fails each one's grounding; proposing is scripted per test.
"""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.suggestions import api as suggestions_api
from tests.agents import save_draft
from tests.conftest import ClientFactory, MemberFactory, SignedUpMember, TenantFactory
from tests.fakes.clock import ControllableClock
from tests.integration.test_agent_archive import archive
from tests.integration.test_agent_versions import agent as read_agent
from tests.integration.test_agent_versions import published
from tests.integration.test_evaluation import add_case, evaluated
from tests.integration.test_evaluation_publish import summary
from tests.integration.test_evaluation_settings import set_repeats
from tests.integration.test_playground import delete_credential_row
from tests.integration.test_projects import archive as archive_project
from tests.integration.test_projects import audit_events
from tests.integration.test_provider_credentials import ANTHROPIC_KEY, added
from tests.integration.test_suggestions import (
    BASE_PROMPT,
    live_agent,
    proposal,
    replied,
    scripted,
    started,
    suggestions_path,
)

APPLIED = "agent.suggestion_applied"
DELETED = "agent.suggestion_deleted"
SUGGESTED_PROMPT = f"{BASE_PROMPT} Always cite the passage you used."
PROMPT_CHANGE = {
    "path": "behaviour.system_prompt",
    "value": SUGGESTED_PROMPT,
    "explanation": "Replies cited nothing.",
    "evidence": ["E1"],
}
TOP_K_CHANGE = {
    "path": "retrieval.top_k",
    "value": 8,
    "explanation": "Too few Chunks.",
    "evidence": ["E1"],
}
SCORE_CHANGE = {
    "path": "retrieval.minimum_score",
    "value": 0.25,
    "explanation": "Weak Chunks crowded out.",
    "evidence": ["E1"],
}


@pytest.fixture
async def visitor(new_client: ClientFactory) -> httpx.AsyncClient:
    """A browser on someone's website: no Studio session."""
    return await new_client()


async def suggested(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    changes: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A live Agent and a completed Suggestion with ``changes``, made from one failed reply."""
    scripted(app, proposer=proposal(changes))
    agent = await live_agent(app, owner)
    await replied(visitor, agent)
    suggestion = await started(owner, agent)
    assert suggestion["outcome"] == "changes", suggestion
    return agent, suggestion


async def edit_draft(
    member: SignedUpMember, agent: dict[str, Any], **sections: dict[str, Any]
) -> dict[str, Any]:
    """Saves the Draft with ``sections`` merged into its current value; the Agent."""
    current = await read_agent(member, agent["project_id"], agent["id"])
    draft = current["draft"]
    for section, values in sections.items():
        draft[section] = {**draft[section], **values}
    response = await save_draft(member, agent["project_id"], agent["id"], draft)
    assert response.status_code == 200, response.text
    saved: dict[str, Any] = response.json()
    return saved


async def diff(member: SignedUpMember, agent: dict[str, Any], suggestion_id: str) -> httpx.Response:
    return await member.client.get(suggestions_path(member, agent, suggestion_id, "diff"))


async def diffed(
    member: SignedUpMember, agent: dict[str, Any], suggestion_id: str
) -> dict[str, Any]:
    response = await diff(member, agent, suggestion_id)
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()
    return found


async def apply(
    member: SignedUpMember, agent: dict[str, Any], suggestion_id: str, base_revision: int
) -> httpx.Response:
    return await member.client.post(
        suggestions_path(member, agent, suggestion_id, "apply"),
        json={"base_revision": base_revision},
    )


async def delete(
    member: SignedUpMember, agent: dict[str, Any], suggestion_id: str
) -> httpx.Response:
    return await member.client.delete(suggestions_path(member, agent, suggestion_id))


async def read(member: SignedUpMember, agent: dict[str, Any], suggestion_id: str) -> dict[str, Any]:
    response = await member.client.get(suggestions_path(member, agent, suggestion_id))
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()
    return found


def rows(found: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [
        (c["path"], c["base_value"], c["draft_value"], c["suggested_value"], c["state"])
        for c in found["changes"]
    ]


# The Diff


async def test_the_diff_marks_each_change_clean_already_applied_or_a_clash(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent, suggestion = await suggested(
        app, owner, visitor, [PROMPT_CHANGE, TOP_K_CHANGE, SCORE_CHANGE]
    )
    saved = await edit_draft(
        owner, agent, behaviour={"system_prompt": SUGGESTED_PROMPT}, retrieval={"top_k": 3}
    )

    found = await diffed(owner, agent, suggestion["id"])

    assert found["draft_revision"] == saved["draft_revision"]
    assert found["stale"] is False
    assert found["stale_notice"] is None
    assert rows(found) == [
        ("behaviour.system_prompt", BASE_PROMPT, SUGGESTED_PROMPT, SUGGESTED_PROMPT, "applied"),
        ("retrieval.top_k", 5, 3, 8, "clash"),
        ("retrieval.minimum_score", 0, 0, 0.25, "clean"),
    ]
    assert found["clashes"] == 1


# Applying


async def test_applying_merges_cleanly_with_unrelated_draft_edits_and_never_publishes(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
    clock: ControllableClock,
) -> None:
    agent, suggestion = await suggested(app, owner, visitor, [PROMPT_CHANGE, SCORE_CHANGE])
    editor = await member_factory(owner, "editor")
    # An unrelated edit the Suggestion doesn't touch.
    edited = await edit_draft(editor, agent, behaviour={"temperature": 0.2})

    response = await apply(editor, agent, suggestion["id"], edited["draft_revision"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["paths"] == ["behaviour.system_prompt", "retrieval.minimum_score"]
    assert body["stale_notice"] is None
    after = body["agent"]
    assert after["draft"]["behaviour"]["system_prompt"] == SUGGESTED_PROMPT
    assert after["draft"]["behaviour"]["temperature"] == 0.2
    assert after["draft"]["retrieval"]["min_score"] == 0.25
    assert after["draft_revision"] == edited["draft_revision"] + 1
    # Nothing is Published: the Live Version is the one the Suggestion was made from.
    assert after["live_version"]["id"] == agent["version"]["id"]
    assert after["has_unpublished_changes"] is True
    assert await read_agent(owner, agent["project_id"], agent["id"]) == after
    # It is marked applied, with who and when, in its detail and the list.
    applied = body["suggestion"]
    assert applied["applied_at"] == clock.now().isoformat().replace("+00:00", "Z")
    assert applied["applied_by"] == {"id": editor.member_id, "name": editor.name}
    assert await read(owner, agent, suggestion["id"]) == applied
    listed = (await owner.client.get(suggestions_path(owner, agent))).json()
    assert [(s["applied_at"], s["applied_by"]) for s in listed] == [
        (applied["applied_at"], applied["applied_by"])
    ]
    # Recorded with the Suggestion and the paths written, never their text.
    (event,) = await audit_events(owner, APPLIED)
    assert event["actor"]["id"] == editor.member_id
    assert event["target"] == {"type": "agent", "id": agent["id"]}
    assert event["before"] is None
    assert event["after"] == {
        "suggestion_id": suggestion["id"],
        "paths": ["behaviour.system_prompt", "retrieval.minimum_score"],
    }
    assert SUGGESTED_PROMPT not in str(event)


async def test_a_value_already_suggested_is_left_and_the_rest_is_written(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent, suggestion = await suggested(app, owner, visitor, [PROMPT_CHANGE, SCORE_CHANGE])
    edited = await edit_draft(owner, agent, behaviour={"system_prompt": SUGGESTED_PROMPT})

    response = await apply(owner, agent, suggestion["id"], edited["draft_revision"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["paths"] == ["retrieval.minimum_score"]
    assert body["agent"]["draft"]["behaviour"]["system_prompt"] == SUGGESTED_PROMPT
    assert body["agent"]["draft"]["retrieval"]["min_score"] == 0.25
    (event,) = await audit_events(owner, APPLIED)
    assert event["after"]["paths"] == ["retrieval.minimum_score"]


async def test_any_clash_refuses_the_whole_apply_listing_each_and_writes_nothing(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent, suggestion = await suggested(
        app, owner, visitor, [PROMPT_CHANGE, TOP_K_CHANGE, SCORE_CHANGE]
    )
    edited = await edit_draft(
        owner, agent, behaviour={"system_prompt": "Be brief."}, retrieval={"top_k": 3}
    )

    response = await apply(owner, agent, suggestion["id"], edited["draft_revision"])

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["conflict"] == "suggestion_clash"
    assert "clash" in body["detail"]
    assert body["latest"] is None
    assert [
        (c["path"], c["base_value"], c["draft_value"], c["suggested_value"])
        for c in body["clashes"]
    ] == [
        ("behaviour.system_prompt", BASE_PROMPT, "Be brief.", SUGGESTED_PROMPT),
        ("retrieval.top_k", 5, 3, 8),
    ]
    # Nothing is written, not even the clean change.
    assert await read_agent(owner, agent["project_id"], agent["id"]) == edited
    assert (await read(owner, agent, suggestion["id"]))["applied_at"] is None
    assert await audit_events(owner, APPLIED) == []


async def test_a_stale_draft_revision_is_the_stale_draft_conflict(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
) -> None:
    agent, suggestion = await suggested(app, owner, visitor, [PROMPT_CHANGE])
    reviewed = (await diffed(owner, agent, suggestion["id"]))["draft_revision"]
    editor = await member_factory(owner, "editor")
    theirs = await edit_draft(editor, agent, behaviour={"temperature": 0.1})

    response = await apply(owner, agent, suggestion["id"], reviewed)

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["conflict"] == "stale_draft"
    assert body["detail"].startswith("Someone else saved this Draft")
    assert body["latest"] == theirs
    assert body["clashes"] == []
    assert await read_agent(owner, agent["project_id"], agent["id"]) == theirs
    assert (await read(owner, agent, suggestion["id"]))["applied_at"] is None


async def test_a_suggestion_from_an_earlier_live_version_is_stale_and_still_applies(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent, suggestion = await suggested(app, owner, visitor, [PROMPT_CHANGE])
    assert suggestion["stale"] is False
    await edit_draft(owner, agent, behaviour={"temperature": 0.3})
    await published(owner, agent["project_id"], agent["id"])

    found = await read(owner, agent, suggestion["id"])
    assert found["stale"] is True
    listed = (await owner.client.get(suggestions_path(owner, agent))).json()
    assert [s["stale"] for s in listed] == [True]
    reviewed = await diffed(owner, agent, suggestion["id"])
    assert reviewed["stale"] is True
    assert "v1" in reviewed["stale_notice"]
    response = await apply(owner, agent, suggestion["id"], reviewed["draft_revision"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stale_notice"] == reviewed["stale_notice"]
    assert "check was against" in body["stale_notice"]
    assert body["agent"]["draft"]["behaviour"]["system_prompt"] == SUGGESTED_PROMPT
    assert body["suggestion"]["stale"] is True


async def test_applying_makes_the_publish_summary_ask_for_a_new_run(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent, suggestion = await suggested(app, owner, visitor, [PROMPT_CHANGE])
    await set_repeats(owner, 1)
    await add_case(owner, agent["project_id"], agent["id"])
    run = (await evaluated(owner, agent["project_id"], agent["id"]))["run"]
    before = await summary(owner, agent["project_id"], agent["id"])
    assert before["run"]["id"] == run["id"]
    assert before["run"]["stale"] is False
    revision = (await read_agent(owner, agent["project_id"], agent["id"]))["draft_revision"]

    response = await apply(owner, agent, suggestion["id"], revision)

    assert response.status_code == 200, response.text
    after = await summary(owner, agent["project_id"], agent["id"])
    assert (after["state"], after["run"]["id"], after["run"]["stale"]) == ("stale", run["id"], True)


async def test_a_suggestion_that_has_not_completed_with_changes_cannot_be_applied(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    scripted(app, proposer=proposal([]))
    agent = await live_agent(app, owner)
    await replied(visitor, agent)
    suggestion = await started(owner, agent)
    assert suggestion["outcome"] == "no_change"
    revision = (await read_agent(owner, agent["project_id"], agent["id"]))["draft_revision"]

    response = await apply(owner, agent, suggestion["id"], revision)

    assert response.status_code == 409, response.text
    assert "no configuration change" in response.json()["detail"]
    assert (await diffed(owner, agent, suggestion["id"]))["changes"] == []


# Deleting


async def test_an_editor_deletes_a_suggestion_recorded_as_an_audit_event(
    app: FastAPI,
    owner: SignedUpMember,
    member_factory: MemberFactory,
    visitor: httpx.AsyncClient,
) -> None:
    agent, suggestion = await suggested(app, owner, visitor, [PROMPT_CHANGE])
    editor = await member_factory(owner, "editor")

    response = await delete(editor, agent, suggestion["id"])

    assert response.status_code == 204, response.text
    assert (await owner.client.get(suggestions_path(owner, agent))).json() == []
    assert (
        await owner.client.get(suggestions_path(owner, agent, suggestion["id"]))
    ).status_code == 404
    (event,) = await audit_events(owner, DELETED)
    assert event["actor"]["id"] == editor.member_id
    assert event["target"] == {"type": "agent", "id": agent["id"]}
    assert event["before"] == {"suggestion_id": suggestion["id"]}
    assert event["after"] is None
    assert (await delete(owner, agent, suggestion["id"])).status_code == 404


async def test_applying_and_deleting_are_refused_on_an_archived_agent_or_project(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent, suggestion = await suggested(app, owner, visitor, [PROMPT_CHANGE])
    revision = (await read_agent(owner, agent["project_id"], agent["id"]))["draft_revision"]
    assert (await archive(owner, agent["project_id"], agent["id"])).status_code == 200

    for response in (
        await apply(owner, agent, suggestion["id"], revision),
        await delete(owner, agent, suggestion["id"]),
    ):
        assert response.status_code == 409, response.text
        assert "archived" in response.json()["detail"]
    # Still readable, Diff included.
    assert (await read(owner, agent, suggestion["id"]))["applied_at"] is None
    assert (await diff(owner, agent, suggestion["id"])).status_code == 200
    assert await audit_events(owner, APPLIED) == []
    assert await audit_events(owner, DELETED) == []


async def test_applying_and_deleting_are_refused_in_an_archived_project(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent, suggestion = await suggested(app, owner, visitor, [PROMPT_CHANGE])
    revision = (await read_agent(owner, agent["project_id"], agent["id"]))["draft_revision"]
    assert (await archive_project(owner, agent["project_id"])).status_code == 200

    for response in (
        await apply(owner, agent, suggestion["id"], revision),
        await delete(owner, agent, suggestion["id"]),
    ):
        assert response.status_code == 409, response.text
        assert "archived" in response.json()["detail"]


async def test_unknown_and_another_organisations_suggestions_cannot_be_applied_or_deleted(
    app: FastAPI,
    owner: SignedUpMember,
    tenant_factory: TenantFactory,
    visitor: httpx.AsyncClient,
) -> None:
    agent, suggestion = await suggested(app, owner, visitor, [PROMPT_CHANGE])
    revision = (await read_agent(owner, agent["project_id"], agent["id"]))["draft_revision"]
    other = await tenant_factory()
    unknown = "00000000-0000-4000-8000-000000000000"

    for member, suggestion_id in ((owner, unknown), (other, suggestion["id"])):
        assert (await diff(member, agent, suggestion_id)).status_code == 404
        assert (await apply(member, agent, suggestion_id, revision)).status_code == 404
        assert (await delete(member, agent, suggestion_id)).status_code == 404
    assert (await read(owner, agent, suggestion["id"]))["applied_at"] is None


async def test_an_invalid_merged_draft_is_refused_like_a_draft_save(
    app: FastAPI, owner: SignedUpMember, visitor: httpx.AsyncClient
) -> None:
    agent, suggestion = await suggested(app, owner, visitor, [PROMPT_CHANGE])
    claude = await added(owner, provider="anthropic", api_key=ANTHROPIC_KEY)
    model = {"credential_id": claude["id"], "model": "claude-sonnet-4-5"}
    edited = await edit_draft(owner, agent, behaviour={"model": model})
    # The Draft names a credential that is gone, so it no longer saves.
    await delete_credential_row(app, claude["id"])

    response = await apply(owner, agent, suggestion["id"], edited["draft_revision"])

    assert response.status_code == 422, response.text
    assert (await read_agent(owner, agent["project_id"], agent["id"]))["draft_revision"] == (
        edited["draft_revision"]
    )
    assert (await read(owner, agent, suggestion["id"]))["applied_at"] is None


async def test_a_suggestion_run_in_progress_cannot_be_deleted_or_applied(
    app: FastAPI,
    owner: SignedUpMember,
    visitor: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scripted(app, proposer=proposal([PROMPT_CHANGE]))
    agent = await live_agent(app, owner)
    await replied(visitor, agent)

    async def unsent(suggestion_id: Any) -> None:
        pass

    monkeypatch.setattr(suggestions_api, "enqueue_suggestion", unsent)
    queued = await started(owner, agent)
    assert queued["status"] == "queued"
    revision = (await read_agent(owner, agent["project_id"], agent["id"]))["draft_revision"]

    deleted = await delete(owner, agent, queued["id"])
    applied = await apply(owner, agent, queued["id"], revision)

    assert deleted.status_code == 409, deleted.text
    assert "Cancel it" in deleted.json()["detail"]
    assert applied.status_code == 409, applied.text
    assert [s["id"] for s in (await owner.client.get(suggestions_path(owner, agent))).json()] == [
        queued["id"]
    ]
