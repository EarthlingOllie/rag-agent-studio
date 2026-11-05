"""What a Document must satisfy: a supported file type, the upload size limit, content that
matches its type, and room in the Project's Document quota. Plus the readable messages an
Editor sees when one isn't met, and the backoff between automatic retries."""

import io
import uuid
import zipfile
from pathlib import PurePath

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document, DocumentStatus

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

# How each type is named in messages.
TYPE_NAMES: dict[str, str] = {
    "application/pdf": "PDF",
    SUPPORTED_TYPES[".docx"]: "DOCX",
    SUPPORTED_TYPES[".pptx"]: "PPTX",
    "text/html": "HTML",
    "text/markdown": "Markdown",
    "text/plain": "TXT",
}

# The part every Word or PowerPoint file (a zip) must contain.
_OFFICE_PARTS = {
    SUPPORTED_TYPES[".docx"]: "word/document.xml",
    SUPPORTED_TYPES[".pptx"]: "ppt/presentation.xml",
}


class UnsupportedFileTypeError(Exception):
    """The file's extension isn't one a Document can be made from."""


def mime_type_for(filename: str) -> str:
    try:
        return SUPPORTED_TYPES[PurePath(filename).suffix.lower()]
    except KeyError:
        raise UnsupportedFileTypeError from None


def size_limit_message(max_bytes: int) -> str:
    return f"This file is larger than the {max_bytes // (1024 * 1024)} MB upload limit."


def content_matches_type(data: bytes, mime_type: str) -> bool:
    """Whether the bytes are plausibly a file of the type: a PDF header, a Word or PowerPoint
    zip with its main part, or UTF-8 text without NUL bytes for the text formats."""
    if mime_type == "application/pdf":
        # The PDF header may follow up to 1 KB of leading junk.
        return b"%PDF-" in data[:1024]
    if mime_type in _OFFICE_PARTS:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                return _OFFICE_PARTS[mime_type] in archive.namelist()
        except zipfile.BadZipFile:
            return False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return "\x00" not in text


def wrong_type_message(mime_type: str) -> str:
    return (
        f"This file isn't a valid {TYPE_NAMES[mime_type]} file. "
        "Check the file, then upload it again."
    )


NO_TEXT = "No readable text was found in this file. Check that it isn't empty or a scanned image."
UNREADABLE_CONTENT = (
    "This file's content can't be read. Check that it isn't password-protected or damaged, "
    "then upload it again."
)
CONVERSION_FAILED = "This file couldn't be converted. Retry it, or upload a fixed copy."
ORIGINAL_MISSING = "The uploaded file is missing from storage. Upload it again."
PROCESSING_FAILED = "This Document couldn't be processed. Retry it, or upload it again."


def provider_failed_message(attempts: int) -> str:
    return (
        f"The Embedding Model's provider didn't respond after {attempts} attempts. "
        "Retry the Document later."
    )


def provider_retrying_message(next_attempt: int, max_attempts: int) -> str:
    return (
        "The Embedding Model's provider didn't respond. Retrying automatically "
        f"(attempt {next_attempt} of {max_attempts})."
    )


def _documents(quota: int) -> str:
    return f"{quota} Document" if quota == 1 else f"{quota} Documents"


def quota_refusal_message(quota: int) -> str:
    """Refusing an upload into a full Project."""
    return (
        f"This Project has reached its quota of {_documents(quota)}. "
        "Delete a Document, or ask an Owner to raise the quota."
    )


def quota_failure_message(quota: int) -> str:
    """Failing a Document that no longer fits, when it is processed."""
    return (
        f"This Project has reached its quota of {_documents(quota)}. "
        "Delete a Document, or ask an Owner to raise the quota, then retry."
    )


async def documents_counted(
    session: AsyncSession, project_id: uuid.UUID, *, excluding: uuid.UUID | None = None
) -> int:
    """The Project's Documents that count towards its quota: every one that isn't Failed."""
    query = select(func.count()).where(
        Document.project_id == project_id, Document.status != DocumentStatus.FAILED
    )
    if excluding is not None:
        query = query.where(Document.id != excluding)
    return await session.scalar(query) or 0


def retry_delay(attempt: int, *, base_seconds: float, max_seconds: float) -> float:
    """How long to wait after failed attempt ``attempt`` (from 1) before the next: exponential
    backoff, doubling from the base, capped at the maximum."""
    return min(max_seconds, base_seconds * 2.0 ** (attempt - 1))
