"""Document routes: the upload limits, start an upload (presigned PUT), confirm it, list
Documents and their statuses (polled by the Studio), read one Document's Chunks, delete a
Document, replace its edition, and retry a Failed Document. Any Member may use them, except
setting the Document quota (Owners)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
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
    StagedEdition,
)
from app.documents.ports import IngestionPorts
from app.documents.tasks import enqueue_ingestion, enqueue_object_deletion
from app.projects.api import PROJECT_ARCHIVED
from app.projects.service import ProjectArchivedError, ProjectNotFoundError
from app.storage.port import ObjectStore
from app.tags.api import TagRef, tag_ref
from app.tags.models import Tag
from app.tags.service import tags_of
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY, OwnerScope, Scope

router = APIRouter(prefix=ORGANISATION_PREFIX + "/projects/{project_id}", tags=["documents"])

UNSUPPORTED_TYPE = (
    "This file type isn't supported. Upload a PDF, DOCX, PPTX, HTML, Markdown or TXT file."
)
UPLOAD_NOT_FOUND = "This upload wasn't found or has expired. Start the upload again."
FILE_NOT_UPLOADED = "The file hasn't reached storage yet. Upload it, then confirm."
HASH_MISMATCH = "The uploaded file doesn't match its content hash. Upload it again."
QUOTA_REACHED = "This Project has reached its Document quota."
QUOTA_MAX = 100_000
DOCUMENT_BUSY = "This Document is still being processed. Try again once it is Ready or Failed."


def duplicate_message(existing_name: str) -> str:
    return f"This file is already in the Project as {existing_name}."


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


class UploadConflictResponse(BaseModel):
    detail: str
    # When the file is a duplicate: the Document that already has the same content.
    document_id: uuid.UUID | None = None
    document_name: str | None = None


_DUPLICATE = "The file is a duplicate of a Document in the Project (``document_id`` names it)."
_UPLOAD_CONFLICT: dict[str, Any] = {
    "model": UploadConflictResponse,
    "description": f"{PROJECT_ARCHIVED} / {FILE_NOT_UPLOADED} / {UPLOAD_NOT_FOUND} / {_DUPLICATE}",
}


def _duplicate(error: service.DuplicateDocumentError) -> JSONResponse:
    content = UploadConflictResponse(
        detail=duplicate_message(error.existing.name),
        document_id=error.existing.id,
        document_name=error.existing.name,
    )
    return JSONResponse(content.model_dump(mode="json"), status_code=status.HTTP_409_CONFLICT)


class StartUploadRequest(BaseModel):
    filename: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX)
    ]
    size_bytes: int = Field(ge=0)
    # The Document this file will be a newer edition of, if it is one. A new edition doesn't add
    # a Document, so the Document quota isn't checked for it.
    replacing_document_id: uuid.UUID | None = None


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


class ReplacementOut(BaseModel):
    """A newer edition uploaded to replace the Document. While it is Queued or Processing the
    current edition keeps serving; when it is Ready it becomes the Document's edition. A Failed
    one leaves the Document as it was."""

    edition: int
    name: str
    status: DocumentStatus
    error_message: str | None
    # What kind of failure it was, while Failed.
    error_category: FailureCategory | None


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
    # How many of its Chunks the ingestion Guardrail scan flagged as instructions aimed at an AI.
    flagged_chunk_count: int
    # The Document's Tags, by name.
    tags: list[TagRef]
    created_at: datetime
    updated_at: datetime
    replacement: ReplacementOut | None


class DocumentDetailOut(DocumentOut):
    # The markdown Docling converted the file to; null until the Document has been converted.
    markdown: str | None


class DocumentStatusOut(BaseModel):
    id: uuid.UUID
    status: DocumentStatus
    error_message: str | None
    error_category: FailureCategory | None
    attempt_count: int
    chunk_count: int
    flagged_chunk_count: int
    replacement: ReplacementOut | None


class GuardrailFlagOut(BaseModel):
    """Why the ingestion Guardrail scan flagged a Chunk as instructions aimed at an AI."""

    # What the injection classifier thinks the Chunk is, such as ``prompt_injection``.
    label: str
    # How sure the classifier is, from 0 to 1.
    score: float
    # What in the Chunk looks like instructions to an AI.
    reason: str


class ChunkOut(BaseModel):
    id: uuid.UUID
    ordinal: int
    text: str
    heading_path: list[str]
    page_start: int | None
    page_end: int | None
    embedding_model_id: str
    # The ingestion Guardrail scan's flag; null when the Chunk wasn't flagged.
    flag: GuardrailFlagOut | None


def _category(failed: Document | StagedEdition) -> FailureCategory | None:
    return None if failed.error_category is None else FailureCategory(failed.error_category)


# The Chunk list's page size: the default, and the most one request may ask for.
CHUNK_PAGE_DEFAULT = 50
CHUNK_PAGE_MAX = 200


class ChunkPageOut(BaseModel):
    items: list[ChunkOut]
    # How many Chunks the Document has in all.
    total: int
    offset: int
    limit: int


def _replacement_out(staged: StagedEdition | None) -> ReplacementOut | None:
    if staged is None:
        return None
    return ReplacementOut(
        edition=staged.edition,
        name=staged.name,
        status=DocumentStatus(staged.status),
        error_message=staged.error_message,
        error_category=_category(staged),
    )


def _document_out(
    document: Document,
    chunks: service.ChunkCounts,
    tags: list[Tag],
    staged: StagedEdition | None = None,
) -> DocumentOut:
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
        chunk_count=chunks.total,
        flagged_chunk_count=chunks.flagged,
        tags=[tag_ref(tag) for tag in tags],
        created_at=document.created_at,
        updated_at=document.updated_at,
        replacement=_replacement_out(staged),
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
        flag=_flag_out(chunk),
    )


def _flag_out(chunk: Chunk) -> GuardrailFlagOut | None:
    # The three are set together or not at all (``ck_chunks_guardrail_flag_complete``).
    label, score, reason = chunk.guardrail_label, chunk.guardrail_score, chunk.guardrail_reason
    if label is None or score is None or reason is None:
        return None
    return GuardrailFlagOut(label=label, score=score, reason=reason)


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
            new_document=body.replacing_document_id is None,
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
    response_model=DocumentOut,
    responses={
        **_errors(
            _NOT_FOUND,
            (413, "The file is larger than the upload limit."),
            (422, HASH_MISMATCH),
        ),
        409: {
            **_UPLOAD_CONFLICT,
            "description": f"{_UPLOAD_CONFLICT['description']} / {QUOTA_REACHED}",
        },
    },
)
async def confirm_upload(
    project_id: uuid.UUID,
    body: ConfirmUploadRequest,
    scope: Scope,
    db: Db,
    redis: RedisDep,
    store: StoreDep,
    settings: SettingsDep,
) -> DocumentOut | JSONResponse:
    """Records the uploaded file's content hash, creates the Document as Queued and starts
    ingestion. The Document then moves to Processing and Ready (or Failed). A file whose content
    is already in the Project is refused, naming the Document that has it."""
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
    except service.DuplicateDocumentError as duplicate:
        return _duplicate(duplicate)
    queued = _document_out(document, service.ChunkCounts(), tags=[])
    await enqueue_ingestion(document.id)
    return queued


@router.get("/documents", operation_id="listDocuments", responses=_errors(_NOT_FOUND))
async def list_documents(
    project_id: uuid.UUID,
    scope: Scope,
    db: Db,
    q: Annotated[
        str | None, Query(max_length=NAME_MAX, description="Part of the name, ignoring case.")
    ] = None,
    status_: Annotated[
        list[DocumentStatus] | None,
        Query(alias="status", description="Only Documents with any of these statuses."),
    ] = None,
    tag_id: Annotated[
        list[uuid.UUID] | None, Query(description="Only Documents with every one of these Tags.")
    ] = None,
) -> list[DocumentOut]:
    """The Project's Documents, newest first, optionally searched by name and filtered by
    status and Tag."""
    where = service.DocumentFilter(
        name=q.strip() if q else None, statuses=status_ or (), tag_ids=tag_id or ()
    )
    try:
        summaries = await service.list_documents(db, scope, project_id, where)
    except ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    tags = await tags_of(db, [s.document.id for s in summaries])
    return [
        _document_out(s.document, s.chunks, tags.get(s.document.id, []), s.replacement)
        for s in summaries
    ]


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
            chunk_count=s.chunks.total,
            flagged_chunk_count=s.chunks.flagged,
            replacement=_replacement_out(s.replacement),
        )
        for s in summaries
    ]


@router.get("/documents/{document_id}", operation_id="getDocument", responses=_errors(_NOT_FOUND))
async def get_document(
    project_id: uuid.UUID, document_id: uuid.UUID, scope: Scope, db: Db, store: StoreDep
) -> DocumentDetailOut:
    """One Document, with the markdown it was converted to: the Document viewer's left pane."""
    try:
        opened = await service.open_document(db, store, scope, project_id, document_id)
    except (ProjectNotFoundError, service.DocumentNotFoundError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    tags = await tags_of(db, [opened.document.id])
    summary = _document_out(
        opened.document,
        opened.chunks,
        tags.get(opened.document.id, []),
        opened.replacement,
    )
    return DocumentDetailOut(**summary.model_dump(), markdown=opened.markdown)


@router.get(
    "/documents/{document_id}/download",
    operation_id="downloadDocument",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    response_class=RedirectResponse,
    responses={
        307: {"description": "Redirects to a short-lived presigned GET of the original file."},
        **_errors(_NOT_FOUND),
    },
)
async def download_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    scope: Scope,
    db: Db,
    store: StoreDep,
    settings: SettingsDep,
) -> RedirectResponse:
    """Downloads the original file: a redirect to a presigned GET on the object store, which
    serves it as an attachment under the Document's name. A link to this route is enough."""
    try:
        document = await service.get_document(db, scope, project_id, document_id)
    except (ProjectNotFoundError, service.DocumentNotFoundError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    url = store.presign_get(
        document.object_key,
        filename=document.name,
        content_type=document.mime_type,
        expires_in=settings.download_url_ttl_seconds,
    )
    return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get(
    "/documents/{document_id}/chunks", operation_id="listChunks", responses=_errors(_NOT_FOUND)
)
async def list_chunks(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    scope: Scope,
    db: Db,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=CHUNK_PAGE_MAX)] = CHUNK_PAGE_DEFAULT,
) -> ChunkPageOut:
    """A page of the Document's Chunks in order, with heading path and pages."""
    try:
        page = await service.list_chunks(
            db, scope, project_id, document_id, offset=offset, limit=limit
        )
    except (ProjectNotFoundError, service.DocumentNotFoundError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return ChunkPageOut(
        items=[_chunk_out(chunk) for chunk in page.chunks],
        total=page.total,
        offset=offset,
        limit=limit,
    )


CHUNK_NOT_FLAGGED = "This Chunk isn't flagged."


@router.delete(
    "/documents/{document_id}/chunks/{chunk_id}/flag",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="clearChunkFlag",
    responses=_errors(
        _NOT_FOUND, (409, f"{PROJECT_ARCHIVED} Or the Chunk isn't flagged: {CHUNK_NOT_FLAGGED}")
    ),
)
async def clear_chunk_flag(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    chunk_id: uuid.UUID,
    scope: Scope,
    db: Db,
    clock: ClockDep,
) -> None:
    """Clears the ingestion Guardrail scan's flag on a Chunk of the Document's current edition,
    for a false positive: the Chunk is retrieved again at once, even in a Project that excludes
    flagged Chunks. Records ``chunk.flag_cleared`` with the flag it had."""
    try:
        await service.clear_chunk_flag(
            db, scope, project_id, document_id, chunk_id, now=clock.now()
        )
    except (ProjectNotFoundError, service.DocumentNotFoundError, service.ChunkNotFoundError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    except service.ChunkNotFlaggedError:
        raise HTTPException(status.HTTP_409_CONFLICT, CHUNK_NOT_FLAGGED) from None


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteDocument",
    responses=_errors(_NOT_FOUND, _ARCHIVED),
)
async def delete_document(
    project_id: uuid.UUID, document_id: uuid.UUID, scope: Scope, db: Db, clock: ClockDep
) -> None:
    """Deletes the Document and its Chunks: it stops being retrieved at once. Its stored files
    are deleted in the background. Records ``document.deleted``."""
    try:
        keys = await service.delete_document(db, scope, project_id, document_id, now=clock.now())
    except (ProjectNotFoundError, service.DocumentNotFoundError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    await enqueue_object_deletion(keys)


@router.post(
    "/documents/{document_id}/editions",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="replaceDocument",
    response_model=DocumentOut,
    responses={
        **_errors(
            _NOT_FOUND,
            (413, "The file is larger than the upload limit."),
            (422, HASH_MISMATCH),
        ),
        409: {
            **_UPLOAD_CONFLICT,
            "description": f"{_UPLOAD_CONFLICT['description']} / {DOCUMENT_BUSY}",
        },
    },
)
async def replace_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    body: ConfirmUploadRequest,
    scope: Scope,
    db: Db,
    redis: RedisDep,
    store: StoreDep,
    settings: SettingsDep,
) -> DocumentOut | JSONResponse:
    """Confirms an uploaded file as the Document's newer edition and starts ingesting it. The
    current edition keeps serving until the new one is Ready; then the new one replaces it in
    place, keeping the Document's ID and Tags. Refused while the Document is being processed."""
    try:
        replacement = await service.replace_document(
            db,
            redis,
            store,
            scope,
            project_id,
            document_id,
            upload_id=body.upload_id,
            content_hash=body.content_hash,
            max_bytes=settings.max_upload_bytes,
        )
    except (ProjectNotFoundError, service.DocumentNotFoundError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    except service.DocumentBusyError:
        raise HTTPException(status.HTTP_409_CONFLICT, DOCUMENT_BUSY) from None
    except service.UploadNotFoundError:
        raise HTTPException(status.HTTP_409_CONFLICT, UPLOAD_NOT_FOUND) from None
    except service.FileNotUploadedError:
        raise HTTPException(status.HTTP_409_CONFLICT, FILE_NOT_UPLOADED) from None
    except service.ContentHashMismatchError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, HASH_MISMATCH) from None
    except service.FileTooLargeError:
        raise _too_large(settings) from None
    except service.DuplicateDocumentError as duplicate:
        return _duplicate(duplicate)
    document = replacement.document
    tags = await tags_of(db, [document.id])
    accepted = _document_out(
        document,
        await service.chunk_counts(db, document),
        tags.get(document.id, []),
        replacement.staged,
    )
    if replacement.discarded:
        await enqueue_object_deletion(replacement.discarded)
    await enqueue_ingestion(document.id)
    return accepted


@router.post(
    "/documents/{document_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="retryDocument",
    response_model=DocumentOut,
    responses={
        **_errors(_NOT_FOUND),
        409: {
            "model": UploadConflictResponse,
            "description": f"{DOCUMENT_BUSY} / {PROJECT_ARCHIVED} / {_DUPLICATE}",
        },
    },
)
async def retry_document(
    project_id: uuid.UUID, document_id: uuid.UUID, scope: Scope, db: Db
) -> DocumentOut | JSONResponse:
    """Processes a Document again from its stored file: it goes back to Queued. When the
    Document's newer edition is what failed, that edition is retried instead; a Ready Document
    is processed again with the Project's current settings (such as OCR), its Chunks serving
    until the new ones replace them."""
    try:
        document, staged = await service.retry_document(db, scope, project_id, document_id)
    except (ProjectNotFoundError, service.DocumentNotFoundError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    except ProjectArchivedError:
        raise HTTPException(status.HTTP_409_CONFLICT, PROJECT_ARCHIVED) from None
    except service.DocumentBusyError:
        raise HTTPException(status.HTTP_409_CONFLICT, DOCUMENT_BUSY) from None
    except service.DuplicateDocumentError as duplicate:
        return _duplicate(duplicate)
    tags = await tags_of(db, [document.id])
    queued = _document_out(
        document, await service.chunk_counts(db, document), tags.get(document.id, []), staged
    )
    await enqueue_ingestion(document.id)
    return queued
