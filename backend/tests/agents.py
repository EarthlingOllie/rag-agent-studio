"""Helpers for driving Agents and the Playground through the API, as the Studio does."""

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCalls, FunctionModel

from app.credentials.registry import Provider
from app.gateway.fakes import FakeModelAdapters
from tests.conftest import SignedUpMember
from tests.documents import project_path
from tests.integration.test_provider_credentials import OPENAI_KEY, added

# A new Agent's Draft: every AgentConfig group at its defaults, as the API returns it.
FULL_DEFAULT_DRAFT: dict[str, Any] = {
    "behaviour": {
        "system_prompt": "",
        "model": None,
        "temperature": 0.7,
        "max_output_tokens": 1024,
        "remembered_turns": 5,
        "fallback_text": "Sorry, I don't know the answer to that.",
    },
    "retrieval": {
        "top_k": 5,
        "hybrid_weight": 0.5,
        "min_score": 0,
        "tag_ids": [],
        "reranker": None,
        "citations": True,
        "mode": "automatic",
        "search_limit": 3,
    },
    "experience": {
        "display_name": "",
        "avatar_url": None,
        "greeting": "",
        "starter_questions": [],
        "ui_text": {"send_button": None, "rate_conversation": None, "unavailable_message": None},
        "rating_prompt_after": 3,
    },
    "guardrails": {
        "input_mode": "block",
        "classifier": None,
        "fail_mode": "closed",
        "refusal_text": "Sorry, I can't help with that request.",
    },
}

# Streams the answer's text; or, to call a tool (Knowledge Search), the tool call.
StreamFunction = Callable[[list[ModelMessage], AgentInfo], AsyncIterator[str | DeltaToolCalls]]


def agents_path(member: SignedUpMember, project_id: str, *rest: str) -> str:
    return "/".join([f"{project_path(member, project_id)}/agents", *rest])


async def create_agent(member: SignedUpMember, project_id: str, name: str = "HR helper") -> Any:
    response = await member.client.post(agents_path(member, project_id), json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


async def save_draft(
    member: SignedUpMember, project_id: str, agent_id: str, draft: dict[str, Any]
) -> httpx.Response:
    return await member.client.put(agents_path(member, project_id, agent_id, "draft"), json=draft)


async def use_default_model(owner: SignedUpMember, model: str = "gpt-4.1-mini") -> str:
    """Adds an OpenAI credential (fake verifier) and makes ``model`` the Default Model.
    Returns the credential's ID."""
    credential = await added(owner, provider="openai", api_key=OPENAI_KEY)
    response = await owner.client.put(
        f"/api/organisations/{owner.organisation_id}/default-model",
        json={"credential_id": credential["id"], "model": model},
    )
    assert response.status_code == 200, response.text
    return str(credential["id"])


def answer_with(app: FastAPI, stream: StreamFunction, *, structured: bool = False) -> list[str]:
    """Every chat model the gateway builds becomes a ``FunctionModel`` streaming ``stream``.
    With ``structured`` the model supports structured (JSON schema) output, so ``stream`` must
    stream the JSON of a cited answer; without it, the model answers in plain text.
    Returns the list the gateway appends "provider:model" to for each model it builds."""
    built: list[str] = []

    def chat(provider: Provider, secret: str, model: str) -> FunctionModel:
        built.append(f"{provider}:{model}")
        return FunctionModel(
            stream_function=stream,
            model_name=model,
            profile={"supports_json_schema_output": structured},
        )

    app.state.model_gateway.adapters = FakeModelAdapters(chat=chat)
    return built


def trace_path(
    member: SignedUpMember, project_id: str, agent_id: str, conversation_id: str, message_id: str
) -> str:
    return playground_path(
        member, project_id, agent_id, conversation_id, "messages", message_id, "trace"
    )


def playground_path(member: SignedUpMember, project_id: str, agent_id: str, *rest: str) -> str:
    return "/".join(
        [agents_path(member, project_id, agent_id), "playground", "conversations", *rest]
    )


async def start_conversation(member: SignedUpMember, project_id: str, agent_id: str) -> Any:
    response = await member.client.post(playground_path(member, project_id, agent_id))
    assert response.status_code == 201, response.text
    return response.json()


def parse_sse(body: str) -> list[tuple[str, Any]]:
    """The (event, data) pairs of a Server-Sent Events body."""
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


async def ask(
    member: SignedUpMember, project_id: str, agent_id: str, conversation_id: str, question: str
) -> httpx.Response:
    return await member.client.post(
        playground_path(member, project_id, agent_id, conversation_id, "messages"),
        json={"content": question},
    )


def answer_text(response: httpx.Response) -> str:
    """The answer a Playground stream sent: its ``token`` events joined."""
    return "".join(data["text"] for event, data in parse_sse(response.text) if event == "token")
