"""API seam: Agentic Retrieval Mode needs a chat model that supports tools.

The capability registry says which models support tools, and credential and model listings
show it. Saving an Agentic Draft whose effective model (the Model override, else the Default
Model) can't use tools is refused; an Agentic Agent whose Default Model later loses tool
support answers as Automatic, and its Trace says so. Bedrock's Mistral 7B Instruct is the
registry's chat model without tool support. Everything is observed through the API.
"""

from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCalls
from sqlalchemy import text

from tests.agents import (
    agents_path,
    answer_with,
    create_agent,
    parse_sse,
    save_draft,
    use_default_model,
)
from tests.conftest import ClientFactory, SignedUpMember
from tests.documents import create_project, project_path, upload
from tests.integration.test_agent_versions import knowledgeable_project, published
from tests.integration.test_agentic_retrieval import agentic, asked, searching
from tests.integration.test_bedrock_credentials import add_keys, created
from tests.integration.test_embed import conversation_token, send
from tests.integration.test_playground import LEAVE
from tests.integration.test_provider_credentials import OPENAI_KEY, added, credentials_path

MISTRAL = "mistral.mistral-7b-instruct-v0:2"
NEEDS_TOOLS = (
    "Agentic Retrieval Mode needs a model that supports tools, and {model} doesn't. "
    "Choose Automatic, or a model that supports tools."
)


async def bedrock_chat(owner: SignedUpMember) -> str:
    """A Bedrock access-keys credential for chat; returns its ID."""
    return str(created(await add_keys(owner, capabilities=["chat"]))["id"])


async def set_default(owner: SignedUpMember, credential_id: str, model: str) -> dict[str, Any]:
    response = await owner.client.put(
        f"/api/organisations/{owner.organisation_id}/default-model",
        json={"credential_id": credential_id, "model": model},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def draft_of(member: SignedUpMember, project_id: str, agent_id: str) -> dict[str, Any]:
    response = await member.client.get(agents_path(member, project_id, agent_id))
    assert response.status_code == 200, response.text
    draft: dict[str, Any] = response.json()["draft"]
    return draft


# The registry and the listings


async def test_the_registry_says_which_models_support_tools(owner: SignedUpMember) -> None:
    response = await owner.client.get("/api/providers")

    assert response.status_code == 200
    tools = {
        (provider["id"], capability["capability"], model["id"]): model["supports_tools"]
        for provider in response.json()
        for capability in provider["capabilities"]
        for model in capability["models"]
    }
    # Every chat model supports tools but Mistral 7B Instruct, the Demo models included.
    assert {key for key, supported in tools.items() if key[1] == "chat" and not supported} == {
        ("bedrock", "chat", MISTRAL)
    }
    assert tools[("demo", "chat", "demo-chat")] is True
    assert tools[("demo", "chat", "demo-naive")] is True
    # Embedding and rerank models aren't chat models: they call no tools.
    assert not any(supported for key, supported in tools.items() if key[1] != "chat")


async def test_a_credentials_chat_models_say_whether_they_support_tools(
    owner: SignedUpMember,
) -> None:
    bedrock = await bedrock_chat(owner)

    response = await owner.client.get(
        credentials_path(owner.organisation_id, bedrock, "models", "chat")
    )

    assert response.status_code == 200, response.text
    assert [(m["name"], m["supports_tools"]) for m in response.json()] == [
        ("Claude Sonnet 4.5", True),
        ("Claude Haiku 4.5", True),
        ("Amazon Nova Pro", True),
        ("Mistral 7B Instruct", False),
    ]


async def test_the_default_model_says_whether_it_supports_tools(owner: SignedUpMember) -> None:
    openai = await use_default_model(owner)
    assert (await set_default(owner, openai, "gpt-4.1-mini"))["supports_tools"] is True

    changed = await set_default(owner, await bedrock_chat(owner), MISTRAL)

    assert (changed["model_name"], changed["supports_tools"]) == ("Mistral 7B Instruct", False)
    read = await owner.client.get(f"/api/organisations/{owner.organisation_id}/default-model")
    assert read.json()["supports_tools"] is False


# Saving an Agentic Draft


async def test_an_agentic_draft_is_refused_when_the_default_model_cant_use_tools(
    owner: SignedUpMember,
) -> None:
    await set_default(owner, await bedrock_chat(owner), MISTRAL)
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]

    refused = await save_draft(owner, project_id, agent_id, {"retrieval": {"mode": "agentic"}})

    assert refused.status_code == 422
    assert refused.json() == {
        "detail": [
            {
                "loc": ["body", "retrieval", "mode"],
                "msg": NEEDS_TOOLS.format(model="the Default Model (Mistral 7B Instruct)"),
                "type": "model_without_tools",
            }
        ]
    }
    assert (await draft_of(owner, project_id, agent_id))["retrieval"]["mode"] == "automatic"
    # Automatic mode needs no tools, so the same Draft saves in it.
    kept = await save_draft(
        owner, project_id, agent_id, {"retrieval": {"mode": "automatic", "top_k": 4}}
    )
    assert kept.status_code == 200, kept.text


