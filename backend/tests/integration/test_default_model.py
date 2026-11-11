"""API seam: the model list per credential and capability, and the Organisation's Default Model.

Credentials are added through the API with the fake verifier. Everything is observed through
the API, including Audit Events and the refusal to delete a credential the Default Model uses.
"""

import asyncio
import json
import uuid
from datetime import timedelta
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.default_model.service import default_chat_model
from app.gateway.gateway import ModelGateway
from app.gateway.live import LiveModelAdapters
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.fakes.clock import ControllableClock
from tests.integration.test_provider_credentials import (
    OPENAI_KEY,
    VOYAGE_KEY,
    added,
    audit_events,
    credentials_path,
)
from tests.unit.test_model_gateway import NO_BEDROCK, openai_completion

GPT_MODELS = [
    {"id": "gpt-4.1", "name": "GPT-4.1", "supports_tools": True},
    {"id": "gpt-4.1-mini", "name": "GPT-4.1 mini", "supports_tools": True},
    {"id": "gpt-4o-mini", "name": "GPT-4o mini", "supports_tools": True},
]


def default_model_path(organisation_id: str) -> str:
    return f"/api/organisations/{organisation_id}/default-model"


async def models(member: SignedUpMember, credential_id: str, capability: str) -> Any:
    response = await member.client.get(
        credentials_path(member.organisation_id, credential_id, "models", capability)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def default_model(member: SignedUpMember) -> Any:
    response = await member.client.get(default_model_path(member.organisation_id))
    assert response.status_code == 200, response.text
    return response.json()


async def set_default(owner: SignedUpMember, credential_id: str, model: str) -> Any:
    return await owner.client.put(
        default_model_path(owner.organisation_id),
        json={"credential_id": credential_id, "model": model},
    )


# Models per credential and capability


async def test_a_credentials_models_are_listed_per_capability(owner: SignedUpMember) -> None:
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY)
    voyage = await added(owner, provider="voyage", api_key=VOYAGE_KEY)

    assert await models(owner, openai["id"], "chat") == GPT_MODELS
    assert await models(owner, openai["id"], "embeddings") == [
        {"id": "text-embedding-3-small", "name": "text-embedding-3-small", "supports_tools": False},
        {"id": "text-embedding-3-large", "name": "text-embedding-3-large", "supports_tools": False},
    ]
    assert await models(owner, openai["id"], "rerank") == []
    assert await models(owner, voyage["id"], "chat") == []
    assert await models(owner, voyage["id"], "rerank") == [
        {"id": "rerank-2.5", "name": "rerank-2.5", "supports_tools": False},
        {"id": "rerank-2.5-lite", "name": "rerank-2.5-lite", "supports_tools": False},
    ]


async def test_only_the_capabilities_a_credential_was_given_have_models(
    owner: SignedUpMember,
) -> None:
    embeddings_only = await added(
        owner, provider="openai", api_key=OPENAI_KEY, capabilities=["embeddings"]
    )

    assert await models(owner, embeddings_only["id"], "chat") == []
    assert len(await models(owner, embeddings_only["id"], "embeddings")) == 2


async def test_an_unknown_capability_or_credential_is_refused(owner: SignedUpMember) -> None:
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY)

    unknown_capability = await owner.client.get(
        credentials_path(owner.organisation_id, openai["id"], "models", "speech")
    )
    unknown_credential = await owner.client.get(
        credentials_path(owner.organisation_id, str(uuid.uuid4()), "models", "chat")
    )

    assert unknown_capability.status_code == 422
    assert unknown_credential.status_code == 404
    assert unknown_credential.json() == {"detail": "Not found"}


async def test_editors_see_a_credentials_models(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY)
    editor = await member_factory(owner, "editor")

    assert await models(editor, openai["id"], "chat") == GPT_MODELS


# The Default Model


async def test_an_organisation_starts_without_a_default_model(owner: SignedUpMember) -> None:
    assert await default_model(owner) is None


