"""The retrieval module: ``retrieve(project, query, settings)`` gives ranked candidates.

This first slice runs pgvector cosine search, limited to the Project, its active Embedding
Model and each Document's current edition of Ready Documents. Hybrid search with full-text
fusion, the minimum score, Tag scoping and the reranker (spec 04, tickets 04-03 to 04-05) grow
inside this one operation, and fill ``RetrievalResult.excluded`` with their reasons.
"""

import uuid
from dataclasses import dataclass, field

from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.config import Retrieval
from app.documents.models import Chunk, Document, DocumentStatus
from app.embeddings.port import Embedder
from app.embeddings.registry import EMBEDDING_MODELS
from app.projects.models import Project


@dataclass(frozen=True)
class Candidate:
    """A retrieved Chunk: its rank from 1 and its relevance score (cosine similarity)."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    text: str
    heading_path: list[str]
    score: float
    rank: int


@dataclass(frozen=True)
class Excluded:
    """A Chunk that was found but left out, and why."""

    chunk_id: uuid.UUID
    score: float
    reason: str


@dataclass(frozen=True)
class RetrievalResult:
    candidates: list[Candidate]
    excluded: list[Excluded] = field(default_factory=list)


class EmbeddingModelUnavailableError(Exception):
    """No embedder is installed for the Project's Embedding Model."""


async def retrieve(
    session: AsyncSession,
    project: Project,
    query: str,
    settings: Retrieval,
    embedders: dict[str, Embedder],
) -> RetrievalResult:
    """The Project's Chunks most similar to ``query``, best first, at most ``top_k``."""
    model_id = project.embedding_model_id
    embedder = embedders.get(model_id)
    if embedder is None:
        raise EmbeddingModelUnavailableError(model_id)
    dimension = EMBEDDING_MODELS[model_id].dimension
    vector = embedder.embed_query(query)
    # Cast to the model's dimension so the query can use that model's HNSW index.
    distance = cast(Chunk.embedding, Vector(dimension)).cosine_distance(vector)
    rows = await session.execute(
        select(Chunk, Document.name, distance.label("distance"))
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.project_id == project.id,
            Chunk.embedding_model_id == model_id,
            Chunk.edition == Document.edition,
            Document.project_id == project.id,
            Document.status == DocumentStatus.READY,
        )
        .order_by(distance, Chunk.id)
        .limit(settings.top_k)
    )
    return RetrievalResult(
        candidates=[
            Candidate(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_name=name,
                text=chunk.text,
                heading_path=list(chunk.heading_path),
                score=1.0 - float(chunk_distance),
                rank=rank,
            )
            for rank, (chunk, name, chunk_distance) in enumerate(rows, start=1)
        ]
    )
