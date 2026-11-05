"""The retrieval probe: the top-k Chunks of a Project nearest a query, by vector alone.

It is for tests and diagnostics (re-embedding checks in ticket 03-10; spec 04 builds real
retrieval). It searches only the Chunks of the Project's current Embedding Model and of each
Document's current edition, ordering by cosine distance alone on the expression the model's
HNSW index is built on, so the index can serve the ordering (a tie-breaking second sort key would
force a sort of every candidate Chunk instead).

The index covers every Project's Chunks of the model, and the Project is a filter applied to
what it returns. A plain HNSW scan stops after ``hnsw.ef_search`` candidates, so a Project whose
Chunks sit behind other Projects' nearer ones would get fewer than ``top_k`` hits. pgvector's
iterative scan (``hnsw.iterative_scan = strict_order``, pgvector 0.8) keeps scanning until the
limit is met, in exact distance order.
"""

from dataclasses import dataclass

from sqlalchemy import Select, and_, select, text
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


def probe_statement(
    project: Project, model: EmbeddingModel, query_vector: list[float], top_k: int
) -> Select[Chunk, str, float]:
    """The probe's query: Chunks, their Document's name and their cosine distance."""
    distance = model_vector(model).cosine_distance(query_vector).label("distance")
    return (
        select(Chunk, Document.name, distance)
        .join(
            Document,
            and_(Document.id == Chunk.document_id, Document.edition == Chunk.edition),
        )
        .where(
            Chunk.project_id == project.id,
            Chunk.embedding_model_id == model.id,
        )
        .order_by(distance)
        .limit(top_k)
    )


async def probe(
    session: AsyncSession,
    project: Project,
    model: EmbeddingModel,
    query_vector: list[float],
    top_k: int,
) -> list[ProbeHit]:
    """The ``top_k`` Chunks of the Project's ``model`` nearest ``query_vector``, nearest first."""
    # Transaction-local: it only affects this query's transaction.
    await session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    rows = await session.execute(probe_statement(project, model, query_vector, top_k))
    return [ProbeHit(chunk, name, 1.0 - float(d)) for chunk, name, d in rows]
