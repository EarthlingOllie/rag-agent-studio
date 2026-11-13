"""API seam: the Chunks the ingestion Guardrail scan flags are quarantined. A flagged Chunk is
never a retrieval candidate, whatever the Project or Agent settings: no setting lets a detected
prompt injection into the model's context. The Trace lists it as left out by the scan. An Editor
reviews it (its text and why it was flagged) and may allow that one Chunk into the corpus as a
false positive: the allow keeps the flag, records who allowed it and when, and is an Audit
Event. Everything is driven and observed through the API, with the rule-driven fake classifier
and the fixture Knowledge Base."""

from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo
from sqlalchemy import update

from app.documents.models import Chunk
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


def allow_path(member: SignedUpMember, project_id: str, document_id: str, chunk_id: str) -> str:
    return f"{project_path(member, project_id)}/documents/{document_id}/chunks/{chunk_id}/allow"


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


# Quarantine


async def test_a_flagged_chunk_is_quarantined_and_never_reaches_the_model(
    app: FastAPI, owner: SignedUpMember
) -> None:
    prompts.clear()
    answer_with(app, recording)
    await use_default_model(owner)
    project_id = await flagged_project(app, owner)
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


async def test_no_project_setting_lets_flagged_chunks_back_in(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, recording)
    await use_default_model(owner)
    project_id = await flagged_project(app, owner)
    agent_id = await agent(owner, project_id)

    # The old per-Project "mark" mode is gone: asking for it changes nothing.
    patched = await owner.client.patch(
        project_path(owner, project_id), json={"flagged_chunk_mode": "mark"}
    )
    found = await traced(owner, project_id, agent_id)

    assert patched.status_code == 200, patched.text
    assert "flagged_chunk_mode" not in patched.json()
    assert left_out_by_the_scan(found) == [PRODUCT]


