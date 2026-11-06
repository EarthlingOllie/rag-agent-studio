"""The retrieval probe's query is served by the Embedding Model's HNSW index.

There is no API surface for which plan Postgres picks, so this calls the probe module with
sequential scans and sorts discouraged (as a large table would make the planner choose) and
reads the Chunks table directly, which the shared test seams allow for behaviour with no API
surface.
"""

import uuid

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings.registry import LOCAL_MODEL
from app.projects.models import Project
from app.retrieval.probe import probe, probe_statement
from tests.conftest import SignedUpMember
from tests.documents import chunks, create_project, upload

# Many more Chunks than HNSW's candidate list (hnsw.ef_search, 40 by default).
OTHER_PROJECT_CHUNKS = 200


async def _copy_chunk(session: AsyncSession, chunk_id: str, copies: int) -> None:
    """Copies the Chunk under new ordinals, as further Chunks of its Document (local model)."""
    await session.execute(
        text(
            "INSERT INTO chunks (id, organisation_id, project_id, document_id, edition, ordinal,"
            " text, heading_path, embedding, embedding_model_id)"
            " SELECT gen_random_uuid(), organisation_id, project_id, document_id, edition,"
            " ordinal + g, text, heading_path, embedding::vector(384) + noise, embedding_model_id"
            " FROM chunks, generate_series(1, :copies) AS g,"
            # Each copy is moved a little in every dimension, deterministically: near-identical
            # vectors would not form a navigable graph.
            " LATERAL (SELECT array_agg((0.01 * sin(g * 7.3 + i * 1.7))::real)::vector AS noise"
            " FROM generate_series(1, 384) AS i) AS moved"
            " WHERE id = :id"
        ),
        {"id": chunk_id, "copies": copies},
    )


async def _as_on_a_large_table(session: AsyncSession) -> None:
    """Steers the planner as a large table would: away from reading every Chunk of the Project
    and sorting them, towards an index that returns them in distance order."""
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    await session.execute(text("SET LOCAL enable_sort = off"))


async def _setup(app: FastAPI, owner: SignedUpMember) -> tuple[str, list[float]]:
    """A Project with three Chunks, and the vector of another Project's Chunk that is nearer the
    query than any of them, copied many times over."""
    mine = await create_project(owner)
    other = await create_project(owner)
    my_document = await upload(app, owner, mine, "leave.md", b"Everyone gets 25 days of leave.")
    other_document = await upload(app, owner, other, "pay.md", b"Expenses are paid monthly.")
    (my_chunk,) = await chunks(owner, mine, my_document["id"])
    (other_chunk,) = await chunks(owner, other, other_document["id"])
    async with app.state.sessionmaker() as session, session.begin():
        await _copy_chunk(session, my_chunk["id"], 2)
        await _copy_chunk(session, other_chunk["id"], OTHER_PROJECT_CHUNKS)
        query = (
            await session.execute(
                text("SELECT embedding::real[] FROM chunks WHERE id = :id"),
                {"id": other_chunk["id"]},
            )
        ).scalar_one()
    return mine, list(query)


async def test_the_probe_orders_on_the_models_hnsw_index(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id, query = await _setup(app, owner)

    async with app.state.sessionmaker() as session, session.begin():
        await _as_on_a_large_table(session)
        project = await session.get(Project, uuid.UUID(project_id))
        assert project is not None
        statement = probe_statement(project, LOCAL_MODEL, query, 3)
        compiled = statement.compile(
            dialect=session.bind.dialect, compile_kwargs={"literal_binds": True}
        )
        plan = "\n".join(row for (row,) in await session.execute(text(f"EXPLAIN {compiled}")))

    assert "Index Scan using ix_chunks_embedding_hnsw_multilingual_e5_small" in plan
    assert "Sort" not in plan


async def test_the_index_finds_a_projects_chunks_behind_other_projects_nearer_ones(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id, query = await _setup(app, owner)

    async with app.state.sessionmaker() as session, session.begin():
        await _as_on_a_large_table(session)
        project = await session.get(Project, uuid.UUID(project_id))
        assert project is not None
        hits = await probe(session, project, LOCAL_MODEL, query, 3)

    assert len(hits) == 3
    assert {hit.chunk.project_id for hit in hits} == {uuid.UUID(project_id)}
    assert [hit.score for hit in hits] == sorted((hit.score for hit in hits), reverse=True)
