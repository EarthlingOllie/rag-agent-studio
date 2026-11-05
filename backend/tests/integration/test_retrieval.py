"""The retrieval module through its interface, against real Postgres with pgvector.

The fixture Knowledge Base (``tests/knowledge_base.py``) is uploaded through the API and
ingested eagerly with the fake converter and the deterministic embedder, so which Chunks each
search finds is known: semantic search finds a Chunk by its exact text, keyword search by
shared words."""

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import update

from app.agents.config import Retrieval
from app.documents.models import Chunk
from app.projects.models import Project
from app.retrieval.service import EmbeddingModelUnavailableError, RetrievalResult, retrieve
from tests.conftest import SignedUpMember, TenantFactory
from tests.documents import create_project, upload
from tests.knowledge_base import (
    EXPENSES,
    FILES,
    LEAVE,
    PARKING,
    PRODUCT,
    PRODUCT_QUESTION,
    RULES,
    RULES_REPEATED,
    UNRELATED_QUESTION,
    knowledge_base,
)


async def search(app: FastAPI, project_id: str, query: str, **settings: Any) -> RetrievalResult:
    async with app.state.sessionmaker() as session:
        project = await session.get_one(Project, uuid.UUID(project_id))
        return await retrieve(
            session, project, query, Retrieval(**settings), app.state.ingestion.embedders
        )


def texts(result: RetrievalResult) -> list[str]:
    return [candidate.text for candidate in result.candidates]


