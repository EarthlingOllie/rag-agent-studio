"""Document routes: start an upload (presigned PUT), confirm it, list Documents and their
statuses (polled by the Studio), read one Document and its Chunks. Any Member may use them."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, StringConstraints
from redis.asyncio import Redis

from app.auth.api import Db, ErrorResponse
from app.core.clock import Clock, get_clock
from app.core.settings import Settings
from app.documents import service
from app.documents.models import MIME_MAX, NAME_MAX, Chunk, Document, DocumentStatus
from app.documents.ports import IngestionPorts
from app.documents.tasks import enqueue_ingestion
from app.projects.api import PROJECT_ARCHIVED
from app.projects.service import ProjectArchivedError, ProjectNotFoundError
from app.storage.port import ObjectStore
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, Scope

router = APIRouter(prefix=ORGANISATION_PREFIX + "/projects/{project_id}", tags=["documents"])

UNSUPPORTED_TYPE = (
    "This file type isn't supported. Upload a PDF, DOCX, PPTX, HTML, Markdown or TXT file."
)
UPLOAD_NOT_FOUND = "This upload wasn't found or has expired. Start the upload again."
FILE_NOT_UPLOADED = "The file hasn't reached storage yet. Upload it, then confirm."
HASH_MISMATCH = "The uploaded file doesn't match its content hash. Upload it again."
DOCUMENT_IN_PROGRESS = (
    "This Document is still being processed. Retry it once it is Ready or Failed."
)

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


class DocumentOut(BaseModel):
    id: uuid.UUID
    name: str
    mime_type: str
    size_bytes: int
    # SHA-256 of the uploaded file, hex.
    content_hash: str
    status: DocumentStatus
    # Why processing failed, when it did.
    error_message: str | None
    edition: int
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class DocumentStatusOut(BaseModel):
    id: uuid.UUID
    status: DocumentStatus
    error_message: str | None
    chunk_count: int


class ChunkOut(BaseModel):
    id: uuid.UUID
    ordinal: int
    text: str
    heading_path: list[str]
    page_start: int | None
    page_end: int | None
    embedding_model_id: str


def _document_out(document: Document, chunk_count: int) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        name=document.name,
        mime_type=document.mime_type,
        size_bytes=document.size_bytes,
        content_hash=document.content_hash,
        status=DocumentStatus(document.status),
        error_message=document.error_message,
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


@router.post(
    "/uploads",
    status_code=status.HTTP_201_CREATED,
    operation_id="startDocumentUpload",
    responses=_errors(
        _NOT_FOUND,
        _ARCHIVED,
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
    """Checks the file type and size, then answers with a presigned URL to PUT the file to."""
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
    except service.UnsupportedFileTypeError:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, UNSUPPORTED_TYPE) from None
    except service.FileTooLargeError:
        megabytes = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"This file is larger than the {megabytes} MB upload limit.",
        ) from None
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
        (409, f"{FILE_NOT_UPLOADED} / {UPLOAD_NOT_FOUND}"),
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
    queued = _document_out(document, chunk_count=0)
    await enqueue_ingestion(document.id)
    return queued


@router.post(
    "/documents/{document_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="retryDocument",
    responses=_errors(_NOT_FOUND, (409, f"{DOCUMENT_IN_PROGRESS} / {PROJECT_ARCHIVED}")),
)
async def retry_document(
    project_id: uuid.UUID, document_id: uuid.UUID, scope: Scope, db: Db
) -> DocumentOut:
    """Processes a Ready or Failed Document again, with the Project's current settings (such as
    OCR). It is Queued, then moves to Processing and Ready (or Failed); its Chunks keep serving
    until the new ones replace them."""
    try:
        summary = await service.retry(db, scope, project_id, document_id)
    except (ProjectNotFoundError, service.DocumentNotFoundError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    except service.DocumentInProgressError:
        raise HTTPException(status.HTTP_409_CONFLICT, DOCUMENT_IN_PROGRESS) from None
    queued = _document_out(summary.document, summary.chunk_count)
    await enqueue_ingestion(summary.document.id)
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
