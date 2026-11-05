"""Uploading Documents: presign, direct upload, confirm. And reading Documents and Chunks.

1. ``start_upload`` checks the file type and size, and answers with a presigned PUT URL. The
   pending upload is remembered in Redis until the URL expires.
2. The browser PUTs the file straight to the object store.
3. ``confirm_upload`` reads the stored file, computes its SHA-256 content hash (checking it
   against the one the browser sent, if any), creates the Document as Queued, and enqueues
   ingestion.

Every function takes the Organisation scope and finds the Project only inside it; uploads go
through ``active_project``, so an archived Project takes none.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PurePath

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Chunk, Document, DocumentStatus
from app.projects import service as projects
from app.storage.port import ObjectNotFoundError, ObjectStore
from app.tenancy.repository import OrganisationScope

# The file types a Document can be uploaded from, by extension, with the MIME type stored.
SUPPORTED_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".html": "text/html",
    ".htm": "text/html",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
}

_PENDING = "document-upload:{}"


class UnsupportedFileTypeError(Exception):
    """The file's extension isn't one a Document can be made from."""


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


@dataclass(frozen=True)
class PendingUpload:
    upload_id: uuid.UUID
    url: str
    content_type: str
    expires_at: datetime


def mime_type_for(filename: str) -> str:
    try:
        return SUPPORTED_TYPES[PurePath(filename).suffix.lower()]
    except KeyError:
        raise UnsupportedFileTypeError from None


async def start_upload(
    session: AsyncSession,
    redis: Redis,
    store: ObjectStore,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    *,
    filename: str,
    size_bytes: int,
    max_bytes: int,
    ttl_seconds: int,
    now: datetime,
) -> PendingUpload:
    project = await projects.active_project(session, scope, project_id)
    content_type = mime_type_for(filename)
    if size_bytes > max_bytes:
        raise FileTooLargeError
    upload_id = uuid.uuid4()
    object_key = f"organisations/{scope.organisation_id}/projects/{project.id}/{upload_id}"
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


async def confirm_upload(
    session: AsyncSession,
    redis: Redis,
    store: ObjectStore,
    scope: OrganisationScope,
    project_id: uuid.UUID,
    *,
    upload_id: uuid.UUID,
    content_hash: str | None,
) -> Document:
    """Creates the Document as Queued; the caller enqueues ingestion after this commits."""
    project = await projects.active_project(session, scope, project_id)
    key = _PENDING.format(f"{project.id}:{upload_id}")
    raw = await redis.get(key)
    if raw is None:
        raise UploadNotFoundError
    pending = json.loads(raw)
    try:
        data = await store.get(pending["object_key"])
    except ObjectNotFoundError:
        raise FileNotUploadedError from None
    digest = hashlib.sha256(data).hexdigest()
    if content_hash is not None and content_hash.lower() != digest:
        raise ContentHashMismatchError
    document = Document(
        organisation_id=scope.organisation_id,
        project_id=project.id,
        name=pending["name"],
        mime_type=pending["mime_type"],
        size_bytes=len(data),
        content_hash=digest,
        object_key=pending["object_key"],
        status=DocumentStatus.QUEUED,
        attempt_count=0,
        edition=1,
    )
    session.add(document)
    await session.commit()
    await redis.delete(key)
    await session.refresh(document)
    return document


@dataclass(frozen=True)
class DocumentSummary:
    document: Document
    chunk_count: int


async def list_documents(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID
) -> list[DocumentSummary]:
    """The Project's Documents, newest first, with their Chunk counts."""
    project = await projects.get_project(session, scope, project_id)
    chunk_count = (
        select(func.count())
        .where(Chunk.document_id == Document.id, Chunk.edition == Document.edition)
        .scalar_subquery()
    )
    rows = await session.execute(
        select(Document, chunk_count)
        .where(Document.project_id == project.id)
        .order_by(Document.created_at.desc(), Document.name)
    )
    return [DocumentSummary(document, count) for document, count in rows]


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


async def list_chunks(
    session: AsyncSession, scope: OrganisationScope, project_id: uuid.UUID, document_id: uuid.UUID
) -> list[Chunk]:
    """The current edition's Chunks, in Document order."""
    document = await get_document(session, scope, project_id, document_id)
    chunks = await session.scalars(
        select(Chunk)
        .where(Chunk.document_id == document.id, Chunk.edition == document.edition)
        .order_by(Chunk.ordinal)
    )
    return list(chunks)