async def test_the_relevant_chunk_ranks_first_with_its_scores(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await knowledge_base(app, owner)

    result = await search(app, project_id, EXPENSES, top_k=20)

    best, *rest = result.candidates
    assert best.text == EXPENSES
    assert best.document_name == "expenses.txt"
    assert best.heading_path == []
    # First in both searches: the highest fused score there is.
    assert best.score == pytest.approx(1.0)
    assert best.semantic_score == pytest.approx(1.0)
    assert best.keyword_score == pytest.approx(1.0)
    assert best.relevance == pytest.approx(1.0)
    assert [c.rank for c in result.candidates] == list(range(1, len(FILES) + 1))
    scores = [c.score for c in result.candidates]
    assert scores == sorted(scores, reverse=True)
    assert all(0 < c.score < 1 for c in rest)
    # LEAVE shares "days" and "of" with the query (2 of its 7 terms); the rest share nothing.
    leave = next(c for c in rest if c.text == LEAVE)
    assert leave.keyword_score == pytest.approx(2 / 7)
    assert [c.keyword_score for c in rest if c.text != LEAVE] == [None] * (len(FILES) - 2)
    assert all(c.semantic_score is not None and c.semantic_score < 0.5 for c in rest)
    assert result.excluded == []


async def test_a_chunk_only_keyword_search_finds_is_retrieved(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await knowledge_base(app, owner)

    hybrid = await search(app, project_id, PRODUCT_QUESTION, min_score=0.3)
    semantic_only = await search(app, project_id, PRODUCT_QUESTION, min_score=0.3, hybrid_weight=1)

    # Hybrid search finds the product by its code, and it clears the minimum score.
    assert texts(hybrid) == [PRODUCT]
    (product,) = hybrid.candidates
    assert product.keyword_score == pytest.approx(3 / 6)
    assert product.relevance == pytest.approx(3 / 6)
    # Semantic search alone can't tell the product Chunk is relevant.
    assert semantic_only.candidates == []
    excluded = {e.text: e for e in semantic_only.excluded}
    assert excluded[PRODUCT].reason == "below_min_score"
    assert excluded[PRODUCT].relevance < 0.3


async def test_keyword_search_alone_finds_only_chunks_sharing_words(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await knowledge_base(app, owner)

    result = await search(app, project_id, PRODUCT_QUESTION, hybrid_weight=0)

    assert texts(result) == [PRODUCT]
    assert result.candidates[0].semantic_score is None
    assert result.candidates[0].score == pytest.approx(1.0)


async def test_the_hybrid_weighting_decides_between_the_searches(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await knowledge_base(app, owner)

    leaning_semantic = await search(app, project_id, RULES, hybrid_weight=0.8)
    leaning_keyword = await search(app, project_id, RULES, hybrid_weight=0.2)

    # Semantic search ranks RULES first (exact text); keyword search ranks RULES_REPEATED first.
    assert texts(leaning_semantic)[:2] == [RULES, RULES_REPEATED]
    assert texts(leaning_keyword)[:2] == [RULES_REPEATED, RULES]
    # Weighted reciprocal rank fusion (k = 60), scaled so first in every search scores 1.
    rules = leaning_keyword.candidates[1]
    assert rules.score == pytest.approx(0.2 * 61 / 61 + 0.8 * 61 / 62)


async def test_chunks_below_the_minimum_score_are_excluded_with_their_reason(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await knowledge_base(app, owner)

    strict = await search(app, project_id, UNRELATED_QUESTION, min_score=0.3)
    lenient = await search(app, project_id, UNRELATED_QUESTION, min_score=0.1)

    # Nothing is relevant enough: no candidates, and every Chunk found says why it was left out.
    assert strict.candidates == []
    assert {e.text for e in strict.excluded} == set(FILES.values())
    assert {e.reason for e in strict.excluded} == {"below_min_score"}
    parking = next(e for e in strict.excluded if e.text == PARKING)
    assert parking.relevance == pytest.approx(1 / 5)  # "the", 1 of the query's 5 terms
    assert parking.document_name == "parking.txt"
    assert parking.score > 0
    # A lower minimum lets the weak keyword match through, and only it.
    assert texts(lenient) == [PARKING]


async def test_chunks_beyond_top_k_are_excluded_with_their_reason(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await knowledge_base(app, owner)

    result = await search(app, project_id, LEAVE, top_k=1)

    assert texts(result) == [LEAVE]
    assert len(result.excluded) == len(FILES) - 1
    assert {e.reason for e in result.excluded} == {"outside_top_k"}
    assert LEAVE not in {e.text for e in result.excluded}
    excluded_scores = [e.score for e in result.excluded]
    assert excluded_scores == sorted(excluded_scores, reverse=True)
    assert all(e.score <= result.candidates[0].score for e in result.excluded)


async def test_only_the_projects_own_chunks_are_searched(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    project_id = await knowledge_base(app, owner)
    # The same texts in another Project of the Organisation, and in another Organisation.
    sibling = await create_project(owner, "Sibling")
    await upload(app, owner, sibling, "product.txt", b"Sibling only: " + PRODUCT.encode())
    stranger = await tenant_factory()
    await knowledge_base(app, stranger)

    semantic = await search(app, project_id, LEAVE, top_k=20)
    keyword = await search(app, project_id, PRODUCT_QUESTION, hybrid_weight=0, top_k=20)

    assert sorted(texts(semantic)) == sorted(FILES.values())
    assert len({c.chunk_id for c in semantic.candidates}) == len(FILES)
    assert texts(keyword) == [PRODUCT]
    assert semantic.excluded == keyword.excluded == []
    empty = await create_project(owner, "Empty")
    nothing = await search(app, empty, PRODUCT_QUESTION)
    assert (nothing.candidates, nothing.excluded) == ([], [])


async def test_only_chunks_of_the_active_embedding_model_are_searched(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await knowledge_base(app, owner)
    # Chunks left over from another Embedding Model (as after a model change, ticket 03-10).
    async with app.state.sessionmaker() as session:
        await session.execute(
            update(Chunk)
            .where(Chunk.project_id == uuid.UUID(project_id), Chunk.text.in_([EXPENSES, PRODUCT]))
            .values(embedding_model_id="an-old-model")
        )
        await session.commit()

    semantic = await search(app, project_id, EXPENSES, top_k=20)
    keyword = await search(app, project_id, PRODUCT_QUESTION, hybrid_weight=0)

    assert EXPENSES not in texts(semantic)
    assert len(semantic.candidates) == len(FILES) - 2
    assert keyword.candidates == []


async def test_a_question_without_words_finds_nothing_by_keyword(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await knowledge_base(app, owner)

    result = await search(app, project_id, "?!", hybrid_weight=0)

    assert (result.candidates, result.excluded) == ([], [])


async def test_a_project_whose_embedding_model_has_no_embedder_cant_be_searched(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await knowledge_base(app, owner)
    app.state.ingestion.embedders = {}

    with pytest.raises(EmbeddingModelUnavailableError):
        await search(app, project_id, LEAVE)
