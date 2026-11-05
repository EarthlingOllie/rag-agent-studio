"""Helpers for driving Agents and the Playground through the API, as the Studio does."""

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.credentials.registry import Provider
from app.gateway.fakes import FakeModelAdapters
from tests.conftest import SignedUpMember
from tests.documents import project_path
from tests.integration.test_provider_credentials import OPENAI_KEY, added

StreamFunction = Callable[[list[ModelMessage], AgentInfo], AsyncIterator[str]]


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