async def test_an_owner_sets_the_default_model_from_a_chat_credential(
    owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY, name="Marketing OpenAI")
    editor = await member_factory(owner, "editor")

    response = await set_default(owner, openai["id"], "gpt-4.1-mini")

    expected = {
        "credential_id": openai["id"],
        "credential_name": "Marketing OpenAI",
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "model_name": "GPT-4.1 mini",
        "supports_tools": True,
        "updated_at": "2026-11-05T09:00:00Z",
    }
    assert response.status_code == 200, response.text
    assert response.json() == expected
    assert await default_model(owner) == expected
    assert await default_model(editor) == expected


async def test_changing_the_default_model_is_audited(
    owner: SignedUpMember, clock: ControllableClock
) -> None:
    anthropic = await added(owner, name="Claude")
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY, name="GPT")

    first = await set_default(owner, anthropic["id"], "claude-sonnet-4-5")
    clock.advance(timedelta(minutes=5))
    second = await set_default(owner, openai["id"], "gpt-4.1")
    unchanged = await set_default(owner, openai["id"], "gpt-4.1")

    assert first.status_code == second.status_code == unchanged.status_code == 200
    assert unchanged.json()["updated_at"] == "2026-11-05T09:05:00Z"
    later, earlier = await audit_events(owner, "default_model.changed")
    claude = {"credential_id": anthropic["id"], "credential_name": "Claude"}
    gpt = {"credential_id": openai["id"], "credential_name": "GPT"}
    assert earlier["actor"]["id"] == owner.member_id
    assert earlier["target"] == {"type": "organisation", "id": owner.organisation_id}
    assert earlier["before"] is None
    assert earlier["after"] == claude | {"provider": "anthropic", "model": "claude-sonnet-4-5"}
    assert later["before"] == earlier["after"]
    assert later["after"] == gpt | {"provider": "openai", "model": "gpt-4.1"}


@pytest.mark.parametrize(
    ("provider", "api_key", "capabilities", "model", "detail"),
    [
        (
            "voyage",
            VOYAGE_KEY,
            None,
            "voyage-3.5",
            "That credential can't be used for chat. Choose a chat-capable credential.",
        ),
        (
            "openai",
            OPENAI_KEY,
            ["embeddings"],
            "gpt-4.1",
            "That credential can't be used for chat. Choose a chat-capable credential.",
        ),
        (
            "openai",
            OPENAI_KEY,
            None,
            "text-embedding-3-small",
            "OpenAI doesn't offer text-embedding-3-small for chat.",
        ),
        ("openai", OPENAI_KEY, None, "gpt-0", "OpenAI doesn't offer gpt-0 for chat."),
    ],
)
async def test_only_a_chat_model_of_a_chat_capable_credential_can_be_the_default(
    provider: str,
    api_key: str,
    capabilities: list[str] | None,
    model: str,
    detail: str,
    owner: SignedUpMember,
) -> None:
    extra = {} if capabilities is None else {"capabilities": capabilities}
    credential = await added(owner, provider=provider, api_key=api_key, **extra)

    response = await set_default(owner, credential["id"], model)

    assert (response.status_code, response.json()) == (422, {"detail": detail})
    assert await default_model(owner) is None
    assert await audit_events(owner, "default_model.changed") == []


