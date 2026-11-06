"""Ingestion: one Document from Queued to Ready.

1. Set Processing.
2. Fetch the original and convert it through the document-converter port, with OCR only if
   the Project's flag is on.
3. Store the converted markdown.
4. Chunk it with ``HybridChunker``, counting tokens with the Embedding Model's tokenizer.
5. Embed the Chunks through the embedder port, in batches: the local model, or the Project's
   provider model through the model gateway with its Provider Credential.
6. Write the Chunks and set Ready, in one transaction.

A replacement goes through the same steps as the Document's staged edition: its Chunks are
written under the new edition number, and in the same transaction the staged edition is swapped
in and the old edition's Chunks removed, so retrieval goes from the old edition to the new one
in one step. Until then, and if the replacement fails, the old edition keeps serving.

A failure sets Failed with a readable message. Ticket 03-04 categorises failures and retries
transient ones; the ingestion Guardrail scan joins between steps 5 and 6 in ticket 03-07.
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
from app.documents.chunking import ChunkDraft, chunk_document
from app.documents.models import Chunk, Document, DocumentStatus, StagedEdition
from app.documents.ports import IngestionPorts
from app.embeddings.port import Embedder
from app.embeddings.provider import resolve_embedder
from app.embeddings.registry import embedding_model
from app.gateway.gateway import ModelGateway
from app.projects.models import Project

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 32
PROCESSING_FAILED = "This Document couldn't be processed. Try uploading it again."


DeleteObjects = Callable[[list[str]], Awaitable[None]]
"""Schedules deletion of stored objects, by key (the ``documents.delete_objects`` task)."""


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
    when it is Queued, otherwise its staged edition when that is. ``None`` if neither is.
    The job carries the Project's Embedding Model and the credential it is called through."""
    row = (
        await session.execute(
            select(Document, Project.embedding_model_id, Project.ocr_enabled, ProviderCredential)
            .join(Project, Project.id == Document.project_id)
            .outerjoin(ProviderCredential, ProviderCredential.id == Project.embedding_credential_id)
            .where(Document.id == document_id)
            .with_for_update(of=Document)
        )
    ).one_or_none()
    if row is None:
        return None
    document, embedding_model_id, ocr, credential = row
    claimed: Document | StagedEdition = document
    if document.status != DocumentStatus.QUEUED:
        staged = await session.get(StagedEdition, document.id, with_for_update=True)
        if staged is None or staged.status != DocumentStatus.QUEUED:
            return None
        claimed = staged
    claimed.status = DocumentStatus.PROCESSING
    claimed.attempt_count += 1
    claimed.updated_at = func.now()
    job = _Job(
        document_id=document.id,
        organisation_id=document.organisation_id,
        project_id=document.project_id,
        edition=claimed.edition,
        name=claimed.name,
        object_key=claimed.object_key,
        staged=claimed is not document,
        embedding_model_id=embedding_model_id,
        ocr=ocr,
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


async def ingest(
    sessionmaker: async_sessionmaker[AsyncSession],
    ports: IngestionPorts,
    gateway: ModelGateway,
    document_id: uuid.UUID,
    *,
    chunk_max_tokens: int,
    delete_objects: DeleteObjects,
) -> None:
    async with sessionmaker() as session:
        job = await _start(session, document_id)
    if job is None:
        return
    model_id, credential = job.embedding_model_id, job.credential
    try:
        original = await ports.object_store.get(job.object_key)
        converted = await asyncio.to_thread(
            partial(ports.converter.convert, ocr=job.ocr), original, job.name
        )
        await ports.object_store.put(
            markdown_key(job.object_key),
            converted.export_to_markdown().encode(),
            content_type="text/markdown; charset=utf-8",
        )
        embedder = resolve_embedder(embedding_model(model_id), credential, ports.embedders, gateway)
        tokenizer = embedder.tokenizer(min(chunk_max_tokens, embedder.model.max_tokens))
        drafts = await asyncio.to_thread(chunk_document, converted, tokenizer)
        vectors = await _embed(embedder, drafts)
    except Exception:
        logger.exception("Ingestion failed", extra={"document_id": str(document_id)})
        await _fail(sessionmaker, job, delete_objects)
        return
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
                    embedding_model_id=model_id,
                )
                for ordinal, (draft, vector) in enumerate(zip(drafts, vectors, strict=True))
            )
            replaced = await _swap(session, document) if job.staged else []
            document.status = DocumentStatus.READY
            document.error_message = None
            document.markdown_key = markdown_key(job.object_key)
            document.updated_at = func.now()
    if document is None:
        # Deleted while it was being processed: nothing refers to what was just stored.
        await delete_objects(stored_keys(job.object_key))
    elif replaced:
        await delete_objects(replaced)


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


async def _fail(
    sessionmaker: async_sessionmaker[AsyncSession], job: _Job, delete_objects: DeleteObjects
) -> None:
    """Sets the edition Failed. A failed staged edition leaves the Document as it was, so its
    current edition keeps serving."""
    async with sessionmaker() as session, session.begin():
        document = await session.get(Document, job.document_id, with_for_update=True)
        if document is not None:
            failed: Document | StagedEdition = document
            if job.staged:
                failed = await session.get_one(StagedEdition, document.id, with_for_update=True)
            failed.status = DocumentStatus.FAILED
            failed.error_message = PROCESSING_FAILED
            failed.updated_at = func.now()
    if document is None:
        await delete_objects(stored_keys(job.object_key))