async def test_the_document_lists_its_quarantined_chunks_for_review(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await flagged_project(app, owner)
    document_id, chunk = await product_chunk(owner, project_id)

    listed = {d["id"]: d for d in await documents(owner, project_id)}
    flagged_only = await owner.client.get(
        f"{project_path(owner, project_id)}/documents/{document_id}/chunks",
        params={"flagged": True},
    )
    leave_id = next(d["id"] for d in listed.values() if d["name"] == "leave.txt")
    none_flagged = await owner.client.get(
        f"{project_path(owner, project_id)}/documents/{leave_id}/chunks",
        params={"flagged": True},
    )

    assert (
        listed[document_id]["flagged_chunk_count"],
        listed[document_id]["quarantined_chunk_count"],
    ) == (1, 1)
    assert listed[leave_id]["quarantined_chunk_count"] == 0
    assert chunk["text"] == PRODUCT
    assert chunk["flag"] == {
        "label": "prompt_injection",
        "score": 0.97,
        "reason": "Flagged by the test",
        "allowed": None,
    }
    assert [c["id"] for c in flagged_only.json()["items"]] == [chunk["id"]]
    assert flagged_only.json()["total"] == 1
    assert none_flagged.json() == {"items": [], "total": 0, "offset": 0, "limit": 50}


# Allowing a false positive


async def test_an_editor_allows_a_false_positive_and_only_that_chunk_is_retrieved_again(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    answer_with(app, recording)
    await use_default_model(owner)
    editor = await member_factory(owner, "editor")
    project_id = await flagged_project(app, editor)
    agent_id = await agent(editor, project_id)
    document_id, chunk = await product_chunk(editor, project_id)

    allowed = await editor.client.post(allow_path(editor, project_id, document_id, chunk["id"]))

    assert allowed.status_code == 200, allowed.text
    allowance = {
        "allowed_at": "2026-11-05T09:00:00Z",
        "allowed_by": {"id": editor.member_id, "name": editor.name},
    }
    # The flag is kept, with who allowed the Chunk and when.
    assert allowed.json()["flag"] == {
        "label": "prompt_injection",
        "score": 0.97,
        "reason": "Flagged by the test",
        "allowed": allowance,
    }
    _, after = await product_chunk(editor, project_id)
    assert after["flag"]["allowed"] == allowance
    listed = {d["id"]: d for d in await documents(editor, project_id)}
    assert (
        listed[document_id]["flagged_chunk_count"],
        listed[document_id]["quarantined_chunk_count"],
    ) == (1, 0)
    found = await traced(editor, project_id, agent_id)
    assert given(found)[0] == PRODUCT
    assert left_out_by_the_scan(found) == []
    events = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/audit-events",
        params={"action": "chunk.allowed"},
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
        "text": PRODUCT,
        "quarantined": True,
    }
    assert event["after"] == {"quarantined": False}
    assert event["occurred_at"] == "2026-11-05T09:00:00Z"


async def test_a_chunk_is_allowed_once(app: FastAPI, owner: SignedUpMember) -> None:
    project_id = await flagged_project(app, owner)
    document_id, chunk = await product_chunk(owner, project_id)
    first = await owner.client.post(allow_path(owner, project_id, document_id, chunk["id"]))

    again = await owner.client.post(allow_path(owner, project_id, document_id, chunk["id"]))

    assert first.status_code == 200, first.text
    assert again.status_code == 409
    assert again.json()["detail"] == "This Chunk is already allowed."


async def test_a_chunk_that_isnt_flagged_has_nothing_to_allow(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await flagged_project(app, owner)
    by_name = {d["name"]: d["id"] for d in await documents(owner, project_id)}
    (leave,) = await chunks(owner, project_id, by_name["leave.txt"])
    assert leave["text"] == LEAVE

    response = await owner.client.post(
        allow_path(owner, project_id, by_name["leave.txt"], leave["id"])
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "This Chunk isn't flagged."


async def test_allowing_needs_the_chunk_in_that_document_of_that_project(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    project_id = await flagged_project(app, owner)
    document_id, chunk = await product_chunk(owner, project_id)
    by_name = {d["name"]: d["id"] for d in await documents(owner, project_id)}
    other_project = await knowledge_base(app, owner, "Sales")
    stranger = await tenant_factory()

    wrong_document = await owner.client.post(
        allow_path(owner, project_id, by_name["leave.txt"], chunk["id"])
    )
    wrong_project = await owner.client.post(
        allow_path(owner, other_project, document_id, chunk["id"])
    )
    other_tenant = await stranger.client.post(
        f"/api/organisations/{stranger.organisation_id}/projects/{project_id}"
        f"/documents/{document_id}/chunks/{chunk['id']}/allow"
    )

    assert [wrong_document.status_code, wrong_project.status_code] == [404, 404]
    assert other_tenant.status_code == 404
    _, after = await product_chunk(owner, project_id)
    assert after["flag"]["allowed"] is None


async def test_an_archived_projects_chunks_cant_be_allowed(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await flagged_project(app, owner)
    document_id, chunk = await product_chunk(owner, project_id)
    archived = await owner.client.post(f"{project_path(owner, project_id)}/archive")
    assert archived.status_code == 200, archived.text

    response = await owner.client.post(allow_path(owner, project_id, document_id, chunk["id"]))

    assert response.status_code == 409
    assert response.json()["detail"] == "This Project is archived. An Owner can restore it."


async def test_an_allow_whose_member_account_is_gone_still_says_when(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    project_id = await flagged_project(app, owner)
    document_id, chunk = await product_chunk(owner, project_id)
    await owner.client.post(allow_path(owner, project_id, document_id, chunk["id"]))
    # The allowing Member's account was removed (the foreign key sets the column to null).
    async with app.state.sessionmaker() as session:
        await session.execute(
            update(Chunk).where(Chunk.id == chunk["id"]).values(guardrail_allowed_by_id=None)
        )
        await session.commit()

    _, after = await product_chunk(owner, project_id)

    assert after["flag"]["allowed"] == {"allowed_at": "2026-11-05T09:00:00Z", "allowed_by": None}
