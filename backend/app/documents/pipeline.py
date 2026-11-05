"""Ingestion: one Document from Queued to Ready.

1. Set Processing.
2. Fetch the original and convert it through the document-converter port, with OCR only if
   the Project's flag is on.
3. Store the converted markdown.
4. Chunk it with ``HybridChunker``, counting tokens with the Embedding Model's tokenizer.
5. Embed the Chunks through the embedder port, in batches.
6. Write the Chunks and set Ready, in one transaction.

A failure sets Failed with a readable message. Ticket 03-04 categorises failures and retries
transient ones; the ingestion Guardrail scan joins between steps 5 and 6 in ticket 03-07.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from functools import partial

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.documents.chunking import ChunkDraft, chunk_document
from app.documents.models import Chunk, Document, DocumentStatus
from app.documents.ports import IngestionPorts
from app.projects.models import Project

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 32
PROCESSING_FAILED = "This Document couldn't be processed. Try uploading it again."


def markdown_key(document: Document) -> str:
    return f"{document.object_key}.converted.md"


@dataclass(frozen=True)
class _Started:
    document: Document
    # The Project's settings, read when the Document is claimed.
    embedding_model_id: str
    ocr: bool


async def _start(session: AsyncSession, document_id: uuid.UUID) -> _Started | None:
    """Claims a Queued Document by setting it to Processing; ``None`` if it isn't Queued."""
    row = (
        await session.execute(
            select(Document, Project.embedding_model_id, Project.ocr_enabled)
            .join(Project, Project.id == Document.project_id)
            .where(Document.id == document_id)
            .with_for_update(of=Document)
        )
    ).one_or_none()
    if row is None or row[0].status != DocumentStatus.QUEUED:
        return None
    document, embedding_model_id, ocr = row
    document.status = DocumentStatus.PROCESSING
    document.attempt_count += 1
    document.updated_at = func.now()
    await session.commit()
    return _Started(document, embedding_model_id, ocr)


def _embed(ports: IngestionPorts, model_id: str, drafts: list[ChunkDraft]) -> list[list[float]]:
    embedder = ports.embedders[model_id]
    vectors: list[list[float]] = []
    for start in range(0, len(drafts), EMBED_BATCH_SIZE):
        batch = drafts[start : start + EMBED_BATCH_SIZE]
        vectors.extend(embedder.embed_passages([draft.embedding_text for draft in batch]))
    return vectors


async def ingest(
    sessionmaker: async_sessionmaker[AsyncSession],
    ports: IngestionPorts,
    document_id: uuid.UUID,
    *,
    chunk_max_tokens: int,
) -> None:
    async with sessionmaker() as session:
        started = await _start(session, document_id)
    if started is None:
        return
    document, model_id = started.document, started.embedding_model_id
    try:
        original = await ports.object_store.get(document.object_key)
        converted = await asyncio.to_thread(
            partial(ports.converter.convert, ocr=started.ocr), original, document.name
        )
        await ports.object_store.put(
            markdown_key(document),
            converted.export_to_markdown().encode(),
            content_type="text/markdown; charset=utf-8",
        )
        embedder = ports.embedders[model_id]
        tokenizer = embedder.tokenizer(min(chunk_max_tokens, embedder.model.max_tokens))
        drafts = await asyncio.to_thread(chunk_document, converted, tokenizer)
        vectors = await asyncio.to_thread(_embed, ports, model_id, drafts)
    except Exception:
        logger.exception("Ingestion failed", extra={"document_id": str(document_id)})
        await _finish(sessionmaker, document, status=DocumentStatus.FAILED, error=PROCESSING_FAILED)
        return
    async with sessionmaker() as session, session.begin():
        # A Document is only claimed from Queued, so these are leftovers of an interrupted run.
        await session.execute(
            delete(Chunk).where(Chunk.document_id == document.id, Chunk.edition == document.edition)
        )
        session.add_all(
            Chunk(
                organisation_id=document.organisation_id,
                project_id=document.project_id,
                document_id=document.id,
                edition=document.edition,
                ordinal=ordinal,
                text=draft.text,
                heading_path=draft.heading_path,
                page_start=draft.page_start,
                page_end=draft.page_end,
                embedding=vector,
                embedding_model_id=model_id,
            )
            for ordinal, (draft, vector) in enumerate(zip(drafts, vectors, strict=True))
        )
        await _set_status(session, document, DocumentStatus.READY, markdown=markdown_key(document))


async def _set_status(
    session: AsyncSession,
    document: Document,
    status: DocumentStatus,
    *,
    error: str | None = None,
    markdown: str | None = None,
) -> None:
    stored = await session.get_one(Document, document.id, with_for_update=True)
    stored.status = status
    stored.error_message = error
    stored.markdown_key = markdown
    stored.updated_at = func.now()


async def _finish(
    sessionmaker: async_sessionmaker[AsyncSession],
    document: Document,
    *,
    status: DocumentStatus,
    error: str,
) -> None:
    async with sessionmaker() as session, session.begin():
        await _set_status(session, document, status, error=error)
