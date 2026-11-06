"""The retrieval module: ``retrieve(project, query, settings)`` gives ranked candidates, plus the
Chunks it found but left out, each with its reason.

Hybrid search (ADR-0001):

1. Semantic search: pgvector cosine search with the query embedded by the Project's active
   Embedding Model. A Chunk's semantic score is its cosine similarity.
2. Keyword search: Postgres full-text search for any of the query's terms (the ``simple``
   configuration, as the Chunks are indexed). A Chunk's keyword score is the share of the
   query's distinct terms it contains; Chunks sharing more terms rank first.
   Both searches are limited to the Project, its active Embedding Model and the current edition
   of its Ready Documents, and return at most ``CANDIDATE_POOL`` Chunks each. A search whose
   weight is 0 isn't run.
3. Weighted reciprocal rank fusion: a Chunk's fused score is the sum over the searches that
   found it of ``weight / (RRF_K + rank)``, with the hybrid weighting giving semantic search's
   weight and keyword search the rest. It is scaled by ``RRF_K + 1`` so that 1 means first in
   every search; candidates are ranked by it.
4. The optional reranker (built by the model gateway from the Agent's rerank-capable
   credential) scores every Chunk found against the query. Candidates are then ranked by that
   score, and it becomes each Chunk's relevance: a rerank model's judgement replaces the
   cosine and keyword scores. Nothing found means nothing to rerank, so it isn't asked.
5. The minimum score: a Chunk's relevance is its rerank score, or else its best semantic or
   keyword score (at least 0). Chunks below the minimum are excluded (``below_min_score``),
   then the best ``top_k`` are the candidates and the rest are excluded (``outside_top_k``).

The fused score depends only on ranks, so it says nothing about whether anything relevant was
found; the relevance does, which is why the minimum applies to it. Tag scoping (ticket 04-04)
grows inside this one operation.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ColumnElement,
    Float,
    Select,
    case,
    cast,
    func,
    literal,
    literal_column,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.config import Retrieval
from app.documents.models import Chunk, Document, DocumentStatus
from app.embeddings.port import Embedder
from app.embeddings.registry import EMBEDDING_MODELS
from app.gateway.ports import Reranker
from app.projects.models import Project

# How many Chunks each search contributes to the fusion.
CANDIDATE_POOL = 50
# The reciprocal rank fusion constant; 60 is the value from the original RRF paper.
RRF_K = 60
# At most this many distinct query terms are searched for (a question is at most 4000 chars).
MAX_QUERY_TERMS = 64

# Chunks are indexed with the 'simple' text search configuration, so queries are parsed with it.
_SIMPLE: ColumnElement[str] = literal_column("'simple'::regconfig")

ExcludedReason = Literal["below_min_score", "outside_top_k"]


@dataclass(frozen=True)
class Candidate:
    """A retrieved Chunk with its rank from 1 and its scores, each from 0 to 1 (a cosine
    similarity can dip below 0). ``semantic_score`` or ``keyword_score`` is ``None`` when that
    search didn't find the Chunk."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    text: str
    heading_path: list[str]
    # The weighted reciprocal rank fusion score candidates are ranked by without a reranker.
    score: float
    # What the minimum score is compared with: the rerank score when there is one.
    relevance: float
    semantic_score: float | None
    keyword_score: float | None
    rank: int
    # The reranker's score, which ranks candidates when the Agent has a reranker.
    rerank_score: float | None = None


@dataclass(frozen=True)
class Excluded:
    """A Chunk that was found but left out, and why."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    text: str
    score: float
    relevance: float
    reason: ExcludedReason
    rerank_score: float | None = None


@dataclass(frozen=True)
class RetrievalResult:
    candidates: list[Candidate]
    excluded: list[Excluded] = field(default_factory=list)


class EmbeddingModelUnavailableError(Exception):
    """No embedder is installed for the Project's Embedding Model."""


@dataclass
class _Found:
    chunk: Chunk
    document_name: str
    fused: float = 0.0
    semantic_score: float | None = None
    keyword_score: float | None = None
    rerank_score: float | None = None

    @property
    def relevance(self) -> float:
        if self.rerank_score is not None:
            return self.rerank_score
        return max(self.semantic_score or 0.0, self.keyword_score or 0.0, 0.0)


def _searchable(project: Project) -> Select[Chunk, str]:
    """The Project's Chunks of its active Embedding Model, in each Ready Document's current
    edition, with their Document's name."""
    return (
        select(Chunk, Document.name)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.project_id == project.id,
            Chunk.embedding_model_id == project.embedding_model_id,
            Chunk.edition == Document.edition,
            Document.project_id == project.id,
            Document.status == DocumentStatus.READY,
        )
    )


async def _semantic(
    session: AsyncSession, project: Project, query: str, embedder: Embedder
) -> list[tuple[Chunk, str, float]]:
    dimension = EMBEDDING_MODELS[project.embedding_model_id].dimension
    vector = await embedder.embed_query(query)
    # Cast to the model's dimension so the query can use that model's HNSW index.
    distance = cast(Chunk.embedding, Vector(dimension)).cosine_distance(vector)
    rows = await session.execute(
        _searchable(project)
        .add_columns(distance.label("distance"))
        .order_by(distance, Chunk.id)
        .limit(CANDIDATE_POOL)
    )
    return [(chunk, name, 1.0 - float(d)) for chunk, name, d in rows]


