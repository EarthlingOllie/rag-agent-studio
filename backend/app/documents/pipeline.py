"""Ingestion: one Document from Queued to Ready.

1. Set Processing, if the Project's Document quota still has room for it.
2. Fetch the original, check its content matches its type, and convert it through the
   document-converter port, with OCR only if the Project's flag is on.
3. Store the converted markdown.
4. Chunk it with ``HybridChunker``, counting tokens with the Embedding Model's tokenizer.
5. Embed the Chunks through the embedder port, in batches: the local model, or the Project's
   provider model through the model gateway with its Provider Credential.
6. Scan the Chunks through the injection-classifier port (the ingestion Guardrail scan): each
   Chunk the classifier flags as instructions aimed at an AI keeps its label, score and reason.
7. Write the Chunks and set Ready, in one transaction.

A replacement goes through the same steps as the Document's staged edition: its Chunks are
written under the new edition number, and in the same transaction the staged edition is swapped
in and the old edition's Chunks removed, so retrieval goes from the old edition to the new one
in one step. Until then, and if the replacement fails, the old edition keeps serving. A
replacement doesn't add a Document, so the quota doesn't apply to it.

A failure sets Failed with a ``FailureCategory`` and a readable message. A transient failure
(the Embedding Model's provider failing) instead puts the edition back to Queued and asks the
task to run again after a backoff, until the last attempt.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.credentials.models import ProviderCredential
from app.documents import limits
from app.documents.chunking import ChunkDraft, chunk_document
from app.documents.converter import UnsupportedContentError
from app.documents.models import Chunk, Document, DocumentStatus, FailureCategory, StagedEdition
from app.documents.ports import IngestionPorts
from app.embeddings.port import Embedder, EmbeddingProviderError
from app.embeddings.provider import UNUSABLE_ERRORS, EmbeddingSizeError, resolve_embedder
from app.embeddings.registry import embedding_model
from app.gateway.gateway import ModelGateway
from app.guardrails.classifier import InjectionFlag
from app.projects.models import Project
from app.storage.port import ObjectNotFoundError

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 32


DeleteObjects = Callable[[list[str]], Awaitable[None]]
"""Schedules deletion of stored objects, by key (the ``documents.delete_objects`` task)."""


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


def markdown_key(object_key: str) -> str:
    """Where the converted markdown of the original stored under ``object_key`` goes."""
    return f"{object_key}.converted.md"


@dataclass(frozen=True)
class _Job:
    """One edition being ingested: the Document's first, or a staged newer one."""

    document_id: uuid.UUID
    organisation_id: uuid.UUID
    project_id: uuid.UUID
    edition: int
    name: str
    mime_type: str
    object_key: str
    staged: bool
    # The Project's settings, read when the edition is claimed.
    embedding_model_id: str
    ocr: bool
    credential: ProviderCredential | None
    """The Provider Credential the Project's Embedding Model is called through; ``None`` for
    the local model."""


async def _start(session: AsyncSession, document_id: uuid.UUID) -> _Job | None:
    """Claims the Document's Queued edition by setting it to Processing: the Document itself
    when it is Queued, otherwise its staged edition when that is. ``None`` if neither is. A
    Queued Document the Project's quota no longer has room for is set to Failed instead. The job
    carries the Project's Embedding Model and the credential it is called through."""
    row = (
        await session.execute(
            select(Document, Project, ProviderCredential)
            .join(Project, Project.id == Document.project_id)
            .outerjoin(ProviderCredential, ProviderCredential.id == Project.embedding_credential_id)
            .where(Document.id == document_id)
            # Locking the Project too makes the quota check below one at a time per Project.
            .with_for_update(of=[Document, Project])
        )
    ).one_or_none()
    if row is None:
        return None
    document, project, credential = row
    claimed: Document | StagedEdition = document
    if document.status != DocumentStatus.QUEUED:
        staged = await session.get(StagedEdition, document.id, with_for_update=True)
        if staged is None or staged.status != DocumentStatus.QUEUED:
            return None
        claimed = staged
    claimed.attempt_count += 1
    claimed.updated_at = func.now()
    if claimed is document:
        others = await limits.documents_counted(session, project.id, excluding=document.id)
        if others >= project.document_quota:
            document.status = DocumentStatus.FAILED
            document.error_category = FailureCategory.QUOTA
            document.error_message = limits.quota_failure_message(project.document_quota)
            await session.commit()
            return None
    claimed.status = DocumentStatus.PROCESSING
    job = _Job(
        document_id=document.id,
        organisation_id=document.organisation_id,
        project_id=document.project_id,
        edition=claimed.edition,
        name=claimed.name,
        mime_type=claimed.mime_type,
        object_key=claimed.object_key,
        staged=claimed is not document,
        embedding_model_id=project.embedding_model_id,
        ocr=project.ocr_enabled,
        credential=credential,
    )
    await session.commit()
    return job