async def test_an_agentic_draft_is_refused_when_its_model_override_cant_use_tools(
    owner: SignedUpMember,
) -> None:
    await use_default_model(owner)
    bedrock = await bedrock_chat(owner)
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]
    mistral = {"credential_id": bedrock, "model": MISTRAL}

    refused = await save_draft(
        owner,
        project_id,
        agent_id,
        {"behaviour": {"model": mistral}, "retrieval": {"mode": "agentic"}},
    )

    assert refused.status_code == 422
    assert refused.json() == {
        "detail": [
            {
                "loc": ["body", "behaviour", "model", "model"],
                "msg": NEEDS_TOOLS.format(model="Mistral 7B Instruct"),
                "type": "model_without_tools",
            }
        ]
    }
    # The override is the effective model: one with tools saves, whatever the Default Model.
    nova = {"credential_id": bedrock, "model": "amazon.nova-pro-v1:0"}
    await set_default(owner, bedrock, MISTRAL)
    saved = await save_draft(
        owner,
        project_id,
        agent_id,
        {"behaviour": {"model": nova}, "retrieval": {"mode": "agentic"}},
    )
    assert saved.status_code == 200, saved.text


async def test_an_override_the_credential_doesnt_offer_is_refused_once(
    owner: SignedUpMember,
) -> None:
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY)
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]

    refused = await save_draft(
        owner,
        project_id,
        agent_id,
        {
            "behaviour": {"model": {"credential_id": openai["id"], "model": MISTRAL}},
            "retrieval": {"mode": "agentic"},
        },
    )

    # The model isn't offered at all: that is the one problem reported for it.
    assert refused.status_code == 422
    assert [(p["loc"], p["type"]) for p in refused.json()["detail"]] == [
        (["body", "behaviour", "model", "model"], "model_unavailable")
    ]


async def test_an_agentic_draft_without_any_model_is_not_refused_for_tools(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    agent_id = (await create_agent(owner, project_id))["id"]

    saved = await save_draft(owner, project_id, agent_id, {"retrieval": {"mode": "agentic"}})

    # With no model at all there is nothing to check yet: the Playground says what is missing.
    assert saved.status_code == 200, saved.text


# Answering after the Default Model lost tool support


async def answers_from_the_question(
    messages: list[ModelMessage], info: AgentInfo
) -> AsyncIterator[str | DeltaToolCalls]:
    """Searches when it is offered Knowledge Search; otherwise answers citing [C1]."""
    if info.function_tools:
        async for event in searching("annual leave", answer="Searched [C1].")(messages, info):
            yield event
        return
    yield "Leave is 25 days [C1]."


async def test_an_agentic_agent_answers_as_automatic_when_the_default_model_cant_use_tools(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, answers_from_the_question)
    await use_default_model(owner)
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "leave.txt", LEAVE.encode())
    agent_id = (await create_agent(owner, project_id))["id"]
    await agentic(owner, project_id, agent_id)
    # Changing the Default Model doesn't revalidate Drafts.
    await set_default(owner, await bedrock_chat(owner), MISTRAL)

    events, trace = await asked(owner, project_id, agent_id, "How much leave do I get?")

    # No Search: the question was answered from the Chunks found up front, as in Automatic mode.
    assert [event for event, _ in events] == ["token", "citation", "done"]
    assert events[0][1] == {"text": "Leave is 25 days [C1]."}
    assert events[1][1]["document_name"] == "leave.txt"
    assert events[2][1]["search_count"] == 0
    assert trace["automatic_fallback"] is True
    assert (trace["model_provider"], trace["model_name"]) == ("bedrock", MISTRAL)
    assert (trace["search_count"], trace["searches"]) == (0, [])
    assert [(c["document_name"], c["cited"]) for c in trace["chunks"]] == [("leave.txt", True)]
    # The Draft is still Agentic.
    assert (await draft_of(owner, project_id, agent_id))["retrieval"]["mode"] == "agentic"


async def test_an_agentic_reply_on_a_model_with_tools_has_no_fallback_warning(
    app: FastAPI, owner: SignedUpMember
) -> None:
    answer_with(app, answers_from_the_question)
    await use_default_model(owner)
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "leave.txt", LEAVE.encode())
    agent_id = (await create_agent(owner, project_id))["id"]
    await agentic(owner, project_id, agent_id)

    events, trace = await asked(owner, project_id, agent_id, "How much leave do I get?")

    assert events[0][0] == "search"
    assert (trace["automatic_fallback"], trace["search_count"]) == (False, 1)


async def test_a_visitor_of_an_agentic_live_version_is_answered_as_automatic_after_the_change(
    app: FastAPI, owner: SignedUpMember, new_client: ClientFactory
) -> None:
    project_id = await knowledgeable_project(app, owner)
    answer_with(app, answers_from_the_question)
    created_agent = await create_agent(owner, project_id)
    await agentic(owner, project_id, created_agent["id"])
    await published(owner, project_id, created_agent["id"])
    await set_default(owner, await bedrock_chat(owner), MISTRAL)
    visitor: httpx.AsyncClient = await new_client()
    token = await conversation_token(visitor, created_agent["public_id"])

    response = await send(visitor, created_agent["public_id"], token, "How much leave?")

    assert response.status_code == 200, response.text
    events = parse_sse(response.text)
    answer = "".join(data["text"] for event, data in events if event == "token")
    assert answer == "Leave is 25 days [C1]."
    message_id = events[-1][1]["message_id"]
    async with app.state.sessionmaker() as session:
        conversation_id = await session.scalar(
            text("SELECT conversation_id::text FROM messages WHERE id = :id"), {"id": message_id}
        )
    trace = await owner.client.get(
        f"{project_path(owner, project_id)}/conversations/{conversation_id}/messages/"
        f"{message_id}/trace"
    )
    assert trace.status_code == 200, trace.text
    assert (trace.json()["automatic_fallback"], trace.json()["search_count"]) == (True, 0)
