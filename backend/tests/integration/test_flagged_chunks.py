"""API seam: what happens to the Chunks the ingestion Guardrail scan flags. Each Project chooses
whether they are only marked (they keep being retrieved, marked in the Document viewer) or
excluded from retrieval (never a candidate; the Trace lists them as left out by the scan). An
Editor can clear a false positive, which is recorded as an Audit Event. Everything is driven and
observed through the API, with the rule-driven fake classifier and the fixture Knowledge Base."""

from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo

from app.guardrails.fake import FakeRule
from tests.agents import (
    AUTOMATIC,
    answer_with,
    ask,
    create_agent,
    parse_sse,
    save_draft,
    start_conversation,
    trace_path,
    use_default_model,
)
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.documents import chunks, documents, project_path
from tests.fakes.clock import ControllableClock
from tests.knowledge_base import LEAVE, PRODUCT, PRODUCT_QUESTION, knowledge_base

# Flags the product Chunk, the one the product question finds best.
FLAG_PRODUCT = FakeRule(
    contains="SKU-4471", label="prompt_injection", score=0.97, reason="Flagged by the test"
)


async def set_mode(member: SignedUpMember, project_id: str, mode: str) -> dict[str, Any]:
    response = await member.client.patch(
        project_path(member, project_id), json={"flagged_chunk_mode": mode}
    )
    assert response.status_code == 200, response.text
    project: dict[str, Any] = response.json()
    return project


async def flagged_project(app: FastAPI, member: SignedUpMember) -> str:
    """The fixture Knowledge Base, with the product Chunk flagged by the scan."""
    app.state.ingestion.classifier.rules = [FLAG_PRODUCT]
    return await knowledge_base(app, member)


async def product_chunk(member: SignedUpMember, project_id: str) -> tuple[str, dict[str, Any]]:
    """The product Document's ID and its one Chunk."""
    by_name = {d["name"]: d["id"] for d in await documents(member, project_id)}
    document_id = by_name["product.txt"]
    (chunk,) = await chunks(member, project_id, document_id)
    return document_id, chunk


def flag_path(member: SignedUpMember, project_id: str, document_id: str, chunk_id: str) -> str:
    return f"{project_path(member, project_id)}/documents/{document_id}/chunks/{chunk_id}/flag"


prompts: list[str] = []