async def _embed(embedder: Embedder, drafts: list[ChunkDraft]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(drafts), EMBED_BATCH_SIZE):
        batch = drafts[start : start + EMBED_BATCH_SIZE]
        vectors.extend(await embedder.embed_passages([draft.embedding_text for draft in batch]))
    return vectors


async def _process(
    ports: IngestionPorts, gateway: ModelGateway, job: _Job, *, chunk_max_tokens: int
) -> tuple[list[ChunkDraft], list[list[float]], list[InjectionFlag | None]]:
    """Steps 2 to 6. Raises ``IngestionFailedError`` for a failure that isn't transient."""
    try:
        original = await ports.object_store.get(job.object_key)
    except ObjectNotFoundError:
        raise IngestionFailedError(FailureCategory.CONVERSION, limits.ORIGINAL_MISSING) from None
    if not limits.content_matches_type(original, job.mime_type):
        raise IngestionFailedError(
            FailureCategory.UNSUPPORTED_CONTENT, limits.wrong_type_message(job.mime_type)
        )
    try:
        converted = await asyncio.to_thread(
            partial(ports.converter.convert, ocr=job.ocr), original, job.name
        )
    except UnsupportedContentError:
        raise IngestionFailedError(
            FailureCategory.UNSUPPORTED_CONTENT, limits.UNREADABLE_CONTENT
        ) from None
    except Exception:
        logger.exception("Conversion failed", extra={"document_id": str(job.document_id)})
        raise IngestionFailedError(FailureCategory.CONVERSION, limits.CONVERSION_FAILED) from None
    await ports.object_store.put(
        markdown_key(job.object_key),
        converted.export_to_markdown().encode(),
        content_type="text/markdown; charset=utf-8",
    )
    try:
        embedder = resolve_embedder(
            embedding_model(job.embedding_model_id), job.credential, ports.embedders, gateway
        )
    except UNUSABLE_ERRORS as error:
        raise IngestionFailedError(
            FailureCategory.PROVIDER, limits.provider_setup_message(str(error))
        ) from None
    tokenizer = embedder.tokenizer(min(chunk_max_tokens, embedder.model.max_tokens))
    drafts = await asyncio.to_thread(chunk_document, converted, tokenizer)
    if not drafts:
        raise IngestionFailedError(FailureCategory.UNSUPPORTED_CONTENT, limits.NO_TEXT)
    try:
        vectors = await _embed(embedder, drafts)
    except EmbeddingSizeError as error:
        raise IngestionFailedError(
            FailureCategory.PROVIDER, limits.provider_setup_message(str(error))
        ) from None
    flags = await asyncio.to_thread(ports.classifier.classify, [draft.text for draft in drafts])
    return drafts, vectors, flags


