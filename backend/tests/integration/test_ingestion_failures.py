"""API seam plus task seam for what goes wrong: files refused before upload, the Document quota,
categorised ingestion failures, automatic retries of transient ones, and retrying by hand.

Failures come from configuring the fakes (converter, embedder, object store) to raise; every
outcome is observed through the API, as an Editor would see it."""

import io
import zipfile
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.documents.converter import UnsupportedContentError
from app.embeddings.port import EmbeddingProviderError
from tests.conftest import MemberFactory, SignedUpMember
from tests.documents import (
    confirm,
    create_project,
    documents,
    project_path,
    put_to_memory_store,
    start_upload,
    upload,
)

HANDBOOK = b"# Handbook\n\nEveryone gets 25 days of annual leave a year."
LOCAL_MODEL = "multilingual-e5-small"


async def limits(member: SignedUpMember, project_id: str) -> httpx.Response:
    return await member.client.get(f"{project_path(member, project_id)}/uploads/limits")


async def set_quota(member: SignedUpMember, project_id: str, quota: int) -> httpx.Response:
    return await member.client.put(
        f"{project_path(member, project_id)}/document-quota", json={"document_quota": quota}
    )


async def retry(member: SignedUpMember, project_id: str, document_id: str) -> httpx.Response:
    return await member.client.post(
        f"{project_path(member, project_id)}/documents/{document_id}/retry"
    )


async def only_document(member: SignedUpMember, project_id: str) -> dict[str, Any]:
    (listed,) = await documents(member, project_id)
    return listed


def failure_of(document: dict[str, Any]) -> tuple[str, str | None, str | None]:
    return document["status"], document["error_category"], document["error_message"]


def zipped(*names: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, "<xml/>")
    return buffer.getvalue()


# --- Limits and the Document quota -------------------------------------------------------


async def test_the_upload_limits_name_the_types_size_and_quota(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)

    response = await limits(owner, project_id)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "accepted_extensions": [
            ".pdf",
            ".docx",
            ".pptx",
            ".html",
            ".htm",
            ".md",
            ".markdown",
            ".txt",
        ],
        "max_upload_bytes": 50 * 1024 * 1024,
        "document_quota": 500,
        "documents_counted": 0,
    }


async def test_only_an_owner_sets_a_projects_document_quota(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)

    refused = await set_quota(editor, project_id, 3)
    changed = await set_quota(owner, project_id, 3)
    invalid = await set_quota(owner, project_id, 0)

    assert refused.status_code == 403
    assert changed.status_code == 200, changed.text
    assert changed.json()["document_quota"] == 3
    assert (await limits(editor, project_id)).json()["document_quota"] == 3
    assert invalid.status_code == 422


