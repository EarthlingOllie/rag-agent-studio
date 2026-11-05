"""Document routes: the upload limits, start an upload (presigned PUT), confirm it, list
Documents and their statuses (polled by the Studio), read one Document's Chunks, and retry a
Failed Document. Any Member may use them, except setting the Document quota (Owners)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, StringConstraints
from redis.asyncio import Redis

from app.auth.api import Db, ErrorResponse
from app.core.clock import Clock, get_clock
from app.core.settings import Settings
from app.documents import limits, service
from app.documents.models import (
    MIME_MAX,
    NAME_MAX,
    Chunk,
    Document,
    DocumentStatus,
    FailureCategory,
)
from app.documents.ports import IngestionPorts
from app.documents.tasks import enqueue_ingestion
from app.projects.api import PROJECT_ARCHIVED
from app.projects.service import ProjectArchivedError, ProjectNotFoundError
from app.storage.port import ObjectStore
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY, OwnerScope, Scope

router = APIRouter(prefix=ORGANISATION_PREFIX + "/projects/{project_id}", tags=["documents"])

UNSUPPORTED_TYPE = (
    "This file type isn't supported. Upload a PDF, DOCX, PPTX, HTML, Markdown or TXT file."
)
UPLOAD_NOT_FOUND = "This upload wasn't found or has expired. Start the upload again."
FILE_NOT_UPLOADED = "The file hasn't reached storage yet. Upload it, then confirm."
HASH_MISMATCH = "The uploaded file doesn't match its content hash. Upload it again."
NOT_FAILED = "Only a Failed Document can be retried."
QUOTA_REACHED = "This Project has reached its Document quota."
QUOTA_MAX = 100_000

ClockDep = Annotated[Clock, Depends(get_clock)]


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


def _store(request: Request) -> ObjectStore:
    ports: IngestionPorts = request.app.state.ingestion
    return ports.object_store


SettingsDep = Annotated[Settings, Depends(_settings)]
RedisDep = Annotated[Redis, Depends(_redis)]
StoreDep = Annotated[ObjectStore, Depends(_store)]


def _errors(*codes: tuple[int, str]) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ErrorResponse, "description": text} for code, text in codes}


_NOT_FOUND = (404, NOT_FOUND)
_ARCHIVED = (409, PROJECT_ARCHIVED)


class StartUploadRequest(BaseModel):
    filename: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX)
    ]
    size_bytes: int = Field(ge=0)


class StartUploadResponse(BaseModel):
    upload_id: uuid.UUID
    # PUT the file's bytes here, with the given Content-Type header, before ``expires_at``.
    url: str
    method: str = "PUT"
    content_type: Annotated[str, StringConstraints(max_length=MIME_MAX)]
    expires_at: datetime


class ConfirmUploadRequest(BaseModel):
    upload_id: uuid.UUID
    # The SHA-256 of the file, hex, if the browser computed it; it is checked when given.
    content_hash: Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{64}$")] | None = None


class UploadLimitsOut(BaseModel):
    # File extensions a Document can be uploaded from.
    accepted_extensions: list[str]
    # The largest file that can be uploaded, in bytes.
    max_upload_bytes: int
    # The most Documents the Project may hold, not counting Failed ones.
    document_quota: int
    # The Documents that count towards the quota now.
    documents_counted: int


class SetDocumentQuotaRequest(BaseModel):
    document_quota: int = Field(ge=1, le=QUOTA_MAX)


class DocumentOut(BaseModel):
    id: uuid.UUID
    name: str
    mime_type: str
    size_bytes: int
    # SHA-256 of the uploaded file, hex.
    content_hash: str
    status: DocumentStatus
    # Why processing failed, when it did; or, while Queued, why it is being retried.
    error_message: str | None
    # What kind of failure it was, while Failed.
    error_category: FailureCategory | None
    # How many times processing has started, automatic retries included.
    attempt_count: int
    edition: int
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class DocumentStatusOut(BaseModel):
    id: uuid.UUID
    status: DocumentStatus
    error_message: str | None
    error_category: FailureCategory | None
    attempt_count: int
    chunk_count: int


class ChunkOut(BaseModel):
    id: uuid.UUID
    ordinal: int
    text: str
    heading_path: list[str]
    page_start: int | None
    page_end: int | None
    embedding_model_id: str


def _category(document: Document) -> FailureCategory | None:
    return None if document.error_category is None else FailureCategory(document.error_category)


def _document_out(document: Document, chunk_count: int) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        name=document.name,
        mime_type=document.mime_type,
        size_bytes=document.size_bytes,
        content_hash=document.content_hash,
        status=DocumentStatus(document.status),
        error_message=document.error_message,
        error_category=_category(document),
        attempt_count=document.attempt_count,
        edition=document.edition,
        chunk_count=chunk_count,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _chunk_out(chunk: Chunk) -> ChunkOut:
    return ChunkOut(
        id=chunk.id,
        ordinal=chunk.ordinal,
        text=chunk.text,
        heading_path=chunk.heading_path,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        embedding_model_id=chunk.embedding_model_id,
    )


def _too_large(settings: Settings) -> HTTPException:
    return HTTPException(
        status.HTTP_413_CONTENT_TOO_LARGE, limits.size_limit_message(settings.max_upload_bytes)
    )


def _quota_reached(full: service.QuotaReachedError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, limits.quota_refusal_message(full.quota))


@router.get("/uploads/limits", operation_id="getUploadLimits", responses=_errors(_NOT_FOUND))
async def get_upload_limits(
    project_id: uuid.UUID, scope: Scope, db: Db, settings: SettingsDep
) -> UploadLimitsOut:
    """What an upload must satisfy: its type, its size, and room in the Document quota. The
    Studio checks files against these before uploading them."""
    try:
        found = await service.upload_limits(
            db, scope, project_id, max_bytes=settings.max_upload_bytes
        )
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return _limits_out(found)


def _limits_out(found: service.UploadLimits) -> UploadLimitsOut:
    return UploadLimitsOut(
        accepted_extensions=list(limits.SUPPORTED_TYPES),
        max_upload_bytes=found.max_upload_bytes,
        document_quota=found.document_quota,
        documents_counted=found.documents_counted,
    )


@router.put(
    "/document-quota",
    operation_id="setDocumentQuota",
    responses=_errors(_NOT_FOUND, (403, OWNERS_ONLY)),
)
async def set_document_quota(
    project_id: uuid.UUID,
    body: SetDocumentQuotaRequest,
    scope: OwnerScope,
    db: Db,
    settings: SettingsDep,
) -> UploadLimitsOut:
    """Sets how many Documents the Project may hold, not counting Failed ones (Owners only).
    Documents it already holds are kept when the quota is lowered."""
    try:
        await service.set_document_quota(db, scope, project_id, quota=body.document_quota)
        found = await service.upload_limits(
            db, scope, project_id, max_bytes=settings.max_upload_bytes
        )
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return _limits_out(found)


@router.post(
    "/uploads",
    status_code=status.HTTP_201_CREATED,
    operation_id="startDocumentUpload",
    responses=_errors(
        _NOT_FOUND,
        _ARCHIVED,
        (409, QUOTA_REACHED),
        (413, "The file is larger than the upload limit."),
        (415, UNSUPPORTED_TYPE),
    ),
)
async def start_upload(
    project_id: uuid.UUID,
    body: StartUploadRequest,
    scope: Scope,
    db: Db,
    redis: RedisDep,
    store: StoreDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> StartUploadResponse:
    """Checks the file type and size, and that the Project's Document quota has room, then
    answers with a presigned URL to PUT the file to."""
    try:
        pending = await service.start_upload(
            db,
            redis,
            store,
            scope,
            project_id,
            filename=body.filename,
            size_bytes=body.size_bytes,
            max_bytes=settings.max_upload_bytes,
            ttl_seconds=settings.upload_url_ttl_seconds,
            now=clock.now(),
        )
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    except limits.UnsupportedFileTypeError:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, UNSUPPORTED_TYPE) from None
    except service.FileTooLargeError:
        raise _too_large(settings) from None
    except service.QuotaReachedError as full:
        raise _quota_reached(full) from None
    return StartUploadResponse(
        upload_id=pending.upload_id,
        url=pending.url,
        content_type=pending.content_type,
        expires_at=pending.expires_at,
    )


@router.post(
    "/documents",
    status_code=status.HTTP_201_CREATED,
    operation_id="confirmDocumentUpload",
    responses=_errors(
        _NOT_FOUND,
        _ARCHIVED,
        (409, f"{FILE_NOT_UPLOADED} / {UPLOAD_NOT_FOUND} / {QUOTA_REACHED}"),
        (413, "The file is larger than the upload limit."),
        (422, HASH_MISMATCH),
    ),
)
async def confirm_upload(
    project_id: uuid.UUID,
    body: ConfirmUploadRequest,
    scope: Scope,
    db: Db,
    redis: RedisDep,
    store: StoreDep,
    settings: SettingsDep,
) -> DocumentOut:
    """Records the uploaded file's content hash, creates the Document as Queued and starts
    ingestion. The Document then moves to Processing and Ready (or Failed)."""
    try:
        document = await service.confirm_upload(
            db,
            redis,
            store,
            scope,
            project_id,
            upload_id=body.upload_id,
            content_hash=body.content_hash,
            max_bytes=settings.max_upload_bytes,
        )
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    except service.UploadNotFoundError:
        raise HTTPException(status.HTTP_409_CONFLICT, UPLOAD_NOT_FOUND) from None
    except service.FileNotUploadedError:
        raise HTTPException(status.HTTP_409_CONFLICT, FILE_NOT_UPLOADED) from None
    except service.ContentHashMismatchError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, HASH_MISMATCH) from None
    except service.FileTooLargeError:
        raise _too_large(settings) from None
    except service.QuotaReachedError as full:
        raise _quota_reached(full) from None
    queued = _document_out(document, chunk_count=0)
    await enqueue_ingestion(document.id)
    return queued


@router.get("/documents", operation_id="listDocuments", responses=_errors(_NOT_FOUND))
async def list_documents(project_id: uuid.UUID, scope: Scope, db: Db) -> list[DocumentOut]:
    """The Project's Documents, newest first."""
    try:
        summaries = await service.list_documents(db, scope, project_id)
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return [_document_out(s.document, s.chunk_count) for s in summaries]


