"""The retrieval module through its interface, against real Postgres with pgvector.

The Knowledge Base is uploaded through the API and ingested eagerly with the fake converter and
the deterministic embedder. That embedder hashes a query like a passage, so a query equal to a
Chunk's text finds exactly that Chunk with a score of 1, and every other Chunk scores far lower:
the fixture's relevant Chunk is known."""

import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy import update

from app.agents.config import Retrieval
from app.documents.models import Chunk
from app.projects.models import Project
from app.retrieval.service import EmbeddingModelUnavailableError, RetrievalResult, retrieve
from tests.conftest import SignedUpMember, TenantFactory
from tests.documents import create_project, upload

# One Chunk per file: no headings, so each Chunk's embedded text is the file's text.
LEAVE = "Everyone gets 25 days of annual leave a year."
EXPENSES = "Claim expenses within 30 days of spending."
PARKING = "Visitors park in the north car park."


async def knowledge_base(app: FastAPI, member: SignedUpMember, name: str = "Handbook") -> str:
    project_id = await create_project(member, name)
    for filename, text in [("leave.txt", LEAVE), ("expenses.txt", EXPENSES), ("park.txt", PARKING)]:
        await upload(app, member, project_id, filename, text.encode())
    return project_id


async def search(app: FastAPI, project_id: str, query: str, top_k: int = 5) -> RetrievalResult:
    async with app.state.sessionmaker() as session:
        project = await session.get_one(Project, uuid.UUID(project_id))
        return await retrieve(
            session, project, query, Retrieval(top_k=top_k), app.state.ingestion.embedders
        )


async def test_the_relevant_chunk_ranks_first_with_its_score(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await knowledge_base(app, owner)

    result = await search(app, project_id, EXPENSES)

    assert result.candidates[0].text == EXPENSES
    assert [c.rank for c in result.candidates] == [1, 2, 3]
    best, *rest = result.candidates
    assert best.score == pytest.approx(1.0)
    assert best.document_name == "expenses.txt"
    assert best.heading_path == []
    assert all(c.score < 0.5 for c in rest)
    scores = [c.score for c in result.candidates]
    assert scores == sorted(scores, reverse=True)
    assert result.excluded == []


async def test_top_k_limits_the_candidates(app: FastAPI, owner: SignedUpMember) -> None:
    project_id = await knowledge_base(app, owner)

    result = await search(app, project_id, LEAVE, top_k=1)

    assert [c.text for c in result.candidates] == [LEAVE]


async def test_only_the_projects_own_chunks_are_searched(
    app: FastAPI, owner: SignedUpMember, tenant_factory: TenantFactory
) -> None:
    project_id = await knowledge_base(app, owner)
    # The same text in another Project of the Organisation, and in another Organisation.
    sibling = await create_project(owner, "Sibling")
    await upload(app, owner, sibling, "leave.txt", b"Sibling only: " + LEAVE.encode())
    stranger = await tenant_factory()
    await knowledge_base(app, stranger)

    result = await search(app, project_id, LEAVE)

    assert sorted(c.text for c in result.candidates) == sorted([LEAVE, EXPENSES, PARKING])
    assert len({c.chunk_id for c in result.candidates}) == 3
    empty = await create_project(owner, "Empty")
    assert (await search(app, empty, LEAVE)).candidates == []


async def test_only_chunks_of_the_active_embedding_model_are_searched(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await knowledge_base(app, owner)
    # Chunks left over from another Embedding Model (as after a model change, ticket 03-10).
    async with app.state.sessionmaker() as session:
        await session.execute(
            update(Chunk)
            .where(Chunk.project_id == uuid.UUID(project_id), Chunk.text == EXPENSES)
            .values(embedding_model_id="an-old-model")
        )
        await session.commit()

    result = await search(app, project_id, EXPENSES)

    assert EXPENSES not in [c.text for c in result.candidates]
    assert len(result.candidates) == 2


async def test_a_project_whose_embedding_model_has_no_embedder_cant_be_searched(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await knowledge_base(app, owner)
    app.state.ingestion.embedders = {}

    with pytest.raises(EmbeddingModelUnavailableError):
        await search(app, project_id, LEAVE)
