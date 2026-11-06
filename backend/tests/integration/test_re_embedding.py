"""API seam: re-embedding a Project's Knowledge Base when its Embedding Model changes.

Tasks run eagerly, so a re-embed job runs inside the request that starts it, in a thread of its
own. To look at the API while the job runs, a test scripts the new model's provider (the model
gateway's fake adapters): a step can hold an embedding call until the test releases it, fail
it, or answer with vectors of the wrong size. Everything is observed through the API.
"""

import asyncio
import threading
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from pydantic_ai.embeddings import EmbeddingResult, EmbeddingSettings
from pydantic_ai.embeddings.result import EmbedInputType
from pydantic_ai.exceptions import ModelHTTPError
from sqlalchemy import text

from app.credentials.registry import Provider
from app.embeddings.fake import HashEmbedder
from app.gateway.fakes import FakeModelAdapters, HashEmbeddingModel
from tests.conftest import MemberFactory, SignedUpMember
from tests.documents import chunks, create_project, documents, project_path, upload
from tests.fakes.clock import ControllableClock
from tests.integration.test_document_editions import GatedConverter
from tests.integration.test_embedding_models import (
    LOCAL,
    choose,
    install_adapters,
    probed,
    project,
)
from tests.integration.test_provider_credentials import (
    OPENAI_KEY,
    VOYAGE_KEY,
    added,
    audit_events,
    credentials_path,
)

VOYAGE = "voyage-3.5"
OPENAI = "text-embedding-3-small"
LEAVE = "Everyone gets 25 days of annual leave."
EXPENSES = "Expenses are paid monthly."
OFFICES = "Offices open at nine."


class Script:
    """What the provider does on each passage-embedding call, in order: ``ok``, ``fail`` (an
    error answer), ``wrong`` (vectors of the wrong size), or ``hold`` before any of them (wait
    until the test releases it). Calls past the end are ``ok``. Queries aren't scripted."""

    def __init__(self, *steps: str) -> None:
        self.steps = list(steps)
        self.calls = 0
        self.held = threading.Event()
        self.released = threading.Event()

    def next(self) -> str:
        self.calls += 1
        return self.steps.pop(0) if self.steps else "ok"

    async def wait_until_held(self) -> None:
        assert await asyncio.to_thread(self.held.wait, 10)

    def release(self) -> None:
        self.released.set()


class ScriptedEmbeddingModel(HashEmbeddingModel):
    def __init__(self, model: str, script: Script) -> None:
        super().__init__(model)
        self._script = script

    async def embed(
        self,
        inputs: str | Sequence[str],
        *,
        input_type: EmbedInputType,
        settings: EmbeddingSettings | None = None,
    ) -> EmbeddingResult:
        if input_type == "document":
            step = self._script.next()
            if step.startswith("hold"):
                self._script.held.set()
                # The job runs in its own thread and event loop, so waiting blocks only it.
                assert self._script.released.wait(timeout=10)
                step = step.removeprefix("hold-") if "-" in step else "ok"
            if step == "fail":
                raise ModelHTTPError(503, self.model_name, {"error": "overloaded"})
            if step == "wrong":
                texts, _ = self.prepare_embed(inputs, settings)
                return EmbeddingResult(
                    [[1.0, 0.0] for _ in texts],
                    inputs=texts,
                    input_type=input_type,
                    model_name=self.model_name,
                    provider_name=self.system,
                )
        return await super().embed(inputs, input_type=input_type, settings=settings)


class ScriptedAdapters(FakeModelAdapters):
    def __init__(self, script: Script) -> None:
        super().__init__()
        self._script = script

    def embedder(self, provider: Provider, secret: str, model: str) -> HashEmbeddingModel:
        return ScriptedEmbeddingModel(model, self._script)


def scripted(app: FastAPI, *steps: str) -> Script:
    """Makes provider embedding calls (ingestion, the re-embed job, the probe) follow a script."""
    script = Script(*steps)
    install_adapters(app, ScriptedAdapters(script))
    return script


def state_path(member: SignedUpMember, project_id: str) -> str:
    return f"{project_path(member, project_id)}/embedding-model"