async def ingest(
    sessionmaker: async_sessionmaker[AsyncSession],
    ports: IngestionPorts,
    gateway: ModelGateway,
    document_id: uuid.UUID,
    *,
    chunk_max_tokens: int,
    delete_objects: DeleteObjects,
    attempt: Attempt,
) -> float | None:
    """Processes the Document's Queued edition. Returns the seconds to wait before running
    again when a transient failure should be retried, and ``None`` otherwise."""
    async with sessionmaker() as session:
        job = await _start(session, document_id)
    if job is None:
        return None
    try:
        drafts, vectors, flags = await _process(
            ports, gateway, job, chunk_max_tokens=chunk_max_tokens
        )
    except IngestionFailedError as failure:
        await _fail(sessionmaker, job, delete_objects, failure.category, failure.message)
        return None
    except EmbeddingProviderError:
        logger.warning(
            "Embedding provider failed",
            extra={"document_id": str(document_id), "attempt": attempt.number},
        )
        if attempt.number >= attempt.max_attempts:
            message = limits.provider_failed_message(attempt.max_attempts)
            await _fail(sessionmaker, job, delete_objects, FailureCategory.PROVIDER, message)
            return None
        message = limits.provider_retrying_message(attempt.number + 1, attempt.max_attempts)
        if not await _requeue(sessionmaker, job, delete_objects, message):
            return None
        return limits.retry_delay(
            attempt.number,
            base_seconds=attempt.retry_base_seconds,
            max_seconds=attempt.retry_max_seconds,
        )
    except Exception:
        logger.exception("Ingestion failed", extra={"document_id": str(document_id)})
        await _fail(
            sessionmaker, job, delete_objects, FailureCategory.CONVERSION, limits.PROCESSING_FAILED
        )
        return None
    async with sessionmaker() as session, session.begin():
        document = await session.get(Document, job.document_id, with_for_update=True)
        if document is not None:
            # Leftovers of an interrupted run of this edition; no reader asks for them.
            await session.execute(
                delete(Chunk).where(Chunk.document_id == document.id, Chunk.edition == job.edition)
            )
            session.add_all(
                Chunk(
                    organisation_id=job.organisation_id,
                    project_id=job.project_id,
                    document_id=job.document_id,
                    edition=job.edition,
                    ordinal=ordinal,
                    text=draft.text,
                    heading_path=draft.heading_path,
                    page_start=draft.page_start,
                    page_end=draft.page_end,
                    embedding=vector,
                    embedding_model_id=job.embedding_model_id,
                    guardrail_label=flag.label if flag else None,
                    guardrail_score=flag.score if flag else None,
                    guardrail_reason=flag.reason if flag else None,
                )
                for ordinal, (draft, vector, flag) in enumerate(
                    zip(drafts, vectors, flags, strict=True)
                )
            )
            replaced = await _swap(session, document) if job.staged else []
            document.status = DocumentStatus.READY
            document.error_message = None
            document.error_category = None
            document.markdown_key = markdown_key(job.object_key)
            document.updated_at = func.now()
    if document is None:
        # Deleted while it was being processed: nothing refers to what was just stored.
        await delete_objects(stored_keys(job.object_key))
    elif replaced:
        await delete_objects(replaced)
    return None


def stored_keys(object_key: str) -> list[str]:
    """An edition's stored objects: its original and its converted markdown."""
    return [object_key, markdown_key(object_key)]


async def _swap(session: AsyncSession, document: Document) -> list[str]:
    """Makes the staged edition, whose Chunks are already written, the Document's edition, and
    removes the old edition's Chunks, all in the caller's transaction. The Document keeps its ID
    (and so its Tags). Returns the old edition's stored objects, to delete once committed."""
    staged = await session.get_one(StagedEdition, document.id, with_for_update=True)
    replaced = stored_keys(document.object_key)
    await session.execute(
        delete(Chunk).where(Chunk.document_id == document.id, Chunk.edition != staged.edition)
    )
    document.edition = staged.edition
    document.name = staged.name
    document.mime_type = staged.mime_type
    document.size_bytes = staged.size_bytes
    document.content_hash = staged.content_hash
    document.object_key = staged.object_key
    document.attempt_count = staged.attempt_count
    await session.delete(staged)
    return replaced


async def _settle(
    sessionmaker: async_sessionmaker[AsyncSession],
    job: _Job,
    delete_objects: DeleteObjects,
    status: DocumentStatus,
    message: str,
    category: FailureCategory | None,
) -> bool:
    """Sets the job's edition (the Document, or its staged edition) to the status, with the
    message and category. A failed staged edition leaves the Document as it was, so its current
    edition keeps serving; a failed Document loses any Chunks it had. ``False`` if the Document
    was deleted meanwhile."""
    async with sessionmaker() as session, session.begin():
        document = await session.get(Document, job.document_id, with_for_update=True)
        if document is not None:
            settled: Document | StagedEdition = document
            if job.staged:
                settled = await session.get_one(StagedEdition, document.id, with_for_update=True)
            elif status == DocumentStatus.FAILED:
                # A Document reprocessed from Ready that fails no longer serves its old Chunks.
                await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
            settled.status = status
            settled.error_message = message
            settled.error_category = category
            settled.updated_at = func.now()
    if document is None:
        await delete_objects(stored_keys(job.object_key))
        return False
    return True


async def _fail(
    sessionmaker: async_sessionmaker[AsyncSession],
    job: _Job,
    delete_objects: DeleteObjects,
    category: FailureCategory,
    message: str,
) -> None:
    await _settle(sessionmaker, job, delete_objects, DocumentStatus.FAILED, message, category)


async def _requeue(
    sessionmaker: async_sessionmaker[AsyncSession],
    job: _Job,
    delete_objects: DeleteObjects,
    message: str,
) -> bool:
    """Puts the edition back to Queued for an automatic retry, saying why."""
    return await _settle(sessionmaker, job, delete_objects, DocumentStatus.QUEUED, message, None)
