"""API seam: a Project's Embedding Model, the models an Organisation can choose from, and the
retrieval probe.

Provider models are called through the model gateway's fake adapters (deterministic, offline,
vectors of the registered dimension); a failing provider is a gateway with failing adapters.
Ingestion runs eagerly through the fake converter. Everything is observed through the API.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import httpx
import httpx2
import pytest
from fastapi import FastAPI
from pydantic_ai.embeddings import EmbeddingModel, EmbeddingResult, EmbeddingSettings
from pydantic_ai.embeddings.result import EmbedInputType
from pydantic_ai.exceptions import ModelHTTPError
from sqlalchemy import text

from app.credentials.registry import Provider
from app.gateway.fakes import FakeModelAdapters
from app.gateway.gateway import ModelGateway
from app.gateway.ports import BedrockAccount
from tests.conftest import MemberFactory, SignedUpMember, TenantFactory
from tests.documents import chunks, create_project, documents, project_path, upload
from tests.fakes.clock import ControllableClock
from tests.integration.test_bedrock_credentials import (
    ACCESS_KEY_ID,
    ROLE_ARN,
    SECRET_ACCESS_KEY,
    add_keys,
    add_role,
    created,
    setup_of,
)
from tests.integration.test_provider_credentials import (
    OPENAI_KEY,
    VOYAGE_KEY,
    added,
    audit_events,
    credentials_path,
)

LOCAL = "multilingual-e5-small"
PROJECT_HAS_DOCUMENTS = (
    "The Embedding Model can't be changed while the Project has Documents. "
    "Delete its Documents first."
)


def embedding_models_path(organisation_id: str) -> str:
    return f"/api/organisations/{organisation_id}/embedding-models"


async def choices(member: SignedUpMember) -> list[dict[str, Any]]:
    response = await member.client.get(embedding_models_path(member.organisation_id))
    assert response.status_code == 200, response.text
    listed: list[dict[str, Any]] = response.json()
    return listed


async def choose(
    member: SignedUpMember, project_id: str, model_id: str, credential_id: str | None = None
) -> httpx.Response:
    return await member.client.put(
        f"{project_path(member, project_id)}/embedding-model",
        json={"model_id": model_id, "credential_id": credential_id},
    )


async def project(member: SignedUpMember, project_id: str) -> dict[str, Any]:
    response = await member.client.get(project_path(member, project_id))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def probe(
    member: SignedUpMember, project_id: str, query: str, top_k: int | None = None
) -> httpx.Response:
    body: dict[str, Any] = {"query": query}
    if top_k is not None:
        body["top_k"] = top_k
    return await member.client.post(
        f"{project_path(member, project_id)}/retrieval-probe", json=body
    )


async def probed(
    member: SignedUpMember, project_id: str, query: str, top_k: int | None = None
) -> dict[str, Any]:
    response = await probe(member, project_id, query, top_k)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


class FailingEmbeddingModel(EmbeddingModel):
    """A provider that answers every embedding request with an error."""

    @property
    def model_name(self) -> str:
        return "failing"

    @property
    def system(self) -> str:
        return "failing"

    async def embed(
        self,
        inputs: str | Sequence[str],
        *,
        input_type: EmbedInputType,
        settings: EmbeddingSettings | None = None,
    ) -> EmbeddingResult:
        raise ModelHTTPError(503, "failing", {"error": "overloaded"})


class WrongSizeEmbeddingModel(FailingEmbeddingModel):
    """A provider that answers with vectors of the wrong size."""

    async def embed(
        self,
        inputs: str | Sequence[str],
        *,
        input_type: EmbedInputType,
        settings: EmbeddingSettings | None = None,
    ) -> EmbeddingResult:
        texts, _ = self.prepare_embed(inputs, settings)
        return EmbeddingResult(
            [[1.0, 0.0] for _ in texts],
            inputs=texts,
            input_type=input_type,
            model_name="wrong",
            provider_name="wrong",
        )


class ProviderAdapters(FakeModelAdapters):
    def __init__(self, embedder: type[EmbeddingModel]) -> None:
        super().__init__()
        self._embedder = embedder

    def embedder(self, provider: Provider, secret: str, model: str) -> EmbeddingModel:
        return self._embedder()


def install_provider(app: FastAPI, embedder: type[EmbeddingModel]) -> None:
    """Makes every provider embedding call, in ingestion and the probe, go to ``embedder``."""
    install_adapters(app, ProviderAdapters(embedder))


def install_adapters(app: FastAPI, adapters: FakeModelAdapters) -> None:
    """Makes ingestion and the probe build their models with ``adapters``."""

    def open_gateway(http: httpx2.AsyncClient) -> ModelGateway:
        return ModelGateway(app.state.envelope, adapters)

    app.state.ingestion.open_gateway = open_gateway
    app.state.model_gateway = ModelGateway(app.state.envelope, adapters)


# The registry of choices


async def test_new_projects_use_the_local_embedding_model(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)

    created_project = await project(owner, project_id)

    assert created_project["embedding_model_id"] == LOCAL
    assert created_project["embedding_credential_id"] is None


async def test_without_credentials_only_the_local_model_can_be_chosen(
    owner: SignedUpMember,
) -> None:
    await added(owner, name="Claude")  # chat only, so it offers no Embedding Model

    assert await choices(owner) == [
        {
            "model_id": LOCAL,
            "name": "multilingual-e5-small (built in)",
            "provider": "local",
            "dimension": 384,
            "tokenizer": "intfloat/multilingual-e5-small",
            "token_limit": 512,
            "credential_id": None,
            "credential_name": None,
        }
    ]


async def test_embedding_capable_credentials_offer_their_providers_models(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY, name="OpenAI")
    await added(
        owner, provider="openai", api_key=OPENAI_KEY, name="Chat only", capabilities=["chat"]
    )
    voyage = await added(owner, provider="voyage", api_key=VOYAGE_KEY, name="Voyage")
    editor = await member_factory(owner, "editor")

    listed = await choices(editor)

    assert [(c["model_id"], c["credential_name"]) for c in listed] == [
        (LOCAL, None),
        ("text-embedding-3-small", "OpenAI"),
        ("text-embedding-3-large", "OpenAI"),
        ("voyage-3.5", "Voyage"),
        ("voyage-3.5-lite", "Voyage"),
        ("voyage-multilingual-2", "Voyage"),
    ]
    by_model = {c["model_id"]: c for c in listed}
    assert by_model["voyage-3.5"] == {
        "model_id": "voyage-3.5",
        "name": "voyage-3.5",
        "provider": "voyage",
        "dimension": 1024,
        "tokenizer": "voyageai/voyage-3.5",
        "token_limit": 32000,
        "credential_id": voyage["id"],
        "credential_name": "Voyage",
    }
    assert by_model["text-embedding-3-large"]["dimension"] == 3072
    assert by_model["text-embedding-3-small"]["credential_id"] == openai["id"]


async def test_another_organisations_credentials_are_not_offered(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    other = await tenant_factory()
    await added(other, provider="voyage", api_key=VOYAGE_KEY)

    assert [c["model_id"] for c in await choices(owner)] == [LOCAL]


# Choosing a provider model


async def test_an_editor_chooses_a_provider_model_and_documents_embed_with_it(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    voyage = await added(owner, provider="voyage", api_key=VOYAGE_KEY, name="Voyage")
    editor = await member_factory(owner, "editor")
    project_id = await create_project(editor)

    response = await choose(editor, project_id, "voyage-3.5", voyage["id"])

    assert response.status_code == 200, response.text
    assert response.json()["embedding_model_id"] == "voyage-3.5"
    assert response.json()["embedding_credential_id"] == voyage["id"]
    assert (await project(editor, project_id))["embedding_model_id"] == "voyage-3.5"

    document = await upload(app, editor, project_id, "leave.md", b"Everyone gets 25 days.")
    (listed,) = await documents(editor, project_id)
    assert listed["status"] == "ready"
    (chunk,) = await chunks(editor, project_id, document["id"])
    assert chunk["embedding_model_id"] == "voyage-3.5"

    answer = await probed(editor, project_id, "Everyone gets 25 days.")
    assert answer["embedding_model_id"] == "voyage-3.5"
    assert answer["dimension"] == 1024
    assert [hit["chunk_id"] for hit in answer["chunks"]] == [chunk["id"]]
    assert answer["chunks"][0]["score"] == pytest.approx(1.0)


async def test_the_large_openai_model_stores_and_retrieves_3072_dimension_vectors(
    app: FastAPI, owner: SignedUpMember
) -> None:
    openai = await added(owner, provider="openai", api_key=OPENAI_KEY)
    project_id = await create_project(owner)
    assert (await choose(owner, project_id, "text-embedding-3-large", openai["id"])).is_success

    document = await upload(app, owner, project_id, "a.md", b"Expenses are paid monthly.")
    (chunk,) = await chunks(owner, project_id, document["id"])

    answer = await probed(owner, project_id, "Expenses are paid monthly.")
    assert (answer["embedding_model_id"], answer["dimension"]) == ("text-embedding-3-large", 3072)
    assert answer["chunks"][0]["chunk_id"] == chunk["id"]
    assert answer["chunks"][0]["score"] == pytest.approx(1.0, abs=1e-3)


async def test_choosing_a_model_is_an_audit_event(
    owner: SignedUpMember, clock: ControllableClock
) -> None:
    voyage = await added(owner, provider="voyage", api_key=VOYAGE_KEY, name="Voyage")
    project_id = await create_project(owner, "Handbook")

    assert (await choose(owner, project_id, "voyage-3.5", voyage["id"])).is_success
    assert (await choose(owner, project_id, "voyage-3.5", voyage["id"])).is_success  # unchanged
    assert (await choose(owner, project_id, LOCAL)).is_success

    events = await audit_events(owner, "project.embedding_model_changed")
    assert [(e["before"], e["after"]) for e in reversed(events)] == [
        (
            {"model_id": LOCAL, "credential_id": None},
            {"model_id": "voyage-3.5", "credential_id": voyage["id"]},
        ),
        (
            {"model_id": "voyage-3.5", "credential_id": voyage["id"]},
            {"model_id": LOCAL, "credential_id": None},
        ),
    ]
    for event in events:
        assert event["target"] == {"type": "project", "id": project_id}
        assert event["actor"]["id"] == owner.member_id
        assert datetime.fromisoformat(event["occurred_at"]) == clock.now()


async def test_switching_back_to_the_local_model_releases_the_credential(
    owner: SignedUpMember,
) -> None:
    voyage = await added(owner, provider="voyage", api_key=VOYAGE_KEY)
    project_id = await create_project(owner)
    await choose(owner, project_id, "voyage-3.5", voyage["id"])

    back = await choose(owner, project_id, LOCAL)

    assert back.json()["embedding_model_id"] == LOCAL
    assert back.json()["embedding_credential_id"] is None
    deleted = await owner.client.delete(credentials_path(owner.organisation_id, voyage["id"]))
    assert deleted.status_code == 204


@pytest.mark.parametrize(
    ("model_id", "use_credential", "detail"),
    [
        ("no-such-model", False, "There is no Embedding Model no-such-model."),
        ("voyage-3.5", False, "Choose a Provider Credential for voyage-3.5."),
        (LOCAL, True, "The built-in Embedding Model doesn't use a Provider Credential."),
        (
            "text-embedding-3-small",
            True,
            "Voyage AI doesn't offer text-embedding-3-small for embeddings.",
        ),
    ],
)
async def test_an_impossible_choice_is_refused(
    owner: SignedUpMember, model_id: str, use_credential: bool, detail: str
) -> None:
    voyage = await added(owner, provider="voyage", api_key=VOYAGE_KEY)
    project_id = await create_project(owner)

    response = await choose(owner, project_id, model_id, voyage["id"] if use_credential else None)

    assert (response.status_code, response.json()) == (422, {"detail": detail})
    assert (await project(owner, project_id))["embedding_model_id"] == LOCAL


async def test_a_credential_without_the_embeddings_capability_is_refused(
    owner: SignedUpMember,
) -> None:
    chat_only = await added(owner, provider="openai", api_key=OPENAI_KEY, capabilities=["chat"])
    project_id = await create_project(owner)

    response = await choose(owner, project_id, "text-embedding-3-small", chat_only["id"])

    assert response.status_code == 422
    assert response.json() == {"detail": "This credential can't be used for embeddings."}


async def test_another_organisations_credential_cannot_be_chosen(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    other = await tenant_factory()
    theirs = await added(other, provider="voyage", api_key=VOYAGE_KEY)
    project_id = await create_project(owner)

    response = await choose(owner, project_id, "voyage-3.5", theirs["id"])

    assert (response.status_code, response.json()) == (
        422,
        {"detail": "There is no such Provider Credential in this Organisation."},
    )


async def test_an_archived_projects_model_cannot_be_changed(owner: SignedUpMember) -> None:
    voyage = await added(owner, provider="voyage", api_key=VOYAGE_KEY)
    project_id = await create_project(owner)
    await owner.client.post(f"{project_path(owner, project_id)}/archive")

    response = await choose(owner, project_id, "voyage-3.5", voyage["id"])

    assert response.status_code == 409
    assert response.json() == {"detail": "This Project is archived. An Owner can restore it."}


async def test_an_unknown_projects_model_cannot_be_changed(owner: SignedUpMember) -> None:
    response = await choose(owner, "00000000-0000-0000-0000-000000000000", LOCAL)

    assert (response.status_code, response.json()) == (404, {"detail": "Not found"})


# Changing the model is refused while the Project has Documents


async def test_the_model_cannot_change_while_the_project_has_documents(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await added(owner, provider="voyage", api_key=VOYAGE_KEY)
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "leave.md", b"Everyone gets 25 days.")

    response = await choose(owner, project_id, "voyage-3.5", voyage["id"])

    assert (response.status_code, response.json()) == (409, {"detail": PROJECT_HAS_DOCUMENTS})
    assert (await project(owner, project_id))["embedding_model_id"] == LOCAL
    assert await audit_events(owner, "project.embedding_model_changed") == []


async def test_choosing_the_current_model_again_is_allowed_with_documents(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "leave.md", b"Everyone gets 25 days.")

    response = await choose(owner, project_id, LOCAL)

    assert response.status_code == 200
    assert response.json()["embedding_model_id"] == LOCAL


# The chosen credential is a reference


async def test_a_credential_a_project_embeds_with_cannot_be_deleted(owner: SignedUpMember) -> None:
    voyage = await added(owner, provider="voyage", api_key=VOYAGE_KEY)
    project_id = await create_project(owner, "Handbook")
    await choose(owner, project_id, "voyage-3.5", voyage["id"])
    # An archived Project still holds its reference.
    await owner.client.post(f"{project_path(owner, project_id)}/archive")

    response = await owner.client.delete(credentials_path(owner.organisation_id, voyage["id"]))

    assert response.status_code == 409
    assert response.json()["references"] == [
        {"kind": "project", "id": project_id, "name": "Handbook (Embedding Model voyage-3.5)"}
    ]


async def test_another_organisations_project_is_not_a_reference(
    owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    mine = await added(owner, provider="voyage", api_key=VOYAGE_KEY)
    other = await tenant_factory()
    theirs = await added(other, provider="voyage", api_key=VOYAGE_KEY)
    their_project = await create_project(other)
    await choose(other, their_project, "voyage-3.5", theirs["id"])

    response = await owner.client.delete(credentials_path(owner.organisation_id, mine["id"]))

    assert response.status_code == 204


# Provider failures


async def test_a_provider_failure_fails_the_document_with_a_readable_message(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await added(owner, provider="voyage", api_key=VOYAGE_KEY)
    project_id = await create_project(owner)
    await choose(owner, project_id, "voyage-3.5", voyage["id"])
    install_provider(app, FailingEmbeddingModel)

    await upload(app, owner, project_id, "leave.md", b"Everyone gets 25 days.")

    (listed,) = await documents(owner, project_id)
    assert listed["status"] == "failed"
    assert listed["error_message"] == (
        "This Document couldn't be processed. Try uploading it again."
    )


async def test_vectors_of_the_wrong_size_fail_the_document(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await added(owner, provider="voyage", api_key=VOYAGE_KEY)
    project_id = await create_project(owner)
    await choose(owner, project_id, "voyage-3.5", voyage["id"])
    install_provider(app, WrongSizeEmbeddingModel)

    await upload(app, owner, project_id, "leave.md", b"Everyone gets 25 days.")

    (listed,) = await documents(owner, project_id)
    assert listed["status"] == "failed"


async def test_bedrock_credentials_offer_titan_and_cohere(owner: SignedUpMember) -> None:
    await add_keys(owner, name="Bedrock keys", capabilities=["embeddings"])
    await add_role(owner, name="Bedrock role", capabilities=["embeddings"])

    listed = await choices(owner)

    assert [(c["model_id"], c["credential_name"]) for c in listed] == [
        (LOCAL, None),
        ("amazon.titan-embed-text-v2:0", "Bedrock keys"),
        ("cohere.embed-multilingual-v3", "Bedrock keys"),
        ("amazon.titan-embed-text-v2:0", "Bedrock role"),
        ("cohere.embed-multilingual-v3", "Bedrock role"),
    ]
    titan = listed[1]
    assert (titan["provider"], titan["dimension"]) == ("bedrock", 1024)


class RecordingBedrock(FakeModelAdapters):
    """The fake adapters, recording the account each Bedrock embedder is built for."""

    def __init__(self) -> None:
        super().__init__()
        self.accounts: list[BedrockAccount] = []

    def bedrock_embedder(self, account: BedrockAccount, model: str) -> EmbeddingModel:
        self.accounts.append(account)
        return super().bedrock_embedder(account, model)


@pytest.mark.parametrize(
    "model_id", ["amazon.titan-embed-text-v2:0", "cohere.embed-multilingual-v3"]
)
async def test_a_bedrock_role_model_is_chosen_and_documents_embed_with_it(
    app: FastAPI, owner: SignedUpMember, model_id: str
) -> None:
    adapters = RecordingBedrock()
    install_adapters(app, adapters)
    external_id = (await setup_of(owner))["external_id"]
    role = created(await add_role(owner, name="Bedrock role", capabilities=["embeddings"]))
    project_id = await create_project(owner)

    response = await choose(owner, project_id, model_id, role["id"])

    assert response.status_code == 200, response.text
    assert response.json()["embedding_credential_id"] == role["id"]
    document = await upload(app, owner, project_id, "leave.md", b"Everyone gets 25 days.")
    (chunk,) = await chunks(owner, project_id, document["id"])
    assert chunk["embedding_model_id"] == model_id
    answer = await probed(owner, project_id, "Everyone gets 25 days.")
    assert (answer["embedding_model_id"], answer["dimension"]) == (model_id, 1024)
    assert [hit["chunk_id"] for hit in answer["chunks"]] == [chunk["id"]]
    # Ingestion and the probe each assumed the Owner's role with the Organisation's external ID.
    role_account = BedrockAccount("eu-west-2", ROLE_ARN, external_id)
    assert adapters.accounts == [role_account, role_account]


async def test_a_bedrock_access_keys_model_embeds_with_the_stored_keys(
    app: FastAPI, owner: SignedUpMember
) -> None:
    adapters = RecordingBedrock()
    install_adapters(app, adapters)
    keys = created(await add_keys(owner, name="Bedrock keys", capabilities=["embeddings"]))
    project_id = await create_project(owner)
    assert (await choose(owner, project_id, "amazon.titan-embed-text-v2:0", keys["id"])).is_success

    await upload(app, owner, project_id, "leave.md", b"Everyone gets 25 days.")
    (listed,) = await documents(owner, project_id)

    assert listed["status"] == "ready"
    assert adapters.accounts == [
        BedrockAccount(
            "us-east-1", access_key_id=ACCESS_KEY_ID, secret_access_key=SECRET_ACCESS_KEY
        )
    ]


# The retrieval probe


async def test_the_probe_returns_the_top_k_chunks_nearest_the_query(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    project_id = await create_project(owner)
    texts = ["Everyone gets 25 days of leave.", "Expenses are paid monthly.", "Offices open at 9."]
    uploaded = [
        await upload(app, owner, project_id, f"{i}.md", text.encode())
        for i, text in enumerate(texts)
    ]
    chunk_ids = [(await chunks(owner, project_id, d["id"]))[0]["id"] for d in uploaded]
    editor = await member_factory(owner, "editor")

    answer = await probed(editor, project_id, "Expenses are paid monthly.", top_k=2)

    assert answer["embedding_model_id"] == LOCAL
    assert answer["dimension"] == 384
    first, second = answer["chunks"]
    assert first == {
        "chunk_id": chunk_ids[1],
        "document_id": uploaded[1]["id"],
        "document_name": "1.md",
        "ordinal": 0,
        "text": "Expenses are paid monthly.",
        "heading_path": [],
        "page_start": 1,
        "page_end": 1,
        "score": pytest.approx(1.0),
    }
    assert second["chunk_id"] in {chunk_ids[0], chunk_ids[2]}
    assert second["score"] < first["score"]


async def test_the_probe_returns_five_chunks_by_default(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    for i in range(6):
        await upload(app, owner, project_id, f"{i}.md", f"Fact number {i}.".encode())

    answer = await probed(owner, project_id, "Fact number 3.")

    assert len(answer["chunks"]) == 5
    scores = [hit["score"] for hit in answer["chunks"]]
    assert scores == sorted(scores, reverse=True)
    assert answer["chunks"][0]["text"] == "Fact number 3."


async def test_the_probe_only_searches_its_own_project(app: FastAPI, owner: SignedUpMember) -> None:
    mine = await create_project(owner, "Mine")
    other = await create_project(owner, "Other")
    await upload(app, owner, other, "secret.md", b"The launch is in May.")

    answer = await probed(owner, mine, "The launch is in May.")

    assert answer["chunks"] == []


async def test_the_probe_skips_chunks_of_other_embedding_models(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "a.md", b"Everyone gets 25 days.")
    (chunk,) = await chunks(owner, project_id, document["id"])
    # Only re-embedding (ticket 03-10) writes a second model's vectors; until then a copy of the
    # Chunk under another model is written directly.
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO chunks (id, organisation_id, project_id, document_id, edition,"
                " ordinal, text, heading_path, embedding, embedding_model_id)"
                " SELECT gen_random_uuid(), organisation_id, project_id, document_id, edition,"
                " ordinal, text, heading_path, :vector, 'voyage-3.5' FROM chunks WHERE id = :id"
            ),
            {"vector": str([1.0] + [0.0] * 1023), "id": chunk["id"]},
        )

    answer = await probed(owner, project_id, "Everyone gets 25 days.", top_k=10)

    assert [hit["chunk_id"] for hit in answer["chunks"]] == [chunk["id"]]


@pytest.mark.parametrize(
    "body", [{"query": ""}, {"query": "x", "top_k": 0}, {"query": "x", "top_k": 51}]
)
async def test_the_probe_needs_a_query_and_a_sensible_top_k(
    owner: SignedUpMember, body: dict[str, Any]
) -> None:
    project_id = await create_project(owner)

    response = await owner.client.post(
        f"{project_path(owner, project_id)}/retrieval-probe", json=body
    )

    assert response.status_code == 422


async def test_an_archived_project_cannot_be_probed(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    await owner.client.post(f"{project_path(owner, project_id)}/archive")

    response = await probe(owner, project_id, "leave")

    assert response.status_code == 409


async def test_an_unknown_project_cannot_be_probed(owner: SignedUpMember) -> None:
    response = await probe(owner, "00000000-0000-0000-0000-000000000000", "leave")

    assert response.status_code == 404


async def test_a_provider_failure_while_probing_is_a_bad_gateway(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await added(owner, provider="voyage", api_key=VOYAGE_KEY)
    project_id = await create_project(owner)
    await choose(owner, project_id, "voyage-3.5", voyage["id"])
    install_provider(app, FailingEmbeddingModel)

    response = await probe(owner, project_id, "leave")

    assert (response.status_code, response.json()) == (
        502,
        {"detail": "The Embedding Model's provider couldn't embed the query. Try again shortly."},
    )


# A Project whose Embedding Model became unusable outside the choice path (written directly:
# the choice refuses all three) is a setup problem the caller must fix, not a provider outage.


async def _set_embedding(app: FastAPI, project_id: str, model_id: str, credential_id: Any) -> None:
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(
            text(
                "UPDATE projects SET embedding_model_id = :model,"
                " embedding_credential_id = :credential WHERE id = :id"
            ),
            {"model": model_id, "credential": credential_id, "id": project_id},
        )


async def test_probing_through_a_credential_without_the_embeddings_capability_says_why(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await added(owner, provider="voyage", api_key=VOYAGE_KEY)
    project_id = await create_project(owner)
    await choose(owner, project_id, "voyage-3.5", voyage["id"])
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(
            text("UPDATE provider_credentials SET capabilities = '{rerank}' WHERE id = :id"),
            {"id": voyage["id"]},
        )

    response = await probe(owner, project_id, "leave")

    assert (response.status_code, response.json()) == (
        409,
        {
            "detail": "The Project's Embedding Model can't be used: "
            "This credential can't be used for embeddings."
        },
    )


async def test_probing_a_provider_model_without_its_credential_says_why(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    await _set_embedding(app, project_id, "voyage-3.5", None)

    response = await probe(owner, project_id, "leave")

    assert (response.status_code, response.json()) == (
        409,
        {
            "detail": "The Project's Embedding Model can't be used: "
            "voyage-3.5 has no Provider Credential. Choose the Embedding Model again."
        },
    )
