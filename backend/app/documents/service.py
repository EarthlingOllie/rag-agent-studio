"""Uploading Documents: presign, direct upload, confirm. And reading Documents and Chunks.

1. ``start_upload`` checks the file type and size, and that the Project's Document quota has
   room, and answers with a presigned PUT URL. The pending upload is remembered in Redis until
   the URL expires.
2. The browser PUTs the file straight to the object store.
3. ``confirm_upload`` checks the quota again, reads the stored file, checks its real size,
   computes its SHA-256 content hash (checking it against the one the browser sent, if any),
   creates the Document as Queued, and enqueues ingestion.

``retry_document`` sends a Ready or Failed Document through ingestion again, with the
Project's current settings (its OCR flag, for one).

Every function takes the Organisation scope and finds the Project only inside it; uploads go
through ``active_project``, so an archived Project takes none. A Failed Document (or a Failed
newer edition of one) can be retried, which queues it for ingestion again.
"""

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import ScalarSelect

from app import audit
from app.documents.limits import documents_counted, mime_type_for
from app.documents.models import (
    FINAL_STATUSES,
    Chunk,
    Document,
    DocumentStatus,
    StagedEdition,
)
from app.documents.pipeline import stored_keys
from app.projects import service as projects
from app.projects.models import Project
from app.storage.port import ObjectNotFoundError, ObjectStore
from app.tags.models import DocumentTag
from app.tenancy.repository import OrganisationScope

_PENDING = "document-upload:{}"


class FileTooLargeError(Exception):
    """The file is larger than the upload limit."""


class UploadNotFoundError(Exception):
    """No pending upload with that ID in this Project: unknown, expired or already used."""


class FileNotUploadedError(Exception):
    """The object store has nothing under the upload's key yet."""


class ContentHashMismatchError(Exception):
    """The stored bytes don't hash to the content hash the browser sent."""


class DocumentNotFoundError(Exception):
    """No Document with that ID in the Project."""


class QuotaReachedError(Exception):
    """The Project already holds as many Documents as its quota allows."""

    def __init__(self, quota: int) -> None:
        super().__init__(quota)
        self.quota = quota


class DocumentBusyError(Exception):
    """The Document, or a newer edition of it, is still being processed."""


class DuplicateDocumentError(Exception):
    """The Project already has a Document with the uploaded file's content hash."""

    def __init__(self, existing: Document) -> None:
        super().__init__(existing.id)
        self.existing = existing


@dataclass(frozen=True)
class PendingUpload:
    upload_id: uuid.UUID
    url: str
    content_type: str
    expires_at: datetime


async def start_upload(
    session: AsyncSession,
    redis: Redis,
    store: ObjectStore,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    *,
    filename: str,
    size_bytes: int,
    new_document: bool = True,
    max_bytes: int,
    ttl_seconds: int,
    now: datetime,
) -> PendingUpload:
    project = await projects.active_project(session, scope, project_id)
    content_type = mime_type_for(filename)
    if size_bytes > max_bytes:
        raise FileTooLargeError
    if new_document:
        # A newer edition of a Document doesn't add one; confirming it checks the Document.
        await _check_quota(session, project)
    upload_id = uuid.uuid4()
    object_key = f"{projects.storage_prefix(scope.organisation_id, project.id)}{upload_id}"
    pending = {"name": filename, "mime_type": content_type, "object_key": object_key}
    await redis.set(
        _PENDING.format(f"{project.id}:{upload_id}"), json.dumps(pending), ex=ttl_seconds
    )
    url = store.presign_put(object_key, content_type=content_type, expires_in=ttl_seconds)
    return PendingUpload(
        upload_id=upload_id,
        url=url,
        content_type=content_type,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )


@dataclass(frozen=True)
class _Received:
    """A confirmed upload's file, read back from the object store."""

    name: str
    mime_type: str
    object_key: str
    size_bytes: int
    content_hash: str
    # The pending upload's Redis key, deleted once the Document is committed.
    pending_key: str


