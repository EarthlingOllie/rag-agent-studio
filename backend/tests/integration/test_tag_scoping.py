"""API seam: Tag scoping. Two Agents share one Project but are limited to Documents with
different Tags, so each is given only its own material; the Trace shows what scoping left out.
Everything is driven and observed through the API, as the Studio does it."""

from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo

from tests.agents import (
    answer_with,
    ask,
    create_agent,
    parse_sse,
    save_draft,
    start_conversation,
    trace_path,
    use_default_model,
)
from tests.conftest import MemberFactory, SignedUpMember
from tests.documents import documents, project_path
from tests.knowledge_base import EXPENSES, LEAVE, PRODUCT, PRODUCT_QUESTION, knowledge_base


async def tag(member: SignedUpMember, project_id: str, name: str, filenames: list[str]) -> str:
    """Creates a Tag and applies it to the named Documents; returns its ID."""
    created = await member.client.post(
        f"{project_path(member, project_id)}/tags", json={"name": name}
    )
    assert created.status_code == 201, created.text
    tag_id: str = created.json()["id"]
    if not filenames:
        return tag_id
    by_name = {d["name"]: d["id"] for d in await documents(member, project_id)}
    applied = await member.client.post(
        f"{project_path(member, project_id)}/documents/tags",
        json={"document_ids": [by_name[f] for f in filenames], "add": [tag_id]},
    )
    assert applied.status_code == 204, applied.text
    return tag_id


async def scoped_agent(
    member: SignedUpMember, project_id: str, name: str, tag_ids: list[str]
) -> str:
    agent_id: str = (await create_agent(member, project_id, name))["id"]
    saved = await save_draft(
        member, project_id, agent_id, {"retrieval": {"tag_ids": tag_ids, "top_k": 3}}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["draft"]["retrieval"]["tag_ids"] == tag_ids
    return agent_id


async def no_idea(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
    yield "Let me check."


async def traced(
    member: SignedUpMember, project_id: str, agent_id: str, question: str
) -> list[dict[str, Any]]:
    """Asks ``question`` in a new Playground Conversation; returns the Trace's Chunks."""
    conversation = await start_conversation(member, project_id, agent_id)
    response = await ask(member, project_id, agent_id, conversation["id"], question)
    assert response.status_code == 200, response.text
    (done,) = [data for event, data in parse_sse(response.text) if event == "done"]
    trace = await member.client.get(
        trace_path(member, project_id, agent_id, conversation["id"], done["message_id"])
    )
    assert trace.status_code == 200, trace.text
    chunks: list[dict[str, Any]] = trace.json()["chunks"]
    return chunks


async def test_agents_sharing_a_project_are_given_only_their_tags_material(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    answer_with(app, no_idea)
    await use_default_model(owner)
    editor = await member_factory(owner, "editor")
    project_id = await knowledge_base(app, editor)
    hr = await tag(editor, project_id, "HR", ["leave.txt", "expenses.txt"])
    sales = await tag(editor, project_id, "Sales", ["product.txt"])
    hr_agent = await scoped_agent(editor, project_id, "HR helper", [hr])
    sales_agent = await scoped_agent(editor, project_id, "Sales helper", [sales])
    everyone = await scoped_agent(editor, project_id, "Front desk", [])

    hr_chunks = await traced(editor, project_id, hr_agent, PRODUCT_QUESTION)
    sales_chunks = await traced(editor, project_id, sales_agent, PRODUCT_QUESTION)
    everyone_chunks = await traced(editor, project_id, everyone, PRODUCT_QUESTION)

    def given(chunks: list[dict[str, Any]]) -> list[str]:
        return [c["text"] for c in chunks if c["excluded_reason"] is None]

    def outside(chunks: list[dict[str, Any]]) -> list[str]:
        return [c["text"] for c in chunks if c["excluded_reason"] == "outside_tags"]

    # The HR helper is given only HR material, even though the product Chunk matches best;
    # the Trace shows the product Chunk was left out by the Tags.
    assert sorted(given(hr_chunks)) == sorted([LEAVE, EXPENSES])
    assert outside(hr_chunks)[0] == PRODUCT
    assert len(outside(hr_chunks)) == 3
    assert set(outside(hr_chunks)).isdisjoint(given(hr_chunks))
    # The Sales helper, in the same Project, is given only the product.
    assert given(sales_chunks) == [PRODUCT]
    assert PRODUCT not in outside(sales_chunks)
    # An Agent with no Tags searches every Document and nothing is left out by Tags.
    assert given(everyone_chunks)[0] == PRODUCT
    assert len(given(everyone_chunks)) == 3
    assert outside(everyone_chunks) == []


async def test_each_tag_lists_the_agents_scoped_to_it_so_deleting_it_can_warn(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await knowledge_base(app, editor)
    hr = await tag(editor, project_id, "HR", ["leave.txt"])
    policies = await tag(editor, project_id, "Policies", [])
    unused = await tag(editor, project_id, "Unused", [])
    hr_agent = await scoped_agent(editor, project_id, "HR helper", [hr, policies])
    onboarding = await scoped_agent(editor, project_id, "Onboarding", [hr])
    await scoped_agent(editor, project_id, "Front desk", [])
    # An Agent in another Project can't be scoped to these Tags; its own Tag is listed there.
    other_project = await knowledge_base(app, editor, "Sales")
    other_tag = await tag(editor, other_project, "HR", [])
    await scoped_agent(editor, other_project, "Sales helper", [other_tag])

    listed = await editor.client.get(f"{project_path(editor, project_id)}/tags")
    renamed = await editor.client.patch(
        f"{project_path(editor, project_id)}/tags/{policies}", json={"name": "Rules"}
    )
    created = await editor.client.post(
        f"{project_path(editor, project_id)}/tags", json={"name": "New"}
    )

    agents = {t["id"]: t["agents"] for t in listed.json()}
    # Each Tag names the Agents whose Draft is scoped to it, by name.
    assert agents[hr] == [
        {"id": hr_agent, "name": "HR helper"},
        {"id": onboarding, "name": "Onboarding"},
    ]
    assert agents[policies] == [{"id": hr_agent, "name": "HR helper"}]
    assert agents[unused] == []
    assert renamed.json()["agents"] == [{"id": hr_agent, "name": "HR helper"}]
    assert created.json()["agents"] == []

    # Deleting the Tag takes it out of those Drafts; it no longer names them.
    deleted = await editor.client.delete(f"{project_path(editor, project_id)}/tags/{hr}")
    assert deleted.status_code == 204
    after = await editor.client.get(f"{project_path(editor, project_id)}/tags")
    assert {t["name"]: t["agents"] for t in after.json()} == {
        "Rules": [{"id": hr_agent, "name": "HR helper"}],
        "Unused": [],
        "New": [],
    }
