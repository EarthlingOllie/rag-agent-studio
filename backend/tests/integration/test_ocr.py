"""API seam plus task seam: the per-Project OCR toggle (ticket 03-08).

A Project's OCR flag is read and changed through the Project routes. Ingestion hands it to the
document converter; the fake converter stands in for Docling and reads a "scanned" file only
when OCR is on, so the effect is observed through the API as an Editor would: the Document's
Chunks. Retry reprocesses an existing Document with the Project's current setting.
"""

import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import update

from app.documents.models import Document, DocumentStatus
from tests.conftest import MemberFactory, SignedUpMember
from tests.documents import chunks, create_project, documents, project_path, upload


async def project(member: SignedUpMember, project_id: str) -> dict[str, Any]:
    response = await member.client.get(project_path(member, project_id))
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()
    return found


async def set_ocr(member: SignedUpMember, project_id: str, *, on: bool) -> httpx.Response:
    return await member.client.patch(project_path(member, project_id), json={"ocr_enabled": on})


async def test_a_new_project_has_ocr_off(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)

    assert (await project(owner, project_id))["ocr_enabled"] is False


async def test_an_editor_turns_ocr_on_and_off(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(owner)

    turned_on = await set_ocr(editor, project_id, on=True)

    assert turned_on.status_code == 200, turned_on.text
    assert turned_on.json()["ocr_enabled"] is True
    assert (await project(owner, project_id))["ocr_enabled"] is True
    turned_off = await set_ocr(editor, project_id, on=False)
    assert turned_off.json()["ocr_enabled"] is False
    assert (await project(owner, project_id))["ocr_enabled"] is False


# A "scanned" file for the fake converter: its text is in an image, so only OCR reads it.
SCANNED = b"%PDF-1.7\n%SCANNED\n# Leave policy\n\nEveryone gets 25 days of annual leave a year.\n"


async def chunk_texts(member: SignedUpMember, project_id: str, document_id: str) -> list[str]:
    return [c["text"] for c in await chunks(member, project_id, document_id)]


async def test_with_ocr_on_a_scanned_pdf_becomes_readable(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    await set_ocr(owner, project_id, on=True)

    document = await upload(app, owner, project_id, "scan.pdf", SCANNED)

    (listed,) = await documents(owner, project_id)
    assert (listed["status"], listed["chunk_count"]) == ("ready", 1)
    assert await chunk_texts(owner, project_id, document["id"]) == [
        "Everyone gets 25 days of annual leave a year."
    ]


async def test_with_ocr_off_a_scanned_pdf_has_no_text(app: FastAPI, owner: SignedUpMember) -> None:
    project_id = await create_project(owner)

    document = await upload(app, owner, project_id, "scan.pdf", SCANNED)

    # No text is a failure that says to turn on OCR (ticket 03-04's categories).
    (listed,) = await documents(owner, project_id)
    assert (listed["status"], listed["error_category"], listed["chunk_count"]) == (
        "failed",
        "unsupported_content",
        0,
    )
    assert "turn on OCR for this Project" in listed["error_message"]
    assert await chunk_texts(owner, project_id, document["id"]) == []


async def test_ocr_doesnt_change_files_that_carry_their_own_text(
    app: FastAPI, owner: SignedUpMember
) -> None:
    text = b"%PDF-1.7\n# Expenses\n\nClaim expenses within 30 days.\n"
    without_ocr = await create_project(owner, "Without OCR")
    with_ocr = await create_project(owner, "With OCR")
    await set_ocr(owner, with_ocr, on=True)

    plain = await upload(app, owner, without_ocr, "expenses.pdf", text)
    ocred = await upload(app, owner, with_ocr, "expenses.pdf", text)

    assert await chunk_texts(owner, without_ocr, plain["id"]) == ["Claim expenses within 30 days."]
    assert await chunk_texts(owner, with_ocr, ocred["id"]) == ["Claim expenses within 30 days."]


# Reprocessing existing Documents through retry


async def retry(member: SignedUpMember, project_id: str, document_id: str) -> httpx.Response:
    return await member.client.post(
        f"{project_path(member, project_id)}/documents/{document_id}/retry"
    )


async def test_retry_reprocesses_a_document_with_ocr_turned_on(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(editor)
    document = await upload(app, editor, project_id, "scan.pdf", SCANNED)
    await set_ocr(editor, project_id, on=True)

    retried = await retry(editor, project_id, document["id"])

    assert retried.status_code == 202, retried.text
    assert (retried.json()["id"], retried.json()["status"]) == (document["id"], "queued")
    (listed,) = await documents(editor, project_id)
    assert (listed["id"], listed["status"], listed["chunk_count"]) == (document["id"], "ready", 1)
    assert await chunk_texts(editor, project_id, document["id"]) == [
        "Everyone gets 25 days of annual leave a year."
    ]


async def test_retry_with_ocr_turned_off_drops_the_text_ocr_read(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    await set_ocr(owner, project_id, on=True)
    document = await upload(app, owner, project_id, "scan.pdf", SCANNED)
    await set_ocr(owner, project_id, on=False)

    retried = await retry(owner, project_id, document["id"])

    # The Chunks OCR read serve until reprocessing replaces them; without OCR the scan has no
    # text, so the Document fails and they are dropped.
    assert (retried.json()["status"], retried.json()["chunk_count"]) == ("queued", 1)
    (listed,) = await documents(owner, project_id)
    assert (listed["status"], listed["chunk_count"]) == ("failed", 0)
    assert await chunk_texts(owner, project_id, document["id"]) == []


async def test_retry_reprocesses_a_failed_document(app: FastAPI, owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")
    document = await upload(app, owner, project_id, "scan.pdf", SCANNED)
    app.state.ingestion.converter.failure = None
    await set_ocr(owner, project_id, on=True)

    retried = await retry(owner, project_id, document["id"])

    assert retried.status_code == 202, retried.text
    (listed,) = await documents(owner, project_id)
    assert (listed["status"], listed["error_message"], listed["chunk_count"]) == (
        "ready",
        None,
        1,
    )


async def set_status(app: FastAPI, document_id: str, status: DocumentStatus) -> None:
    """Arranges a Document that is mid-ingestion, which eager tasks never leave one in."""
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(
            update(Document).where(Document.id == uuid.UUID(document_id)).values(status=status)
        )


@pytest.mark.parametrize("status", [DocumentStatus.QUEUED, DocumentStatus.PROCESSING])
async def test_a_document_still_being_processed_cant_be_retried(
    app: FastAPI, owner: SignedUpMember, status: DocumentStatus
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "scan.pdf", SCANNED)
    await set_status(app, document["id"], status)

    retried = await retry(owner, project_id, document["id"])

    assert retried.status_code == 409
    assert retried.json() == {
        "detail": "This Document is still being processed. Try again once it is Ready or Failed."
    }


async def test_an_archived_projects_documents_cant_be_retried(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "scan.pdf", SCANNED)
    await owner.client.post(f"{project_path(owner, project_id)}/archive")

    retried = await retry(owner, project_id, document["id"])

    assert retried.status_code == 409
    assert retried.json() == {"detail": "This Project is archived. An Owner can restore it."}


async def test_retrying_an_unknown_document_or_anothers_projects_is_not_found(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner, "One")
    other_id = await create_project(owner, "Two")
    document = await upload(app, owner, project_id, "scan.pdf", SCANNED)

    answers = [
        await retry(owner, other_id, document["id"]),
        await retry(owner, project_id, "00000000-0000-0000-0000-000000000000"),
        await retry(owner, "00000000-0000-0000-0000-000000000000", document["id"]),
    ]

    assert [(a.status_code, a.json()) for a in answers] == [(404, {"detail": "Not found"})] * 3