async def _receive(
    session: AsyncSession,
    redis: Redis,
    store: ObjectStore,
    project: Project,
    *,
    upload_id: uuid.UUID,
    content_hash: str | None,
    max_bytes: int,
) -> _Received:
    """Reads the pending upload's file, checks its real size and its content hash, and refuses
    a duplicate of a Document (or a staged edition) already in the Project. The caller holds
    the Project's lock, so two confirmations of the same file can't both pass the duplicate
    check."""
    key = _PENDING.format(f"{project.id}:{upload_id}")
    raw = await redis.get(key)
    if raw is None:
        raise UploadNotFoundError
    pending = json.loads(raw)
    try:
        data = await store.get(pending["object_key"])
    except ObjectNotFoundError:
        raise FileNotUploadedError from None
    if len(data) > max_bytes:
        # The presigned URL can't bound the size, so a file larger than it claimed is removed.
        await redis.delete(key)
        await store.delete(pending["object_key"])
        raise FileTooLargeError
    digest = hashlib.sha256(data).hexdigest()
    if content_hash is not None and content_hash.lower() != digest:
        raise ContentHashMismatchError
    duplicate = await _document_with_hash(session, project.id, digest)
    if duplicate is not None:
        # Nothing will refer to the refused copy, so neither the upload nor its file is kept.
        await redis.delete(key)
        await store.delete(pending["object_key"])
        raise DuplicateDocumentError(duplicate)
    return _Received(
        name=pending["name"],
        mime_type=pending["mime_type"],
        object_key=pending["object_key"],
        size_bytes=len(data),
        content_hash=digest,
        pending_key=key,
    )


async def _document_with_hash(
    session: AsyncSession, project_id: uuid.UUID, content_hash: str
) -> Document | None:
    """The Project's Document whose current edition, or whose staged edition still being
    ingested, has this content hash. A Failed edition is not a Duplicate, so its file can be
    uploaded again, as a new Document or as the next edition."""
    staged = select(StagedEdition.document_id).where(
        StagedEdition.project_id == project_id,
        StagedEdition.content_hash == content_hash,
        StagedEdition.status != DocumentStatus.FAILED,
    )
    return await session.scalar(
        select(Document)
        .where(
            Document.project_id == project_id,
            or_(
                and_(
                    Document.content_hash == content_hash,
                    Document.status != DocumentStatus.FAILED,
                ),
                Document.id.in_(staged),
            ),
        )
        .order_by(Document.created_at)
        .limit(1)
    )


async def confirm_upload(
    session: AsyncSession,
    redis: Redis,
    store: ObjectStore,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    *,
    upload_id: uuid.UUID,
    content_hash: str | None,
    max_bytes: int,
) -> Document:
    """Creates the Document as Queued; the caller enqueues ingestion after this commits. The
    Project stays locked until then, so concurrent confirms can't overfill its quota."""
    project = await projects.active_project(session, scope, project_id, lock=True)
    await _check_quota(session, project)
    received = await _receive(
        session,
        redis,
        store,
        project,
        upload_id=upload_id,
        content_hash=content_hash,
        max_bytes=max_bytes,
    )
    document = Document(
        organisation_id=scope.organisation_id,
        project_id=project.id,
        name=received.name,
        mime_type=received.mime_type,
        size_bytes=received.size_bytes,
        content_hash=received.content_hash,
        object_key=received.object_key,
        status=DocumentStatus.QUEUED,
        attempt_count=0,
        edition=1,
    )
    session.add(document)
    await session.commit()
    await redis.delete(received.pending_key)
    await session.refresh(document)
    return document


async def _check_quota(session: AsyncSession, project: Project) -> None:
    if await documents_counted(session, project.id) >= project.document_quota:
        raise QuotaReachedError(project.document_quota)


@dataclass(frozen=True)
class UploadLimits:
    max_upload_bytes: int
    document_quota: int
    documents_counted: int


async def upload_limits(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, *, max_bytes: int
) -> UploadLimits:
    project = await projects.get_project(session, scope, project_id)
    return UploadLimits(
        max_upload_bytes=max_bytes,
        document_quota=project.document_quota,
        documents_counted=await documents_counted(session, project.id),
    )


async def set_document_quota(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, *, quota: int
) -> None:
    """Sets how many Documents the Project may hold. Lowering it below what the Project holds
    keeps those Documents; only new uploads, and Documents processed later, are refused."""
    project = await projects.get_project(session, scope, project_id, lock=True)
    project.document_quota = quota
    await session.commit()


