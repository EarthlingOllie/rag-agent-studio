"""The retrieval probe: the top-k Chunks of a Project nearest a query, by vector alone.

It is for tests and diagnostics (re-embedding checks in ticket 03-10; spec 04 builds real
retrieval). It searches only the Chunks of the Project's current Embedding Model and of each
Document's current edition, ordering by cosine distance on the expression the model's HNSW
index is built on, so the index can serve it.
"""

from dataclasses import dataclass

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Chunk, Document, model_vector
from app.embeddings.registry import EmbeddingModel
from app.projects.models import Project


@dataclass(frozen=True)
class ProbeHit:
    chunk: Chunk
    document_name: str
    # Cosine similarity: 1 for the same direction, 0 for unrelated, -1 for opposite.
    score: float


async def probe(
    session: AsyncSession,
    project: Project,
    model: EmbeddingModel,
    query_vector: list[float],
    top_k: int,
) -> list[ProbeHit]:
    """The ``top_k`` Chunks of the Project's ``model`` nearest ``query_vector``, nearest first."""
    distance = model_vector(model).cosine_distance(query_vector).label("distance")
    rows = await session.execute(
        select(Chunk, Document.name, distance)
        .join(
            Document,
            and_(Document.id == Chunk.document_id, Document.edition == Chunk.edition),
        )
        .where(
            Chunk.project_id == project.id,
            Chunk.embedding_model_id == model.id,
        )
        .order_by(distance, Chunk.id)
        .limit(top_k)
    )
    return [ProbeHit(chunk, name, 1.0 - float(d)) for chunk, name, d in rows]
