"""Embedding Model routes: the models an Organisation can choose from, choosing a Project's,
and the retrieval probe. Any Member (Owner or Editor) may use them."""

import logging
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, StringConstraints

from app.auth.api import Db, ErrorResponse
from app.documents.ports import IngestionPorts
from app.embeddings.provider import UNUSABLE_ERRORS, resolve_embedder
from app.embeddings.registry import embedding_model
from app.gateway.gateway import ModelGateway
from app.projects import embedding, service
from app.projects.api import PROJECT_ARCHIVED, ClockDep, ProjectOut, respond
from app.re_embedding import service as re_embedding
from app.re_embedding.models import ReEmbedJob, ReEmbedStatus
from app.re_embedding.tasks import enqueue_re_embed
from app.retrieval.probe import probe
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, Scope

logger = logging.getLogger(__name__)

router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["embedding-models"])

PROVIDER_FAILED = "The Embedding Model's provider couldn't embed the query. Try again shortly."
MODEL_UNUSABLE = "The Project's Embedding Model can't be used: {reason}"
# Setup problems (``UNUSABLE_ERRORS``) are a 409 with the reason rather than the 502 kept for
# provider failures that may pass.
PROBE_TOP_K_MAX = 50


def _errors(*codes: tuple[int, str]) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ErrorResponse, "description": text} for code, text in codes}


class EmbeddingModelChoiceOut(BaseModel):
    """An Embedding Model the Organisation can choose, and the credential it is called
    through (none for the built-in local model)."""

    model_id: str
    name: str
    provider: str
    dimension: int
    tokenizer: str
    # The most tokens the model reads at once.
    token_limit: int
    credential_id: uuid.UUID | None
    credential_name: str | None


class SetEmbeddingModelRequest(BaseModel):
    model_id: str
    # Required for a provider model; must be empty for the local model.
    credential_id: uuid.UUID | None = None


class ReEmbedOut(BaseModel):
    """A re-embed job: the Knowledge Base moving from one Embedding Model to another."""

    id: uuid.UUID
    status: ReEmbedStatus
    # The model the Project used when the job started, and the one it re-embeds to.
    from_model_id: str
    model_id: str
    credential_id: uuid.UUID | None
    # The Chunks with the new model's vector so far, of all the Knowledge Base's Chunks.
    embedded_chunks: int
    total_chunks: int
    # Why a failed job failed.
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None


class EmbeddingModelStateOut(BaseModel):
    """The Project's active Embedding Model, the pending one while a re-embed runs, and the
    latest re-embed job (running or ended), if there has been one."""

    model_id: str
    credential_id: uuid.UUID | None
    pending_model_id: str | None
    pending_credential_id: uuid.UUID | None
    re_embed: ReEmbedOut | None


class ProbeRequest(BaseModel):
    query: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    top_k: Annotated[int, Field(ge=1, le=PROBE_TOP_K_MAX)] = 5


class ProbeChunkOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    ordinal: int
    text: str
    heading_path: list[str]
    page_start: int | None
    page_end: int | None
    # Cosine similarity to the query: 1 is the same direction.
    score: float


class ProbeOut(BaseModel):
    embedding_model_id: str
    dimension: int
    # Nearest first.
    chunks: list[ProbeChunkOut]


@router.get("/embedding-models", operation_id="listEmbeddingModels", responses=_errors())
async def list_embedding_models(scope: Scope, db: Db) -> list[EmbeddingModelChoiceOut]:
    """The built-in local model, then the Embedding Models each embedding-capable Provider
    Credential offers, by credential name."""
    return [
        EmbeddingModelChoiceOut(
            model_id=choice.model.id,
            name=choice.model.name,
            provider=choice.model.provider,
            dimension=choice.model.dimension,
            tokenizer=choice.model.tokenizer,
            token_limit=choice.model.max_tokens,
            credential_id=None if choice.credential is None else choice.credential.id,
            credential_name=None if choice.credential is None else choice.credential.name,
        )
        for choice in await embedding.embedding_choices(db, scope)
    ]