@router.get(
    "/documents/statuses", operation_id="listDocumentStatuses", responses=_errors(_NOT_FOUND)
)
async def list_document_statuses(
    project_id: uuid.UUID, scope: Scope, db: Db
) -> list[DocumentStatusOut]:
    """Just each Document's status: the Studio polls this while any Document isn't Ready or
    Failed."""
    try:
        summaries = await service.list_documents(db, scope, project_id)
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return [
        DocumentStatusOut(
            id=s.document.id,
            status=DocumentStatus(s.document.status),
            error_message=s.document.error_message,
            error_category=_category(s.document),
            attempt_count=s.document.attempt_count,
            chunk_count=s.chunk_count,
        )
        for s in summaries
    ]


@router.get(
    "/documents/{document_id}/chunks", operation_id="listChunks", responses=_errors(_NOT_FOUND)
)
async def list_chunks(
    project_id: uuid.UUID, document_id: uuid.UUID, scope: Scope, db: Db
) -> list[ChunkOut]:
    """The Document's Chunks in order, with heading path and pages."""
    try:
        chunks = await service.list_chunks(db, scope, project_id, document_id)
    except (ProjectNotFoundError, service.DocumentNotFoundError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return [_chunk_out(chunk) for chunk in chunks]


@router.post(
    "/documents/{document_id}/retry",
    operation_id="retryDocument",
    responses=_errors(_NOT_FOUND, (409, f"{NOT_FAILED} / {PROJECT_ARCHIVED}")),
)
async def retry_document(
    project_id: uuid.UUID, document_id: uuid.UUID, scope: Scope, db: Db
) -> DocumentOut:
    """Puts a Failed Document back to Queued and processes it again, from the stored file."""
    try:
        document = await service.retry_document(db, scope, project_id, document_id)
    except (ProjectNotFoundError, service.DocumentNotFoundError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    except service.DocumentNotFailedError:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_FAILED) from None
    queued = _document_out(document, chunk_count=0)
    await enqueue_ingestion(document.id)
    return queued