async def test_a_full_project_refuses_uploads_with_a_clear_message(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    assert (await set_quota(owner, project_id, 2)).status_code == 200
    await upload(app, owner, project_id, "a.md", b"# A\n\nFirst.")
    # Started while there was room, confirmed after the Project filled up.
    late = (await start_upload(owner, project_id, "c.md", len(HANDBOOK))).json()
    await put_to_memory_store(app, late["url"], HANDBOOK, late["content_type"])
    await upload(app, owner, project_id, "b.md", b"# B\n\nSecond.")

    refused_start = await start_upload(owner, project_id, "d.md", 10)
    refused_confirm = await confirm(owner, project_id, late["upload_id"])

    message = (
        "This Project has reached its quota of 2 Documents. "
        "Delete a Document, or ask an Owner to raise the quota."
    )
    assert (refused_start.status_code, refused_start.json()["detail"]) == (409, message)
    assert (refused_confirm.status_code, refused_confirm.json()["detail"]) == (409, message)
    assert len(await documents(owner, project_id)) == 2
    assert (await limits(owner, project_id)).json()["documents_counted"] == 2


async def test_failed_documents_do_not_count_towards_the_quota(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    assert (await set_quota(owner, project_id, 1)).status_code == 200
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")
    await upload(app, owner, project_id, "broken.md", HANDBOOK)
    app.state.ingestion.converter.failure = None

    await upload(app, owner, project_id, "fine.md", HANDBOOK)

    assert sorted(d["status"] for d in await documents(owner, project_id)) == ["failed", "ready"]
    assert (await limits(owner, project_id)).json()["documents_counted"] == 1


async def test_a_retried_document_that_no_longer_fits_fails_on_quota(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    assert (await set_quota(owner, project_id, 2)).status_code == 200
    await upload(app, owner, project_id, "a.md", b"# A\n\nFirst.")
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")
    failed = await upload(app, owner, project_id, "b.md", b"# B\n\nSecond.")
    app.state.ingestion.converter.failure = None
    assert (await set_quota(owner, project_id, 1)).status_code == 200

    response = await retry(owner, project_id, failed["id"])

    assert response.status_code == 200, response.text
    retried = next(d for d in await documents(owner, project_id) if d["id"] == failed["id"])
    assert failure_of(retried) == (
        "failed",
        "quota",
        "This Project has reached its quota of 1 Document. "
        "Delete a Document, or ask an Owner to raise the quota, then retry.",
    )


# --- Type and size, before and after the upload --------------------------------------------


async def test_a_file_larger_than_it_claimed_is_refused_on_confirm(
    app: FastAPI, owner: SignedUpMember, settings_env: pytest.MonkeyPatch
) -> None:
    project_id = await create_project(owner)
    started = (await start_upload(owner, project_id, "small.md", 10)).json()
    oversized = b"x" * (50 * 1024 * 1024 + 1)
    await put_to_memory_store(app, started["url"], oversized, started["content_type"])

    response = await confirm(owner, project_id, started["upload_id"])

    assert (response.status_code, response.json()["detail"]) == (
        413,
        "This file is larger than the 50 MB upload limit.",
    )
    assert await documents(owner, project_id) == []
    assert app.state.ingestion.object_store.objects == {}


# --- Categorised failures -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "data", "kind"),
    [
        ("guide.pdf", b"This is not really a PDF", "PDF"),
        ("notes.docx", b"plain text, not a Word file", "DOCX"),
        ("notes.docx", zipped("ppt/presentation.xml"), "DOCX"),
        ("deck.pptx", zipped("word/document.xml"), "PPTX"),
        ("page.html", b"\x89PNG\r\n\x1a\n\x00\x00binary", "HTML"),
        ("notes.md", b"\xff\xfe\x00b\x00a\x00d", "Markdown"),
        ("notes.txt", b"caf\xe9 au lait", "TXT"),
    ],
)
async def test_content_that_does_not_match_its_type_fails_as_unsupported(
    app: FastAPI, owner: SignedUpMember, filename: str, data: bytes, kind: str
) -> None:
    project_id = await create_project(owner)

    await upload(app, owner, project_id, filename, data)

    assert failure_of(await only_document(owner, project_id)) == (
        "failed",
        "unsupported_content",
        f"This file isn't a valid {kind} file. Check the file, then upload it again.",
    )


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        ("real.pdf", b"%PDF-1.7\n1 0 obj\n# Title\n\nSome text."),
        ("real.docx", zipped("word/document.xml")),
        ("real.pptx", zipped("ppt/presentation.xml")),
        ("real.txt", "Café au lait.".encode()),
    ],
)
async def test_content_that_matches_its_type_is_converted(
    app: FastAPI, owner: SignedUpMember, filename: str, data: bytes
) -> None:
    project_id = await create_project(owner)

    await upload(app, owner, project_id, filename, data)

    # The fake converter reads any bytes as text, so each of these yields some Chunks.
    assert failure_of(await only_document(owner, project_id)) == ("ready", None, None)


async def test_a_file_with_no_readable_text_fails_as_unsupported(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)

    await upload(app, owner, project_id, "blank.md", b"   \n\n  ")

    assert failure_of(await only_document(owner, project_id)) == (
        "failed",
        "unsupported_content",
        "No readable text was found in this file. Check that it isn't empty or a scanned image.",
    )


