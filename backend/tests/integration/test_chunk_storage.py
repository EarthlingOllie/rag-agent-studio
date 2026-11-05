"""How Chunks are stored: vector, Embedding Model ID and ``tsvector``, with HNSW and GIN indexes.

Retrieval (spec 04) is the API surface for these; until it exists, this reads the table
directly, which the shared test seams allow for behaviour with no API surface.
"""

import math
import uuid

from fastapi import FastAPI
from sqlalchemy import text

from app.documents.tasks import enqueue_ingestion
from tests.conftest import SignedUpMember
from tests.documents import chunks, create_project, documents, upload


async def test_chunks_store_a_vector_of_the_models_dimension_and_a_full_text_index(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    document = await upload(
        app, owner, project_id, "leave.md", b"# Leave\n\nEveryone gets 25 days of annual leave."
    )
    (chunk,) = await chunks(owner, project_id, document["id"])

    async with app.state.sessionmaker() as session:
        row = (
            await session.execute(
                text(
                    "SELECT embedding::real[] AS vector, vector_dims(embedding) AS dims,"
                    " embedding_model_id, search_vector @@ plainto_tsquery('simple', 'annual"
                    " leave') AS found, search_vector @@ plainto_tsquery('simple', 'expenses')"
                    " AS not_found FROM chunks WHERE id = :id"
                ),
                {"id": chunk["id"]},
            )
        ).one()

    assert (row.dims, row.embedding_model_id) == (384, "multilingual-e5-small")
    assert math.isclose(math.sqrt(sum(v * v for v in row.vector)), 1.0, rel_tol=1e-5)
    assert (row.found, row.not_found) == (True, False)


async def test_chunk_vectors_have_an_hnsw_index_per_model_and_text_a_gin_index(
    app: FastAPI,
) -> None:
    async with app.state.sessionmaker() as session:
        rows = await session.execute(
            text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'chunks'")
        )
        indexes = {name: definition for name, definition in rows}

    hnsw = indexes["ix_chunks_embedding_hnsw_multilingual_e5_small"]
    assert "USING hnsw" in hnsw
    assert "(embedding)::vector(384)" in hnsw
    assert "vector_cosine_ops" in hnsw
    assert "WHERE ((embedding_model_id)::text = 'multilingual-e5-small'::text)" in hnsw
    assert "USING gin (search_vector)" in indexes["ix_chunks_search_vector"]


async def test_ingestion_runs_once_per_upload(app: FastAPI, owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "leave.md", b"# Leave\n\n25 days.")
    before = await chunks(owner, project_id, document["id"])

    # A redelivered task, and one for a Document that doesn't exist, change nothing.
    await enqueue_ingestion(uuid.UUID(document["id"]))
    await enqueue_ingestion(uuid.uuid4())

    assert await chunks(owner, project_id, document["id"]) == before
    (listed,) = await documents(owner, project_id)
    assert listed["status"] == "ready"