async def state(member: SignedUpMember, project_id: str) -> dict[str, Any]:
    response = await member.client.get(state_path(member, project_id))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def re_embed(member: SignedUpMember, project_id: str) -> dict[str, Any]:
    job: dict[str, Any] = (await state(member, project_id))["re_embed"]
    return job


def progress(job: dict[str, Any]) -> tuple[str, int, int]:
    return job["status"], job["embedded_chunks"], job["total_chunks"]


async def credential(
    owner: SignedUpMember, provider: str = "voyage", name: str | None = None
) -> str:
    key = VOYAGE_KEY if provider == "voyage" else OPENAI_KEY
    added_credential = await added(
        owner, provider=provider, api_key=key, name=name or provider.title()
    )
    credential_id: str = added_credential["id"]
    return credential_id


async def knowledge_base(
    app: FastAPI, member: SignedUpMember, *texts: str
) -> tuple[str, list[dict[str, Any]]]:
    """A Project with one single-Chunk Document per text, on the local model."""
    project_id = await create_project(member)
    uploaded = [
        await upload(app, member, project_id, f"{i}.md", body.encode())
        for i, body in enumerate(texts)
    ]
    return project_id, uploaded


async def probe_models(member: SignedUpMember, project_id: str, query: str) -> tuple[str, str]:
    """Which model the probe searched with, and the text of the Chunk it found first."""
    answer = await probed(member, project_id, query)
    return answer["embedding_model_id"], answer["chunks"][0]["text"]


# Re-embedding and switching over