async def test_content_the_converter_cannot_read_fails_as_unsupported(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    app.state.ingestion.converter.failure = UnsupportedContentError("password protected")

    await upload(app, owner, project_id, "locked.md", HANDBOOK)

    assert failure_of(await only_document(owner, project_id)) == (
        "failed",
        "unsupported_content",
        "This file's content can't be read. Check that it isn't password-protected or damaged, "
        "then upload it again.",
    )


async def test_a_conversion_error_fails_with_a_readable_message(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")

    await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    document = await only_document(owner, project_id)
    assert failure_of(document) == (
        "failed",
        "conversion",
        "This file couldn't be converted. Retry it, or upload a fixed copy.",
    )
    # A conversion error isn't transient, so it isn't retried automatically.
    assert document["attempt_count"] == 1


async def test_an_original_missing_from_storage_fails_with_a_readable_message(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")
    failed = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    app.state.ingestion.converter.failure = None
    app.state.ingestion.object_store.objects.clear()

    await retry(owner, project_id, failed["id"])

    assert failure_of(await only_document(owner, project_id)) == (
        "failed",
        "conversion",
        "The uploaded file is missing from storage. Upload it again.",
    )


async def test_an_unexpected_error_fails_with_a_general_message(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")
    failed = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    app.state.ingestion.converter.failure = None
    app.state.ingestion.object_store.failure = OSError("disk full")

    await retry(owner, project_id, failed["id"])

    assert failure_of(await only_document(owner, project_id)) == (
        "failed",
        "conversion",
        "This Document couldn't be processed. Retry it, or upload it again.",
    )


# --- Transient failures retry automatically ----------------------------------------------------


async def test_a_transient_provider_error_is_retried_automatically(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    embedder = app.state.ingestion.embedders[LOCAL_MODEL]
    embedder.failures = [EmbeddingProviderError("timeout"), EmbeddingProviderError("503")]

    await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    document = await only_document(owner, project_id)
    assert failure_of(document) == ("ready", None, None)
    assert document["attempt_count"] == 3
    assert document["chunk_count"] == 1


async def test_a_provider_error_that_persists_fails_after_the_last_attempt(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    embedder = app.state.ingestion.embedders[LOCAL_MODEL]
    embedder.failures = [EmbeddingProviderError("down")] * 10

    await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    document = await only_document(owner, project_id)
    assert failure_of(document) == (
        "failed",
        "provider",
        "The Embedding Model's provider didn't respond after 4 attempts. Retry the Document later.",
    )
    assert document["attempt_count"] == 4


# --- Retrying by hand ---------------------------------------------------------------------------


async def test_an_editor_retries_a_failed_document_until_it_is_ready(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(editor)
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")
    failed = await upload(app, editor, project_id, "handbook.md", HANDBOOK)
    app.state.ingestion.converter.failure = None

    response = await retry(editor, project_id, failed["id"])

    assert response.status_code == 200, response.text
    assert failure_of(response.json()) == ("queued", None, None)
    document = await only_document(editor, project_id)
    assert failure_of(document) == ("ready", None, None)
    assert (document["chunk_count"], document["attempt_count"]) == (1, 2)


async def test_only_a_failed_document_can_be_retried(app: FastAPI, owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    ready = await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    response = await retry(owner, project_id, ready["id"])

    assert (response.status_code, response.json()["detail"]) == (
        409,
        "Only a Failed Document can be retried.",
    )


async def test_a_document_in_an_archived_project_is_not_retried(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")
    failed = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    app.state.ingestion.converter.failure = None
    assert (await owner.client.post(f"{project_path(owner, project_id)}/archive")).is_success

    response = await retry(owner, project_id, failed["id"])

    assert (response.status_code, response.json()["detail"]) == (
        409,
        "This Project is archived. An Owner can restore it.",
    )
    assert (await only_document(owner, project_id))["status"] == "failed"


async def test_retry_and_limit_routes_of_unknown_things_are_not_found(
    owner: SignedUpMember,
) -> None:
    project_id = await create_project(owner)
    unknown = "00000000-0000-4000-8000-000000000000"

    answers = [
        await retry(owner, project_id, unknown),
        await retry(owner, unknown, unknown),
        await limits(owner, unknown),
        await set_quota(owner, unknown, 5),
    ]

    assert {(a.status_code, a.json()["detail"]) for a in answers} == {(404, "Not found")}