async def retry_document(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, document_id: uuid.UUID
) -> tuple[Document, StagedEdition | None]:
    """Puts what failed back to Queued, for the caller to enqueue ingestion once this commits:
    a Failed Document, or, when the Document is Ready and its newer edition is what failed,
    that edition. With nothing Failed, a Ready Document is processed again with the Project's
    current settings (such as OCR); its Chunks keep serving until the new ones replace them.
    Refused while the Document or a newer edition is still being processed, and when a Failed
    file's content has since been uploaded again (a Failed edition is not a Duplicate, so that
    is allowed). Returns the Document and its staged edition, if any."""
    project = await projects.active_project(session, scope, project_id, lock=True)
    document = await session.scalar(
        select(Document)
        .where(Document.id == document_id, Document.project_id == project.id)
        .with_for_update()
    )
    if document is None:
        raise DocumentNotFoundError
    staged = await session.get(StagedEdition, document.id, with_for_update=True)
    if document.status not in FINAL_STATUSES or (
        staged is not None and staged.status not in FINAL_STATUSES
    ):
        raise DocumentBusyError
    retried: Document | StagedEdition = document
    if staged is not None and document.status != DocumentStatus.FAILED:
        retried = staged
    if retried.status == DocumentStatus.FAILED:
        duplicate = await _document_with_hash(session, project.id, retried.content_hash)
        if duplicate is not None and duplicate.id != document.id:
            raise DuplicateDocumentError(duplicate)
    retried.status = DocumentStatus.QUEUED
    retried.error_message = None
    retried.error_category = None
    retried.updated_at = func.now()
    await session.commit()
    await session.refresh(document)
    if staged is not None:
        await session.refresh(staged)
    return document, staged


@dataclass(frozen=True)
class ChunkCounts:
    """How many Chunks a Document's current edition has, and how many of them the ingestion
    Guardrail scan flagged."""

    total: int = 0
    flagged: int = 0


def _active_model(project_id: Any) -> ScalarSelect[str]:
    """The Project's active Embedding Model, as a subquery."""
    return (
        select(Project.embedding_model_id)
        .where(Project.id == project_id)
        .correlate_except(Project)
        .scalar_subquery()
    )


def _chunk_counts() -> tuple[ScalarSelect[int], ScalarSelect[int]]:
    """Correlated subqueries counting the current edition's Chunks, and its flagged ones, for
    a query over ``Document``. Only the Project's active Embedding Model's rows count: a
    re-embed writes a second row per Chunk for the pending model."""
    current = (
        Chunk.document_id == Document.id,
        Chunk.edition == Document.edition,
        Chunk.embedding_model_id == _active_model(Document.project_id),
    )
    total = select(func.count()).where(*current).scalar_subquery()
    flagged = (
        select(func.count()).where(*current, Chunk.guardrail_label.is_not(None)).scalar_subquery()
    )
    return total, flagged


@dataclass(frozen=True)
class DocumentSummary:
    document: Document
    chunks: ChunkCounts
    # A newer edition being ingested, or one that failed; ``None`` when there is neither.
    replacement: StagedEdition | None


@dataclass(frozen=True)
class DocumentFilter:
    """Narrows the Document list. Every given condition must hold."""

    # Part of the name, ignoring case.
    name: str | None = None
    # Any of these statuses.
    statuses: Sequence[DocumentStatus] = ()
    # Every one of these Tags.
    tag_ids: Sequence[uuid.UUID] = ()


NO_FILTER = DocumentFilter()


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_documents(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    where: DocumentFilter = NO_FILTER,
) -> list[DocumentSummary]:
    """The Project's Documents, newest first, with their Chunk counts and replacements."""
    project = await projects.get_project(session, scope, project_id)
    total, flagged = _chunk_counts()
    query = (
        select(Document, total, flagged, StagedEdition)
        .outerjoin(StagedEdition, StagedEdition.document_id == Document.id)
        .where(Document.project_id == project.id)
    )
    if where.name:
        query = query.where(Document.name.ilike(f"%{_escape_like(where.name)}%", escape="\\"))
    if where.statuses:
        query = query.where(Document.status.in_([str(s) for s in where.statuses]))
    for tag_id in set(where.tag_ids):
        query = query.where(
            select(DocumentTag.tag_id)
            .where(DocumentTag.document_id == Document.id, DocumentTag.tag_id == tag_id)
            .exists()
        )
    rows = await session.execute(query.order_by(Document.created_at.desc(), Document.name))
    return [
        DocumentSummary(document, ChunkCounts(count, flagged_count), staged)
        for document, count, flagged_count, staged in rows
    ]


async def get_document(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, document_id: uuid.UUID
) -> Document:
    project = await projects.get_project(session, scope, project_id)
    document = await session.scalar(
        select(Document).where(Document.id == document_id, Document.project_id == project.id)
    )
    if document is None:
        raise DocumentNotFoundError
    return document


@dataclass(frozen=True)
class OpenedDocument:
    document: Document
    chunks: ChunkCounts
    # The converted markdown; ``None`` until the Document has been converted.
    markdown: str | None
    # A newer edition being ingested, if any.
    replacement: StagedEdition | None


