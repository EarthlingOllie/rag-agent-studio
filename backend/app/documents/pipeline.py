"""Ingestion: one Document from Queued to Ready.

1. Set Processing, if the Project's Document quota still has room for it.
2. Fetch the original, check its content matches its type, and convert it through the
   document-converter port.
3. Store the converted markdown.
4. Chunk it with ``HybridChunker``, counting tokens with the Embedding Model's tokenizer.
5. Embed the Chunks through the embedder port, in batches.
6. Write the Chunks and set Ready, in one transaction.

A failure sets Failed with a ``FailureCategory`` and a readable message. A transient failure
(the Embedding Model's provider failing) instead puts the Document back to Queued and asks the
task to run again after a backoff, until the last attempt. The ingestion Guardrail scan joins
between steps 5 and 6 in ticket 03-07.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.documents import limits
from app.documents.chunking import ChunkDraft, chunk_document
from app.documents.converter import UnsupportedContentError
from app.documents.models import Chunk, Document, DocumentStatus, FailureCategory
from app.documents.ports import IngestionPorts
from app.embeddings.port import EmbeddingProviderError
from app.projects.models import Project
from app.storage.port import ObjectNotFoundError

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 32


@dataclass(frozen=True)
class Attempt:
    """Which automatic attempt this run is (from 1), of how many, and the backoff between."""

    number: int = 1
    max_attempts: int = 1
    retry_base_seconds: float = 10.0
    retry_max_seconds: float = 300.0


class IngestionFailedError(Exception):
    def __init__(self, category: FailureCategory, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message


def markdown_key(document: Document) -> str:
    return f"{document.object_key}.converted.md"


async def _start(session: AsyncSession, document_id: uuid.UUID) -> tuple[Document, str] | None:
    """Claims a Queued Document by setting it to Processing; ``None`` if it isn't Queued. A
    Document the Project's quota no longer has room for is set to Failed instead."""
    row = (
        await session.execute(
            select(Document, Project)
            .join(Project, Project.id == Document.project_id)
            .where(Document.id == document_id)
            # Locking the Project too makes the quota check below one at a time per Project.
            .with_for_update()
        )
    ).one_or_none()
    if row is None or row[0].status != DocumentStatus.QUEUED:
        return None
    document, project = row
    document.attempt_count += 1
    document.updated_at = func.now()
    others = await limits.documents_counted(session, project.id, excluding=document.id)
    if others >= project.document_quota:
        document.status = DocumentStatus.FAILED
        document.error_category = FailureCategory.QUOTA
        document.error_message = limits.quota_failure_message(project.document_quota)
        await session.commit()
        return None
    document.status = DocumentStatus.PROCESSING
    await session.commit()
    return document, project.embedding_model_id


def _embed(ports: IngestionPorts, model_id: str, drafts: list[ChunkDraft]) -> list[list[float]]:
    embedder = ports.embedders[model_id]
    vectors: list[list[float]] = []
    for start in range(0, len(drafts), EMBED_BATCH_SIZE):
        batch = drafts[start : start + EMBED_BATCH_SIZE]
        vectors.extend(embedder.embed_passages([draft.embedding_text for draft in batch]))
    return vectors


async def _process(
    ports: IngestionPorts, document: Document, model_id: str, *, chunk_max_tokens: int
) -> tuple[list[ChunkDraft], list[list[float]]]:
    """Steps 2 to 5. Raises ``IngestionFailedError`` for a failure that isn't transient."""
    try:
        original = await ports.object_store.get(document.object_key)
    except ObjectNotFoundError:
        raise IngestionFailedError(FailureCategory.CONVERSION, limits.ORIGINAL_MISSING) from None
    if not limits.content_matches_type(original, document.mime_type):
        raise IngestionFailedError(
            FailureCategory.UNSUPPORTED_CONTENT, limits.wrong_type_message(document.mime_type)
        )
    try:
        converted = await asyncio.to_thread(ports.converter.convert, original, document.name)
    except UnsupportedContentError:
        raise IngestionFailedError(
            FailureCategory.UNSUPPORTED_CONTENT, limits.UNREADABLE_CONTENT
        ) from None
    except Exception:
        logger.exception("Conversion failed", extra={"document_id": str(document.id)})
        raise IngestionFailedError(FailureCategory.CONVERSION, limits.CONVERSION_FAILED) from None
    await ports.object_store.put(
        markdown_key(document),
        converted.export_to_markdown().encode(),
        content_type="text/markdown; charset=utf-8",
    )
    embedder = ports.embedders[model_id]
    tokenizer = embedder.tokenizer(min(chunk_max_tokens, embedder.model.max_tokens))
    drafts = await asyncio.to_thread(chunk_document, converted, tokenizer)
    if not drafts:
        raise IngestionFailedError(FailureCategory.UNSUPPORTED_CONTENT, limits.NO_TEXT)
    vectors = await asyncio.to_thread(_embed, ports, model_id, drafts)
    return drafts, vectors


async def ingest(
    sessionmaker: async_sessionmaker[AsyncSession],
    ports: IngestionPorts,
    document_id: uuid.UUID,
    *,
    chunk_max_tokens: int,
    attempt: Attempt,
) -> float | None:
    """Processes the Document. Returns the seconds to wait before running again when a
    transient failure should be retried, and ``None`` otherwise."""
    async with sessionmaker() as session:
        started = await _start(session, document_id)
    if started is None:
        return None
    document, model_id = started
    try:
        drafts, vectors = await _process(
            ports, document, model_id, chunk_max_tokens=chunk_max_tokens
        )
    except IngestionFailedError as failure:
        await _fail(sessionmaker, document, failure.category, failure.message)
        return None
    except EmbeddingProviderError:
        logger.warning(
            "Embedding provider failed",
            extra={"document_id": str(document_id), "attempt": attempt.number},
        )
        if attempt.number >= attempt.max_attempts:
            message = limits.provider_failed_message(attempt.max_attempts)
            await _fail(sessionmaker, document, FailureCategory.PROVIDER, message)
            return None
        message = limits.provider_retrying_message(attempt.number + 1, attempt.max_attempts)
        async with sessionmaker() as session, session.begin():
            await _set_status(session, document, DocumentStatus.QUEUED, error=message)
        return limits.retry_delay(
            attempt.number,
            base_seconds=attempt.retry_base_seconds,
            max_seconds=attempt.retry_max_seconds,
        )
    except Exception:
        logger.exception("Ingestion failed", extra={"document_id": str(document_id)})
        await _fail(sessionmaker, document, FailureCategory.CONVERSION, limits.PROCESSING_FAILED)
        return None
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
    return None


async def _set_status(
    session: AsyncSession,
    document: Document,
    status: DocumentStatus,
    *,
    error: str | None = None,
    category: FailureCategory | None = None,
    markdown: str | None = None,
) -> None:
    stored = await session.get_one(Document, document.id, with_for_update=True)
    stored.status = status
    stored.error_message = error
    stored.error_category = category
    stored.markdown_key = markdown
    stored.updated_at = func.now()


async def _fail(
    sessionmaker: async_sessionmaker[AsyncSession],
    document: Document,
    category: FailureCategory,
    message: str,
) -> None:
    async with sessionmaker() as session, session.begin():
        await _set_status(
            session, document, DocumentStatus.FAILED, error=message, category=category
        )