async def recording(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    prompts.append(str(messages))
    yield "Let me check."


async def traced(member: SignedUpMember, project_id: str, agent_id: str) -> list[dict[str, Any]]:
    """Asks the product question in a new Playground Conversation; returns the Trace's Chunks."""
    conversation = await start_conversation(member, project_id, agent_id)
    response = await ask(member, project_id, agent_id, conversation["id"], PRODUCT_QUESTION)
    assert response.status_code == 200, response.text
    (done,) = [data for event, data in parse_sse(response.text) if event == "done"]
    trace = await member.client.get(
        trace_path(member, project_id, agent_id, conversation["id"], done["message_id"])
    )
    assert trace.status_code == 200, trace.text
    found: list[dict[str, Any]] = trace.json()["chunks"]
    return found


async def agent(member: SignedUpMember, project_id: str) -> str:
    agent_id: str = (await create_agent(member, project_id))["id"]
    saved = await save_draft(member, project_id, agent_id, {"retrieval": {**AUTOMATIC, "top_k": 3}})
    assert saved.status_code == 200, saved.text
    return agent_id


def given(found: list[dict[str, Any]]) -> list[str]:
    return [c["text"] for c in found if c["excluded_reason"] is None]


def left_out_by_the_scan(found: list[dict[str, Any]]) -> list[str]:
    return [c["text"] for c in found if c["excluded_reason"] == "guardrail_flagged"]


# The setting


async def test_a_new_project_marks_flagged_chunks_and_an_editor_can_choose_to_exclude_them(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    created = await editor.client.post(
        f"/api/organisations/{owner.organisation_id}/projects", json={"name": "Handbook"}
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    assert created.json()["flagged_chunk_mode"] == "mark"

    excluded = await set_mode(editor, project_id, "exclude")
    reread = await editor.client.get(project_path(editor, project_id))
    renamed = await editor.client.patch(project_path(editor, project_id), json={"name": "HR"})
    marked = await set_mode(editor, project_id, "mark")

    assert excluded["flagged_chunk_mode"] == "exclude"
    assert reread.json()["flagged_chunk_mode"] == "exclude"
    # Changing something else leaves the setting alone.
    assert renamed.json()["flagged_chunk_mode"] == "exclude"
    assert marked["flagged_chunk_mode"] == "mark"


async def test_the_setting_is_mark_or_exclude_and_an_archived_project_keeps_its_own(
    owner: SignedUpMember,
) -> None:
    created = await owner.client.post(
        f"/api/organisations/{owner.organisation_id}/projects", json={"name": "Handbook"}
    )
    project_id = created.json()["id"]

    unknown = await owner.client.patch(
        project_path(owner, project_id), json={"flagged_chunk_mode": "delete"}
    )
    archived = await owner.client.post(f"{project_path(owner, project_id)}/archive")
    refused = await owner.client.patch(
        project_path(owner, project_id), json={"flagged_chunk_mode": "exclude"}
    )

    assert unknown.status_code == 422
    assert archived.status_code == 200, archived.text
    assert refused.status_code == 409
    assert refused.json()["detail"] == "This Project is archived. An Owner can restore it."
    reread = await owner.client.get(project_path(owner, project_id))
    assert reread.json()["flagged_chunk_mode"] == "mark"


# Retrieval


async def test_a_marked_flagged_chunk_is_still_retrieved(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, recording)
    await use_default_model(owner)
    project_id = await flagged_project(app, owner)
    agent_id = await agent(owner, project_id)

    found = await traced(owner, project_id, agent_id)

    assert given(found)[0] == PRODUCT
    assert left_out_by_the_scan(found) == []


async def test_an_excluded_flagged_chunk_never_reaches_the_model_and_the_trace_says_why(
    app: FastAPI, owner: SignedUpMember
) -> None:
    prompts.clear()
    answer_with(app, recording)
    await use_default_model(owner)
    project_id = await flagged_project(app, owner)
    await set_mode(owner, project_id, "exclude")
    agent_id = await agent(owner, project_id)

    found = await traced(owner, project_id, agent_id)

    # The product Chunk matches the question best, but it is never a candidate: the model is
    # given the next best Chunks, and still three of them (the flagged one takes no place).
    assert PRODUCT not in given(found)
    assert len(given(found)) == 3
    assert left_out_by_the_scan(found) == [PRODUCT]
    (excluded,) = [c for c in found if c["excluded_reason"] == "guardrail_flagged"]
    assert (excluded["rank"], excluded["cited"]) == (None, False)
    assert PRODUCT not in prompts[-1]
    assert given(found)[0] in prompts[-1]


async def test_excluding_flagged_chunks_takes_effect_at_once_and_marking_brings_them_back(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, recording)
    await use_default_model(owner)
    project_id = await flagged_project(app, owner)
    agent_id = await agent(owner, project_id)

    await set_mode(owner, project_id, "exclude")
    excluded = await traced(owner, project_id, agent_id)
    await set_mode(owner, project_id, "mark")
    marked = await traced(owner, project_id, agent_id)

    assert left_out_by_the_scan(excluded) == [PRODUCT]
    assert given(marked)[0] == PRODUCT


# Clearing a flag


async def test_an_editor_clears_a_false_positive_and_the_chunk_is_retrieved_again(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    answer_with(app, recording)
    await use_default_model(owner)
    editor = await member_factory(owner, "editor")
    project_id = await flagged_project(app, editor)
    await set_mode(editor, project_id, "exclude")
    agent_id = await agent(editor, project_id)
    document_id, chunk = await product_chunk(editor, project_id)
    assert chunk["flag"] is not None

    cleared = await editor.client.delete(flag_path(editor, project_id, document_id, chunk["id"]))

    assert cleared.status_code == 204, cleared.text
    _, after = await product_chunk(editor, project_id)
    assert after["flag"] is None
    listed = {d["id"]: d for d in await documents(editor, project_id)}
    assert listed[document_id]["flagged_chunk_count"] == 0
    found = await traced(editor, project_id, agent_id)
    assert given(found)[0] == PRODUCT
    assert left_out_by_the_scan(found) == []
    events = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/audit-events",
        params={"action": "chunk.flag_cleared"},
    )
    (event,) = events.json()["items"]
    assert (event["actor"]["id"], event["target"]) == (
        editor.member_id,
        {"type": "chunk", "id": chunk["id"]},
    )
    assert event["before"] == {
        "project_id": project_id,
        "document_id": document_id,
        "document_name": "product.txt",
        "label": "prompt_injection",
        "score": 0.97,
        "reason": "Flagged by the test",
    }
    assert event["after"] == {"flag": None}
    assert event["occurred_at"] == "2026-11-05T09:00:00Z"


async def test_a_chunk_that_isnt_flagged_has_no_flag_to_clear(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await flagged_project(app, owner)
    by_name = {d["name"]: d["id"] for d in await documents(owner, project_id)}
    (leave,) = await chunks(owner, project_id, by_name["leave.txt"])
    assert leave["text"] == LEAVE

    response = await owner.client.delete(
        flag_path(owner, project_id, by_name["leave.txt"], leave["id"])
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "This Chunk isn't flagged."


async def test_clearing_needs_the_chunk_in_that_document_of_that_project(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    project_id = await flagged_project(app, owner)
    document_id, chunk = await product_chunk(owner, project_id)
    by_name = {d["name"]: d["id"] for d in await documents(owner, project_id)}
    other_project = await knowledge_base(app, owner, "Sales")
    stranger = await tenant_factory()

    wrong_document = await owner.client.delete(
        flag_path(owner, project_id, by_name["leave.txt"], chunk["id"])
    )
    wrong_project = await owner.client.delete(
        flag_path(owner, other_project, document_id, chunk["id"])
    )
    other_tenant = await stranger.client.delete(
        f"/api/organisations/{stranger.organisation_id}/projects/{project_id}"
        f"/documents/{document_id}/chunks/{chunk['id']}/flag"
    )

    assert [wrong_document.status_code, wrong_project.status_code] == [404, 404]
    assert other_tenant.status_code == 404
    _, after = await product_chunk(owner, project_id)
    assert after["flag"] is not None


async def test_an_archived_projects_flags_cant_be_cleared(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await flagged_project(app, owner)
    document_id, chunk = await product_chunk(owner, project_id)
    archived = await owner.client.post(f"{project_path(owner, project_id)}/archive")
    assert archived.status_code == 200, archived.text

    response = await owner.client.delete(flag_path(owner, project_id, document_id, chunk["id"]))

    assert response.status_code == 409
    assert response.json()["detail"] == "This Project is archived. An Owner can restore it."