async def open_document(
    session: AsyncSession,
    store: ObjectStore,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
) -> OpenedDocument:
    """One Document, with its Chunk count and the markdown Docling converted it to."""
    document = await get_document(session, scope, project_id, document_id)
    counts = await chunk_counts(session, document)
    markdown = None
    if document.markdown_key is not None:
        markdown = (await store.get(document.markdown_key)).decode()
    replacement = await session.get(StagedEdition, document.id)
    return OpenedDocument(document, counts, markdown, replacement)


@dataclass(frozen=True)
class ChunkPage:
    chunks: list[Chunk]
    # How many Chunks the current edition has in all.
    total: int


async def list_chunks(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    offset: int,
    limit: int,
) -> ChunkPage:
    """A page of the current edition's Chunks, in Document order."""
    document = await get_document(session, scope, project_id, document_id)
    current = (
        Chunk.document_id == document.id,
        Chunk.edition == document.edition,
        Chunk.embedding_model_id == _active_model(document.project_id),
    )
    total = await session.scalar(select(func.count()).where(*current))
    chunks = await session.scalars(
        select(Chunk).where(*current).order_by(Chunk.ordinal).offset(offset).limit(limit)
    )
    return ChunkPage(list(chunks), total or 0)


async def delete_document(
    session: AsyncSession,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    now: datetime,
) -> list[str]:
    """Deletes the Document and its Chunks in one transaction, so retrieval stops at once, and
    records ``document.deleted``. Returns its stored objects (originals and converted markdown,
    of the current and any staged edition) for the caller to schedule deletion of."""
    project = await projects.active_project(session, scope, project_id)
    document = await session.scalar(
        select(Document)
        .where(Document.id == document_id, Document.project_id == project.id)
        .with_for_update()
    )
    if document is None:
        raise DocumentNotFoundError
    staged = await session.get(StagedEdition, document.id, with_for_update=True)
    keys = stored_keys(document.object_key)
    if staged is not None:
        keys += stored_keys(staged.object_key)
    await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
    await audit.record(
        session,
        organisation_id=scope.organisation_id,
        actor_id=scope.member_id,
        action="document.deleted",
        target=audit.AuditTarget("document", document.id),
        before={
            "project_id": str(project.id),
            "name": document.name,
            "content_hash": document.content_hash,
        },
        occurred_at=now,
    )
    await session.delete(document)
    await session.commit()
    return keys


@dataclass(frozen=True)
class Replacement:
    document: Document
    staged: StagedEdition
    # A previous failed replacement's stored objects, which nothing refers to any more.
    discarded: list[str]


async def replace_document(
    session: AsyncSession,
    redis: Redis,
    store: ObjectStore,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    upload_id: uuid.UUID,
    content_hash: str | None,
    max_bytes: int,
) -> Replacement:
    """Stages the uploaded file as the Document's next edition, Queued; the caller enqueues
    ingestion after this commits. The current edition keeps serving until the staged one is
    Ready. Refused while the Document or an earlier replacement is still being processed; a
    failed replacement is overwritten."""
    project = await projects.active_project(session, scope, project_id, lock=True)
    document = await session.scalar(
        select(Document)
        .where(Document.id == document_id, Document.project_id == project.id)
        .with_for_update()
    )
    if document is None:
        raise DocumentNotFoundError
    staged = await session.get(StagedEdition, document.id, with_for_update=True)
    if document.status not in FINAL_STATUSES or (
        staged is not None and staged.status != DocumentStatus.FAILED
    ):
        raise DocumentBusyError
    received = await _receive(
        session,
        redis,
        store,
        project,
        upload_id=upload_id,
        content_hash=content_hash,
        max_bytes=max_bytes,
    )
    discarded: list[str] = []
    if staged is None:
        staged = StagedEdition(
            document_id=document.id, organisation_id=document.organisation_id, project_id=project.id
        )
        session.add(staged)
    else:
        discarded = stored_keys(staged.object_key)
    staged.edition = document.edition + 1
    staged.name = received.name
    staged.mime_type = received.mime_type
    staged.size_bytes = received.size_bytes
    staged.content_hash = received.content_hash
    staged.object_key = received.object_key
    staged.status = DocumentStatus.QUEUED
    staged.error_message = None
    staged.error_category = None
    staged.attempt_count = 0
    staged.updated_at = func.now()
    await session.commit()
    await redis.delete(received.pending_key)
    await session.refresh(staged)
    return Replacement(document, staged, discarded)


async def chunk_counts(session: AsyncSession, document: Document) -> ChunkCounts:
    """How many Chunks the Document's current edition has, and how many are flagged."""
    total, flagged = _chunk_counts()
    row = (await session.execute(select(total, flagged).where(Document.id == document.id))).one()
    return ChunkCounts(row[0], row[1])