async def test_a_credential_from_elsewhere_cannot_be_the_default(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    other = await tenant_factory()
    theirs = await added(other, provider="openai", api_key=OPENAI_KEY)

    elsewhere = await set_default(owner, theirs["id"], "gpt-4.1")
    unknown = await set_default(owner, str(uuid.uuid4()), "gpt-4.1")

    expected = (422, {"detail": "Choose one of this Organisation's credentials."})
    assert (elsewhere.status_code, elsewhere.json()) == expected
    assert (unknown.status_code, unknown.json()) == expected
    assert await default_model(owner) is None


async def test_editors_cannot_set_the_default_model(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY)
    editor = await member_factory(owner, "editor")

    response = await set_default(editor, openai["id"], "gpt-4.1")

    assert (response.status_code, response.json()) == (403, {"detail": "Only Owners can do this"})
    assert await default_model(owner) is None


# The Default Model as a credential reference


async def test_the_default_models_credential_cannot_be_deleted(owner: SignedUpMember) -> None:
    claude = await added(owner, name="Claude")
    gpt = await added(owner, provider="openai", api_key=OPENAI_KEY, name="GPT")
    await set_default(owner, claude["id"], "claude-haiku-4-5")

    blocked = await owner.client.delete(credentials_path(owner.organisation_id, claude["id"]))
    other_one = await owner.client.delete(credentials_path(owner.organisation_id, gpt["id"]))

    assert blocked.status_code == 409
    assert blocked.json()["references"] == [
        {
            "kind": "default_model",
            "id": owner.organisation_id,
            "name": "Default Model (Claude Haiku 4.5)",
        }
    ]
    assert other_one.status_code == 204
    assert (await default_model(owner))["credential_id"] == claude["id"]


async def test_moving_the_default_model_releases_the_old_credential(
    owner: SignedUpMember,
) -> None:
    claude = await added(owner, name="Claude")
    gpt = await added(owner, provider="openai", api_key=OPENAI_KEY, name="GPT")
    await set_default(owner, claude["id"], "claude-haiku-4-5")
    await set_default(owner, gpt["id"], "gpt-4.1")

    released = await owner.client.delete(credentials_path(owner.organisation_id, claude["id"]))
    still_used = await owner.client.delete(credentials_path(owner.organisation_id, gpt["id"]))

    assert released.status_code == 204
    assert still_used.status_code == 409


async def test_another_organisations_default_model_is_not_a_reference(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    mine = await added(owner, name="Mine")
    other = await tenant_factory()
    theirs = await added(other, name="Theirs")
    await set_default(other, theirs["id"], "claude-haiku-4-5")

    response = await owner.client.delete(credentials_path(owner.organisation_id, mine["id"]))

    assert response.status_code == 204


async def test_a_credential_deleted_while_it_is_chosen_is_either_deleted_or_the_default(
    app: FastAPI, owner: SignedUpMember
) -> None:
    """Choosing a credential and deleting it at once never leaves a Default Model without one."""
    for _ in range(5):
        credential = await added(owner, provider="openai", api_key=OPENAI_KEY)
        chosen, deleted = await asyncio.gather(
            set_default(owner, credential["id"], "gpt-4.1"),
            owner.client.delete(credentials_path(owner.organisation_id, credential["id"])),
        )

        current = await default_model(owner)
        if deleted.status_code == 204:
            assert chosen.status_code == 422
            assert current is None or current["credential_id"] != credential["id"]
        else:
            assert (chosen.status_code, deleted.status_code) == (200, 409)
            assert current["credential_id"] == credential["id"]


# The Default Model through the model gateway


async def _default_chat_model(app: FastAPI, organisation_id: str) -> Model | None:
    async with app.state.sessionmaker() as session:
        model: Model | None = await default_chat_model(
            session, app.state.model_gateway, uuid.UUID(organisation_id)
        )
        return model


async def test_without_a_default_model_there_is_no_default_chat_model(
    app: FastAPI, owner: SignedUpMember
) -> None:
    assert await _default_chat_model(app, owner.organisation_id) is None


async def test_the_default_model_is_built_by_the_gateway_with_the_fake_adapters(
    app: FastAPI, owner: SignedUpMember
) -> None:
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY)
    await set_default(owner, openai["id"], "gpt-4o-mini")

    model = await _default_chat_model(app, owner.organisation_id)

    assert model is not None
    result = await Agent(model).run("Hello")
    assert result.output == "Fake reply from openai:gpt-4o-mini."


async def test_the_default_model_calls_its_provider_with_the_stored_key(
    app: FastAPI, owner: SignedUpMember
) -> None:
    """With the live adapters, the stored key is opened and sent to the provider (recorded)."""
    requests: list[httpx2.Request] = []

    def provider(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return openai_completion("Hello from the Default Model")

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(provider))
    adapters = LiveModelAdapters(client, NO_BEDROCK)
    app.state.model_gateway = ModelGateway(app.state.envelope, adapters)
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY)
    await set_default(owner, openai["id"], "gpt-4.1")

    model = await _default_chat_model(app, owner.organisation_id)

    assert model is not None
    result = await Agent(model).run("Hello")
    assert result.output == "Hello from the Default Model"
    (request,) = requests
    assert request.headers["authorization"] == f"Bearer {OPENAI_KEY}"
    assert json.loads(request.content)["model"] == "gpt-4.1"