async def test_changing_the_model_re_embeds_the_knowledge_base_and_switches_over(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    voyage = await credential(owner)
    editor = await member_factory(owner, "editor")
    project_id, (leave, _) = await knowledge_base(app, editor, LEAVE, EXPENSES)

    response = await choose(editor, project_id, VOYAGE, voyage)

    assert response.status_code == 200, response.text
    # Tests run the job eagerly, inside the request, so it has switched by now.
    assert (response.json()["embedding_model_id"], response.json()["embedding_credential_id"]) == (
        VOYAGE,
        voyage,
    )
    switched = await state(editor, project_id)
    assert {k: v for k, v in switched.items() if k != "re_embed"} == {
        "model_id": VOYAGE,
        "credential_id": voyage,
        "pending_model_id": None,
        "pending_credential_id": None,
    }
    job = switched["re_embed"]
    assert {k: job[k] for k in ("status", "from_model_id", "model_id", "credential_id")} == {
        "status": "completed",
        "from_model_id": LOCAL,
        "model_id": VOYAGE,
        "credential_id": voyage,
    }
    assert (job["embedded_chunks"], job["total_chunks"], job["error_message"]) == (2, 2, None)
    assert datetime.fromisoformat(job["finished_at"]) >= datetime.fromisoformat(job["started_at"])
    # The Chunks keep their place and text; their vectors are the new model's.
    (chunk,) = await chunks(editor, project_id, leave["id"])
    assert (chunk["embedding_model_id"], chunk["text"], chunk["ordinal"]) == (VOYAGE, LEAVE, 0)
    assert [d["chunk_count"] for d in await documents(editor, project_id)] == [1, 1]
    answer = await probed(editor, project_id, LEAVE)
    assert (answer["embedding_model_id"], answer["dimension"]) == (VOYAGE, 1024)
    assert answer["chunks"][0]["chunk_id"] == chunk["id"]
    assert answer["chunks"][0]["score"] == pytest.approx(1.0)
    assert len(answer["chunks"]) == 2  # the old vectors were deleted, not just hidden


async def test_the_old_vectors_serve_until_the_switch_and_progress_is_visible(
    app: FastAPI, owner: SignedUpMember, settings_env: pytest.MonkeyPatch
) -> None:
    settings_env.setenv("RE_EMBED_BATCH_SIZE", "1")
    voyage = await credential(owner)
    project_id, (leave, _, _) = await knowledge_base(app, owner, LEAVE, EXPENSES, OFFICES)
    script = scripted(app, "ok", "hold")

    choosing = asyncio.create_task(choose(owner, project_id, VOYAGE, voyage))
    await script.wait_until_held()  # one Chunk re-embedded, the second being embedded

    during = await state(owner, project_id)
    assert (during["model_id"], during["credential_id"]) == (LOCAL, None)
    assert (during["pending_model_id"], during["pending_credential_id"]) == (VOYAGE, voyage)
    assert progress(during["re_embed"]) == ("running", 1, 3)
    assert during["re_embed"]["finished_at"] is None
    assert (await project(owner, project_id))["embedding_model_id"] == LOCAL
    # Retrieval still uses the old model's vectors, and each Chunk shows once.
    assert await probe_models(owner, project_id, LEAVE) == (LOCAL, LEAVE)
    assert [d["chunk_count"] for d in await documents(owner, project_id)] == [1, 1, 1]
    assert chunk_models(await chunks(owner, project_id, leave["id"])) == [LOCAL]

    script.release()
    assert (await choosing).status_code == 200

    assert progress(await re_embed(owner, project_id)) == ("completed", 3, 3)
    assert await probe_models(owner, project_id, LEAVE) == (VOYAGE, LEAVE)
    assert chunk_models(await chunks(owner, project_id, leave["id"])) == [VOYAGE]


def chunk_models(listed: list[dict[str, Any]]) -> list[str]:
    return [c["embedding_model_id"] for c in listed]


async def test_a_project_without_documents_switches_at_once(owner: SignedUpMember) -> None:
    voyage = await credential(owner)
    project_id = await create_project(owner)

    assert (await choose(owner, project_id, VOYAGE, voyage)).status_code == 200

    now = await state(owner, project_id)
    assert (now["model_id"], now["pending_model_id"], now["re_embed"]) == (VOYAGE, None, None)


async def test_the_same_model_through_another_credential_switches_at_once(
    app: FastAPI, owner: SignedUpMember
) -> None:
    first = await credential(owner)
    second = await credential(owner, name="Voyage (team)")
    project_id = await create_project(owner)
    await choose(owner, project_id, VOYAGE, first)
    document = await upload(app, owner, project_id, "a.md", LEAVE.encode())
    (before,) = await chunks(owner, project_id, document["id"])

    response = await choose(owner, project_id, VOYAGE, second)

    assert response.json()["embedding_credential_id"] == second
    assert (await state(owner, project_id))["re_embed"] is None
    # The vectors are the same model's, so they are kept as they are.
    assert await chunks(owner, project_id, document["id"]) == [before]


async def test_a_re_embed_back_to_the_local_model_works_the_same_way(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await credential(owner)
    project_id = await create_project(owner)
    await choose(owner, project_id, VOYAGE, voyage)
    await upload(app, owner, project_id, "a.md", LEAVE.encode())

    assert (await choose(owner, project_id, LOCAL)).status_code == 200

    assert progress(await re_embed(owner, project_id)) == ("completed", 1, 1)
    assert await probe_models(owner, project_id, LEAVE) == (LOCAL, LEAVE)
    # The credential is no longer referenced.
    deleted = await owner.client.delete(credentials_path(owner.organisation_id, voyage))
    assert deleted.status_code == 204


async def test_headings_are_embedded_as_ingestion_embeds_them(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await credential(owner)
    project_id = await create_project(owner)
    await upload(app, owner, project_id, "a.md", b"# Handbook\n\n## Leave\n\n" + LEAVE.encode())

    await choose(owner, project_id, VOYAGE, voyage)

    # The fake provider gives a vector of exactly what it embedded, so a query of the headings
    # and the text, one per line, finds the Chunk with a score of 1.
    answer = await probed(owner, project_id, f"Handbook\nLeave\n{LEAVE}")
    assert answer["chunks"][0]["heading_path"] == ["Handbook", "Leave"]
    assert answer["chunks"][0]["score"] == pytest.approx(1.0)


# Failures leave the Project on its active model


async def test_a_provider_failure_partway_leaves_the_project_on_its_model(
    app: FastAPI, owner: SignedUpMember, settings_env: pytest.MonkeyPatch
) -> None:
    settings_env.setenv("RE_EMBED_BATCH_SIZE", "1")
    voyage = await credential(owner)
    project_id, (leave, _) = await knowledge_base(app, owner, LEAVE, EXPENSES)
    # The first Chunk is re-embedded; then the provider fails every automatic attempt.
    script = scripted(app, "ok", "fail", "fail", "fail", "fail")

    response = await choose(owner, project_id, VOYAGE, voyage)

    assert response.status_code == 200
    assert response.json()["embedding_model_id"] == LOCAL
    assert script.calls == 5
    failed = await state(owner, project_id)
    assert (failed["model_id"], failed["credential_id"], failed["pending_model_id"]) == (
        LOCAL,
        None,
        None,
    )
    assert progress(failed["re_embed"]) == ("failed", 1, 2)
    assert failed["re_embed"]["error_message"] == (
        "The Embedding Model's provider didn't respond after 4 attempts. "
        "The Project still uses multilingual-e5-small; choose the model again to retry."
    )
    assert failed["re_embed"]["finished_at"] is not None
    assert await probe_models(owner, project_id, LEAVE) == (LOCAL, LEAVE)
    # The new model's vectors written before the failure are gone.
    assert await model_rows(app, project_id) == {LOCAL: 2}
    assert chunk_models(await chunks(owner, project_id, leave["id"])) == [LOCAL]


async def model_rows(app: FastAPI, project_id: str) -> dict[str, int]:
    """How many Chunk rows the Project has per Embedding Model: read from the database, because
    the API only ever shows the active model's."""
    async with app.state.sessionmaker() as session:
        rows = await session.execute(
            text(
                "SELECT embedding_model_id, count(*) FROM chunks WHERE project_id = :id"
                " GROUP BY embedding_model_id"
            ),
            {"id": project_id},
        )
        return {model: count for model, count in rows}


async def test_a_provider_that_recovers_is_retried_and_the_job_completes(
    app: FastAPI, owner: SignedUpMember, settings_env: pytest.MonkeyPatch
) -> None:
    settings_env.setenv("RE_EMBED_BATCH_SIZE", "1")
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE, EXPENSES)
    script = scripted(app, "ok", "fail", "ok")

    await choose(owner, project_id, VOYAGE, voyage)

    # The retry kept the first Chunk's new vector: three calls in all, not four.
    assert script.calls == 3
    assert progress(await re_embed(owner, project_id)) == ("completed", 2, 2)
    assert (await state(owner, project_id))["model_id"] == VOYAGE


async def test_vectors_of_the_wrong_size_fail_the_job_with_the_reason(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    scripted(app, "wrong")

    await choose(owner, project_id, VOYAGE, voyage)

    job = await re_embed(owner, project_id)
    assert progress(job) == ("failed", 0, 1)
    assert job["error_message"] == (
        "The Embedding Model's provider can't be used: voyage-3.5 answered with 2 dimensions, "
        "not 1024. The Project still uses multilingual-e5-small; choose the model again once "
        "it is fixed."
    )
    assert (await state(owner, project_id))["model_id"] == LOCAL


async def test_a_credential_that_can_no_longer_embed_fails_the_job(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    # The choice checks the credential, so it loses its embeddings capability after the choice:
    # when the job opens its model gateway, just before it reads the job.
    loop = asyncio.get_running_loop()
    open_gateway = app.state.ingestion.open_gateway

    async def lose_capability() -> None:
        async with app.state.sessionmaker() as session, session.begin():
            await session.execute(
                text("UPDATE provider_credentials SET capabilities = '{rerank}' WHERE id = :id"),
                {"id": voyage},
            )

    def changing_gateway(client: Any) -> Any:
        asyncio.run_coroutine_threadsafe(lose_capability(), loop).result(10)
        return open_gateway(client)

    app.state.ingestion.open_gateway = changing_gateway

    await choose(owner, project_id, VOYAGE, voyage)

    job = await re_embed(owner, project_id)
    assert job["status"] == "failed"
    assert job["error_message"] == (
        "The Embedding Model's provider can't be used: This credential can't be used for "
        "embeddings. The Project still uses multilingual-e5-small; choose the model again once "
        "it is fixed."
    )
    assert (await state(owner, project_id))["model_id"] == LOCAL


async def test_an_unexpected_error_fails_the_job(app: FastAPI, owner: SignedUpMember) -> None:
    voyage = await credential(owner)
    project_id = await create_project(owner)
    await choose(owner, project_id, VOYAGE, voyage)
    await upload(app, owner, project_id, "a.md", LEAVE.encode())
    local = app.state.ingestion.embedders[LOCAL]
    assert isinstance(local, HashEmbedder)
    local.failures.append(RuntimeError("the model file is corrupt"))

    await choose(owner, project_id, LOCAL)

    job = await re_embed(owner, project_id)
    assert (job["status"], job["error_message"]) == (
        "failed",
        "Re-embedding stopped on an unexpected error. "
        "The Project still uses voyage-3.5; choose the model again to retry.",
    )
    assert (await state(owner, project_id))["model_id"] == VOYAGE
    assert await probe_models(owner, project_id, LEAVE) == (VOYAGE, LEAVE)


async def test_after_a_failure_choosing_the_model_again_retries(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    scripted(app, "wrong")
    await choose(owner, project_id, VOYAGE, voyage)
    assert (await re_embed(owner, project_id))["status"] == "failed"

    await choose(owner, project_id, VOYAGE, voyage)

    assert progress(await re_embed(owner, project_id)) == ("completed", 1, 1)
    assert (await state(owner, project_id))["model_id"] == VOYAGE


# Uploads during the job


async def test_documents_uploaded_during_the_job_are_embedded_with_both_models(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    script = scripted(app, "hold")
    choosing = asyncio.create_task(choose(owner, project_id, VOYAGE, voyage))
    await script.wait_until_held()
    assert progress(await re_embed(owner, project_id)) == ("running", 0, 1)

    uploaded = await upload(app, owner, project_id, "expenses.md", EXPENSES.encode())

    # The upload wrote its Chunk's vector for both models: the Knowledge Base grew by one, and
    # so did what the pending model already has.
    assert progress(await re_embed(owner, project_id)) == ("running", 1, 2)
    (listed,) = [d for d in await documents(owner, project_id) if d["id"] == uploaded["id"]]
    assert (listed["status"], listed["chunk_count"]) == ("ready", 1)
    # It serves with the active model right away.
    assert await probe_models(owner, project_id, EXPENSES) == (LOCAL, EXPENSES)
    script.release()
    await choosing
    assert progress(await re_embed(owner, project_id)) == ("completed", 2, 2)
    # Only the original Document's Chunk needed the job: the upload's was already there.
    assert script.calls == 2  # the job's one batch, and the upload's pending embedding
    assert await probe_models(owner, project_id, EXPENSES) == (VOYAGE, EXPENSES)


async def test_an_upload_whose_pending_vectors_fail_is_re_embedded_by_the_job(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    # The job's first call is held; the upload's pending embedding then fails.
    script = scripted(app, "hold", "fail")
    choosing = asyncio.create_task(choose(owner, project_id, VOYAGE, voyage))
    await script.wait_until_held()

    uploaded = await upload(app, owner, project_id, "expenses.md", EXPENSES.encode())

    (listed,) = [d for d in await documents(owner, project_id) if d["id"] == uploaded["id"]]
    assert listed["status"] == "ready"  # the active model's vectors are all it needs
    assert progress(await re_embed(owner, project_id)) == ("running", 0, 2)
    script.release()
    await choosing

    assert progress(await re_embed(owner, project_id)) == ("completed", 2, 2)
    assert await probe_models(owner, project_id, EXPENSES) == (VOYAGE, EXPENSES)


async def test_an_upload_processing_through_the_switch_is_processed_again(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    gate = GatedConverter()
    app.state.ingestion.converter = gate
    # The upload starts before the re-embed, so it embeds with the local model only.
    uploading = asyncio.create_task(
        upload(app, owner, project_id, "expenses.md", EXPENSES.encode())
    )
    await gate.wait_until_started()

    # The job finds only the first Document's Chunk, and switches.
    assert (await choose(owner, project_id, VOYAGE, voyage)).status_code == 200
    assert (await state(owner, project_id))["model_id"] == VOYAGE
    gate.release.set()
    uploaded = await uploading

    # Its local vectors are of no use any more, so it was processed again with the new model.
    (listed,) = [d for d in await documents(owner, project_id) if d["id"] == uploaded["id"]]
    assert (listed["status"], listed["chunk_count"], listed["attempt_count"]) == ("ready", 1, 2)
    assert listed["error_message"] is None
    assert await probe_models(owner, project_id, EXPENSES) == (VOYAGE, EXPENSES)
    assert await model_rows(app, project_id) == {VOYAGE: 2}


async def test_a_document_deleted_during_the_job_is_skipped(
    app: FastAPI, owner: SignedUpMember, settings_env: pytest.MonkeyPatch
) -> None:
    settings_env.setenv("RE_EMBED_BATCH_SIZE", "2")
    voyage = await credential(owner)
    project_id, (leave, expenses) = await knowledge_base(app, owner, LEAVE, EXPENSES)
    script = scripted(app, "hold")
    choosing = asyncio.create_task(choose(owner, project_id, VOYAGE, voyage))
    await script.wait_until_held()  # both Chunks are being embedded

    deleted = await owner.client.delete(
        f"{project_path(owner, project_id)}/documents/{expenses['id']}"
    )
    assert deleted.status_code == 204
    script.release()
    await choosing

    assert progress(await re_embed(owner, project_id)) == ("completed", 1, 1)
    assert [d["id"] for d in await documents(owner, project_id)] == [leave["id"]]
    assert await model_rows(app, project_id) == {VOYAGE: 1}


# Choosing again while a re-embed runs


async def test_choosing_the_active_model_again_cancels_the_re_embed(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    script = scripted(app, "hold")
    choosing = asyncio.create_task(choose(owner, project_id, VOYAGE, voyage))
    await script.wait_until_held()

    cancelled = await choose(owner, project_id, LOCAL)

    assert cancelled.status_code == 200
    now = await state(owner, project_id)
    assert (now["model_id"], now["pending_model_id"]) == (LOCAL, None)
    assert progress(now["re_embed"]) == ("cancelled", 0, 1)
    script.release()
    await choosing
    # The job stopped without writing what it had embedded.
    assert (await re_embed(owner, project_id))["status"] == "cancelled"
    assert await model_rows(app, project_id) == {LOCAL: 1}
    assert await probe_models(owner, project_id, LEAVE) == (LOCAL, LEAVE)


async def test_choosing_the_pending_model_again_changes_nothing(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    script = scripted(app, "hold")
    choosing = asyncio.create_task(choose(owner, project_id, VOYAGE, voyage))
    await script.wait_until_held()
    job_id = (await re_embed(owner, project_id))["id"]

    again = await choose(owner, project_id, VOYAGE, voyage)

    assert again.status_code == 200
    assert (await re_embed(owner, project_id))["id"] == job_id
    script.release()
    await choosing
    assert progress(await re_embed(owner, project_id)) == ("completed", 1, 1)


async def test_choosing_a_third_model_replaces_the_running_re_embed(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await credential(owner)
    openai = await credential(owner, "openai")
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    script = scripted(app, "hold")
    choosing = asyncio.create_task(choose(owner, project_id, VOYAGE, voyage))
    await script.wait_until_held()
    first = (await re_embed(owner, project_id))["id"]
    script.release()  # the replacing job's calls must not wait

    replaced = await choose(owner, project_id, OPENAI, openai)
    await choosing

    assert replaced.status_code == 200
    job = await re_embed(owner, project_id)
    assert (job["id"] != first, job["model_id"], job["status"]) == (True, OPENAI, "completed")
    assert (await state(owner, project_id))["model_id"] == OPENAI
    assert await model_rows(app, project_id) == {OPENAI: 1}


async def test_a_job_cancelled_before_its_retry_stops(app: FastAPI, owner: SignedUpMember) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    script = scripted(app, "hold-fail")
    choosing = asyncio.create_task(choose(owner, project_id, VOYAGE, voyage))
    await script.wait_until_held()

    await choose(owner, project_id, LOCAL)
    script.release()
    await choosing

    # The failed call would have been retried, but the retry found the job cancelled.
    assert script.calls == 1
    assert (await re_embed(owner, project_id))["status"] == "cancelled"


async def test_a_job_cancelled_before_it_fails_stays_cancelled(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    script = scripted(app, "hold-wrong")
    choosing = asyncio.create_task(choose(owner, project_id, VOYAGE, voyage))
    await script.wait_until_held()

    await choose(owner, project_id, LOCAL)
    script.release()
    await choosing

    job = await re_embed(owner, project_id)
    assert (job["status"], job["error_message"]) == ("cancelled", None)
    assert await audit_events(owner, "project.re_embed_failed") == []


# The pending credential is a reference


async def test_the_pending_models_credential_cannot_be_deleted(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    script = scripted(app, "hold")
    choosing = asyncio.create_task(choose(owner, project_id, VOYAGE, voyage))
    await script.wait_until_held()

    response = await owner.client.delete(credentials_path(owner.organisation_id, voyage))

    assert response.status_code == 409
    assert response.json()["references"] == [
        {"kind": "project", "id": project_id, "name": "Handbook (re-embedding to voyage-3.5)"}
    ]
    script.release()
    await choosing


async def test_a_finished_jobs_credential_can_be_deleted(
    app: FastAPI, owner: SignedUpMember
) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    scripted(app, "wrong")
    await choose(owner, project_id, VOYAGE, voyage)

    response = await owner.client.delete(credentials_path(owner.organisation_id, voyage))

    assert response.status_code == 204
    job = await re_embed(owner, project_id)
    assert (job["status"], job["credential_id"]) == ("failed", None)


# Audit Events


async def test_model_changes_are_audit_events(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    voyage = await credential(owner)
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    script = scripted(app, "hold")
    choosing = asyncio.create_task(choose(owner, project_id, VOYAGE, voyage))
    await script.wait_until_held()
    await choose(owner, project_id, LOCAL)  # cancelled
    script.release()
    await choosing
    scripted(app, "wrong")
    await choose(owner, project_id, VOYAGE, voyage)  # failed
    await choose(owner, project_id, VOYAGE, voyage)  # completed

    local = {"model_id": LOCAL, "credential_id": None}
    pending = {**local, "pending_model_id": VOYAGE, "pending_credential_id": voyage}
    idle = {**local, "pending_model_id": None, "pending_credential_id": None}
    started = await audit_events(owner, "project.re_embed_started")
    assert [(e["before"], e["after"]) for e in started] == [(idle, pending)] * 3
    (cancelled,) = await audit_events(owner, "project.re_embed_cancelled")
    assert (cancelled["before"], cancelled["after"]) == (pending, idle)
    for event in [*started, cancelled]:
        assert event["actor"]["id"] == owner.member_id
        assert event["target"] == {"type": "project", "id": project_id}
        assert datetime.fromisoformat(event["occurred_at"]) == clock.now()
    (failed,) = await audit_events(owner, "project.re_embed_failed")
    assert failed["after"]["model_id"] == VOYAGE
    assert failed["after"]["error_message"].startswith("The Embedding Model's provider can't be")
    (switched,) = await audit_events(owner, "project.embedding_model_changed")
    assert (switched["before"], switched["after"]) == (
        local,
        {"model_id": VOYAGE, "credential_id": voyage},
    )
    # The background job records what it did itself, with no Member as the actor.
    assert failed["actor"] is None
    assert switched["actor"] is None
    assert switched["target"] == {"type": "project", "id": project_id}


# Reading the state


async def test_any_member_reads_the_state_even_of_an_archived_project(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    project_id, _ = await knowledge_base(app, owner, LEAVE)
    await owner.client.post(f"{project_path(owner, project_id)}/archive")
    editor = await member_factory(owner, "editor")

    assert await state(editor, project_id) == {
        "model_id": LOCAL,
        "credential_id": None,
        "pending_model_id": None,
        "pending_credential_id": None,
        "re_embed": None,
    }


async def test_an_unknown_projects_state_is_not_found(owner: SignedUpMember) -> None:
    response = await owner.client.get(state_path(owner, "00000000-0000-0000-0000-000000000000"))

    assert (response.status_code, response.json()) == (404, {"detail": "Not found"})