async def _query_terms(session: AsyncSession, query: str) -> list[str]:
    """The query's distinct terms, as Postgres indexes Chunk text (the ``simple`` config)."""
    terms = await session.scalars(
        select(func.unnest(func.tsvector_to_array(func.to_tsvector(_SIMPLE, query)))).limit(
            MAX_QUERY_TERMS
        )
    )
    return list(terms)


def _matches(term: str) -> ColumnElement[bool]:
    return Chunk.search_vector.bool_op("@@")(func.plainto_tsquery(_SIMPLE, term))


async def _keyword(
    session: AsyncSession, project: Project, terms: Sequence[str]
) -> list[tuple[Chunk, str, float]]:
    matched: ColumnElement[float] = sum(
        (cast(case((_matches(term), 1), else_=0), Float) for term in terms),
        start=cast(literal(0), Float),
    )
    share = (matched / len(terms)).label("share")
    rows = await session.execute(
        _searchable(project)
        .add_columns(share)
        .where(Chunk.search_vector.bool_op("@@")(_any_of(terms)))
        .order_by(
            share.desc(),
            func.ts_rank_cd(Chunk.search_vector, _any_of(terms)).desc(),
            Chunk.id,
        )
        .limit(CANDIDATE_POOL)
    )
    return [(chunk, name, float(s)) for chunk, name, s in rows]


def _any_of(terms: Sequence[str]) -> ColumnElement[str]:
    query: ColumnElement[str] = func.plainto_tsquery(_SIMPLE, terms[0])
    for term in terms[1:]:
        query = query.op("||")(func.plainto_tsquery(_SIMPLE, term))
    return query


async def _rerank(reranker: Reranker, query: str, ranked: list[_Found]) -> list[_Found]:
    """``ranked`` in the reranker's order, each with its rerank score. The reranker is given the
    Chunks in fused order, so it can break its ties by that order; asked without a ``top_k``,
    it returns every one of them (the ``Reranker`` port's contract)."""
    reranked = await reranker.rerank(query, [entry.chunk.text for entry in ranked])
    result: list[_Found] = []
    for document in reranked:
        entry = ranked[document.index]
        entry.rerank_score = document.score
        result.append(entry)
    return result


async def retrieve(
    session: AsyncSession,
    project: Project,
    query: str,
    settings: Retrieval,
    embedders: dict[str, Embedder],
    *,
    reranker: Reranker | None = None,
) -> RetrievalResult:
    """The Project's Chunks most relevant to ``query``, best first, at most ``top_k``, and the
    Chunks found but left out. With a ``reranker``, every Chunk found is reranked before the
    minimum score and ``top_k`` are applied."""
    embedder = embedders.get(project.embedding_model_id)
    if embedder is None:
        raise EmbeddingModelUnavailableError(project.embedding_model_id)
    found: dict[uuid.UUID, _Found] = {}

    def fuse(rows: list[tuple[Chunk, str, float]], weight: float, semantic: bool) -> None:
        for rank, (chunk, name, score) in enumerate(rows, start=1):
            entry = found.setdefault(chunk.id, _Found(chunk, name))
            entry.fused += weight * (RRF_K + 1) / (RRF_K + rank)
            if semantic:
                entry.semantic_score = score
            else:
                entry.keyword_score = score

    semantic_weight = settings.hybrid_weight
    keyword_weight = 1.0 - semantic_weight
    if semantic_weight > 0:
        fuse(await _semantic(session, project, query, embedder), semantic_weight, semantic=True)
    if keyword_weight > 0:
        terms = await _query_terms(session, query)
        if terms:
            fuse(await _keyword(session, project, terms), keyword_weight, semantic=False)

    ranked = sorted(found.values(), key=lambda f: (-f.fused, -f.relevance, f.chunk.id))
    if reranker is not None and ranked:
        ranked = await _rerank(reranker, query, ranked)
    candidates: list[Candidate] = []
    excluded: list[Excluded] = []
    for entry in ranked:
        reason: ExcludedReason | None = None
        if entry.relevance < settings.min_score:
            reason = "below_min_score"
        elif len(candidates) >= settings.top_k:
            reason = "outside_top_k"
        if reason is not None:
            excluded.append(
                Excluded(
                    chunk_id=entry.chunk.id,
                    document_id=entry.chunk.document_id,
                    document_name=entry.document_name,
                    text=entry.chunk.text,
                    score=entry.fused,
                    relevance=entry.relevance,
                    reason=reason,
                    rerank_score=entry.rerank_score,
                )
            )
            continue
        candidates.append(
            Candidate(
                chunk_id=entry.chunk.id,
                document_id=entry.chunk.document_id,
                document_name=entry.document_name,
                text=entry.chunk.text,
                heading_path=list(entry.chunk.heading_path),
                score=entry.fused,
                relevance=entry.relevance,
                semantic_score=entry.semantic_score,
                keyword_score=entry.keyword_score,
                rank=len(candidates) + 1,
                rerank_score=entry.rerank_score,
            )
        )
    return RetrievalResult(candidates=candidates, excluded=excluded)