@router.put(
    "/projects/{project_id}/embedding-model",
    operation_id="setProjectEmbeddingModel",
    responses=_errors(
        (404, NOT_FOUND),
        (409, PROJECT_ARCHIVED),
        (422, "The model or credential can't be used; the detail says why."),
    ),
)
async def set_project_embedding_model(
    project_id: uuid.UUID, body: SetEmbeddingModelRequest, scope: Scope, db: Db, clock: ClockDep
) -> ProjectOut:
    """Chooses the Project's Embedding Model: the local one, or a provider model with a
    Provider Credential that offers it. A Project without Documents switches at once
    (``project.embedding_model_changed``). One with Documents gets it as its pending model and
    a background re-embed (``project.re_embed_started``); its active model keeps serving until
    the job switches over. Choosing again while a re-embed runs cancels it
    (``project.re_embed_cancelled``). Follow the re-embed with ``getProjectEmbeddingModel``."""
    try:
        change = await embedding.set_embedding_model(
            db,
            scope,
            project_id,
            model_id=body.model_id,
            credential_id=body.credential_id,
            now=clock.now(),
        )
    except service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except service.ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    except embedding.EmbeddingChoiceError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    if change.started is not None:
        await enqueue_re_embed(change.started.id)
        # The job may have finished already (tasks run eagerly in tests).
        await db.refresh(change.project)
    return await respond(db, change.project)


async def _re_embed_out(db: Db, job: ReEmbedJob) -> ReEmbedOut:
    progress = await re_embedding.progress(db, job)
    return ReEmbedOut(
        id=job.id,
        status=ReEmbedStatus(job.status),
        from_model_id=job.from_model_id,
        model_id=job.model_id,
        credential_id=job.credential_id,
        embedded_chunks=progress.embedded,
        total_chunks=progress.total,
        error_message=job.error_message,
        started_at=job.created_at,
        finished_at=job.finished_at,
    )


@router.get(
    "/projects/{project_id}/embedding-model",
    operation_id="getProjectEmbeddingModel",
    responses=_errors((404, NOT_FOUND)),
)
async def get_project_embedding_model(
    project_id: uuid.UUID, scope: Scope, db: Db
) -> EmbeddingModelStateOut:
    """The Project's Embedding Model, archived or not: the active one, the pending one while a
    re-embed runs, and the latest re-embed with its progress (or why it failed)."""
    try:
        project = await service.get_project(db, scope, project_id)
    except service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    latest = await re_embedding.latest_job(db, project.id)
    running = latest is not None and latest.status == ReEmbedStatus.RUNNING
    return EmbeddingModelStateOut(
        model_id=project.embedding_model_id,
        credential_id=project.embedding_credential_id,
        pending_model_id=latest.model_id if latest is not None and running else None,
        pending_credential_id=latest.credential_id if latest is not None and running else None,
        re_embed=None if latest is None else await _re_embed_out(db, latest),
    )


@router.post(
    "/projects/{project_id}/retrieval-probe",
    operation_id="probeRetrieval",
    responses=_errors(
        (404, NOT_FOUND),
        (409, f"{PROJECT_ARCHIVED} Or: {MODEL_UNUSABLE.format(reason='<why>')}"),
        (502, PROVIDER_FAILED),
    ),
)
async def probe_retrieval(
    project_id: uuid.UUID, body: ProbeRequest, scope: Scope, db: Db, request: Request
) -> ProbeOut:
    """The ``top_k`` Chunks nearest the query by vector, for tests and diagnostics. Searches
    the Chunks of the Project's current Embedding Model only."""
    try:
        project = await service.active_project(db, scope, project_id)
    except service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except service.ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    ports: IngestionPorts = request.app.state.ingestion
    gateway: ModelGateway = request.app.state.model_gateway
    model = embedding_model(project.embedding_model_id)
    credential = await embedding.project_credential(db, project)
    try:
        embedder = resolve_embedder(model, credential, ports.embedders, gateway)
    except UNUSABLE_ERRORS as error:
        detail = MODEL_UNUSABLE.format(reason=error)
        raise HTTPException(status.HTTP_409_CONFLICT, detail) from None
    try:
        vector = await embedder.embed_query(body.query)
    except Exception:
        logger.exception(
            "Embedding the probe's query failed", extra={"project_id": str(project_id)}
        )
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, PROVIDER_FAILED) from None
    hits = await probe(db, project, model, vector, body.top_k)
    return ProbeOut(
        embedding_model_id=model.id,
        dimension=model.dimension,
        chunks=[
            ProbeChunkOut(
                chunk_id=hit.chunk.id,
                document_id=hit.chunk.document_id,
                document_name=hit.document_name,
                ordinal=hit.chunk.ordinal,
                text=hit.chunk.text,
                heading_path=hit.chunk.heading_path,
                page_start=hit.chunk.page_start,
                page_end=hit.chunk.page_end,
                score=hit.score,
            )
            for hit in hits
        ],
    )
