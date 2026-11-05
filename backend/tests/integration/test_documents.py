"""API seam plus task seam: an Editor uploads a Document (presign, direct upload, confirm) and
ingestion runs eagerly through the fake converter and the deterministic embedder. Outcomes are
observed through the API: the Document list, the status endpoint and the Chunk list."""

import json
from pathlib import Path

import pytest
from docling_core.types.doc.document import DoclingDocument
from fastapi import FastAPI

from tests.conftest import MemberFactory, SignedUpMember
from tests.documents import (
    chunks,
    confirm,
    create_project,
    documents,
    project_path,
    put_to_memory_store,
    start_upload,
    upload,
)

HANDBOOK = b"""# Northwind staff handbook

Welcome to Northwind Traders.

## Annual leave

Everyone gets 25 days of annual leave a year.
Book leave in the HR portal.

## Expenses

Claim expenses within 30 days.
"""
# The SHA-256 of HANDBOOK, computed outside the app.
HANDBOOK_SHA256 = "a18312ccfeec19318861ce44c370ebe21dcdc40dcb73b799656bcad316e19797"


async def test_an_editor_uploads_a_document_that_goes_from_queued_to_ready(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(editor)

    confirmed = await upload(app, editor, project_id, "handbook.md", HANDBOOK)

    assert confirmed["status"] == "queued"
    assert (confirmed["name"], confirmed["mime_type"]) == ("handbook.md", "text/markdown")
    assert (confirmed["size_bytes"], confirmed["content_hash"]) == (len(HANDBOOK), HANDBOOK_SHA256)
    (listed,) = await documents(editor, project_id)
    assert listed["id"] == confirmed["id"]
    assert (listed["status"], listed["error_message"]) == ("ready", None)
    assert listed["chunk_count"] == 3


async def test_a_ready_document_lists_its_chunks_with_headings_and_pages(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    # The fake converter starts a new page at each form feed.
    paged = HANDBOOK.replace(b"## Expenses", b"\f## Expenses")

    document = await upload(app, owner, project_id, "handbook.txt", paged)

    listed = await chunks(owner, project_id, document["id"])
    assert [(c["ordinal"], c["heading_path"], c["page_start"], c["page_end"]) for c in listed] == [
        (0, ["Northwind staff handbook"], 1, 1),
        (1, ["Northwind staff handbook", "Annual leave"], 1, 1),
        (2, ["Northwind staff handbook", "Expenses"], 2, 2),
    ]
    assert [c["text"] for c in listed] == [
        "Welcome to Northwind Traders.",
        "Everyone gets 25 days of annual leave a year. Book leave in the HR portal.",
        "Claim expenses within 30 days.",
    ]
    assert {c["embedding_model_id"] for c in listed} == {"multilingual-e5-small"}


FIXTURES = Path(__file__).parents[1] / "fixtures"


class ReplayConverter:
    """Returns Docling's output for the sample PDF, from ``tests/fixtures/docling``, and keeps
    what it was asked to convert."""

    def __init__(self) -> None:
        self.received: list[tuple[str, bytes]] = []

    def convert(self, data: bytes, filename: str) -> DoclingDocument:
        self.received.append((filename, data))
        recorded = FIXTURES / "docling" / "northwind-handbook.pdf.json"
        return DoclingDocument.model_validate(json.loads(recorded.read_text()))


async def test_an_uploaded_pdf_becomes_ready_with_chunks_from_its_pages(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    converter = ReplayConverter()
    app.state.ingestion.converter = converter
    pdf = (FIXTURES / "documents" / "northwind-handbook.pdf").read_bytes()

    document = await upload(app, owner, project_id, "northwind-handbook.pdf", pdf)

    assert converter.received == [("northwind-handbook.pdf", pdf)]
    assert document["mime_type"] == "application/pdf"
    (listed,) = await documents(owner, project_id)
    assert (listed["status"], listed["chunk_count"]) == ("ready", 3)
    listed_chunks = await chunks(owner, project_id, document["id"])
    assert [(c["heading_path"][-1], c["page_start"], c["page_end"]) for c in listed_chunks] == [
        ("Annual leave", 1, 1),
        ("Expenses", 2, 2),
        ("Working from home", 2, 2),
    ]
    assert "25 days of annual leave" in listed_chunks[0]["text"]


async def test_the_status_endpoint_reports_each_documents_status(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    first = await upload(app, owner, project_id, "first.md", b"# One\n\nFirst file.")
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")
    second = await upload(app, owner, project_id, "second.md", b"# Two\n\nSecond file.")

    response = await owner.client.get(f"{project_path(owner, project_id)}/documents/statuses")

    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            "id": second["id"],
            "status": "failed",
            "error_message": "This Document couldn't be processed. Try uploading it again.",
            "chunk_count": 0,
            "replacement": None,
        },
        {
            "id": first["id"],
            "status": "ready",
            "error_message": None,
            "chunk_count": 1,
            "replacement": None,
        },
    ]


async def test_documents_are_counted_on_their_project(app: FastAPI, owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    other_project_id = await create_project(owner, "Empty")
    await upload(app, owner, project_id, "a.md", b"A")
    await upload(app, owner, project_id, "b.md", b"B")

    listed = (await owner.client.get(f"/api/organisations/{owner.organisation_id}/projects")).json()

    counts = {p["id"]: p["document_count"] for p in listed}
    assert counts == {project_id: 2, other_project_id: 0}


@pytest.mark.parametrize(
    "filename", ["guide.pdf", "notes.DOCX", "deck.pptx", "page.html", "page.htm", "a.markdown"]
)
async def test_each_supported_file_type_can_be_uploaded(
    owner: SignedUpMember, filename: str
) -> None:
    project_id = await create_project(owner)

    response = await start_upload(owner, project_id, filename, 10)

    assert response.status_code == 201, response.text
    assert response.json()["method"] == "PUT"


@pytest.mark.parametrize("filename", ["sheet.xlsx", "photo.png", "README"])
async def test_an_unsupported_file_type_is_refused_before_upload(
    owner: SignedUpMember, filename: str
) -> None:
    project_id = await create_project(owner)

    response = await start_upload(owner, project_id, filename, 10)

    assert response.status_code == 415
    assert response.json()["detail"] == (
        "This file type isn't supported. Upload a PDF, DOCX, PPTX, HTML, Markdown or TXT file."
    )


async def test_a_file_over_the_size_limit_is_refused_before_upload(owner: SignedUpMember) -> None:
    project_id = await create_project(owner)

    at_limit = await start_upload(owner, project_id, "big.pdf", 50 * 1024 * 1024)
    over = await start_upload(owner, project_id, "big.pdf", 50 * 1024 * 1024 + 1)

    assert at_limit.status_code == 201, at_limit.text
    assert (over.status_code, over.json()["detail"]) == (
        413,
        "This file is larger than the 50 MB upload limit.",
    )


async def test_the_browsers_content_hash_is_checked_against_the_stored_file(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    started = (await start_upload(owner, project_id, "handbook.md", len(HANDBOOK))).json()
    await put_to_memory_store(app, started["url"], HANDBOOK, "text/markdown")

    wrong = await confirm(owner, project_id, started["upload_id"], "0" * 64)
    right = await confirm(owner, project_id, started["upload_id"], HANDBOOK_SHA256.upper())

    assert (wrong.status_code, wrong.json()["detail"]) == (
        422,
        "The uploaded file doesn't match its content hash. Upload it again.",
    )
    assert right.status_code == 201, right.text
    assert right.json()["content_hash"] == HANDBOOK_SHA256
    assert len(await documents(owner, project_id)) == 1


async def test_an_upload_is_confirmed_only_once_after_the_file_arrives(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    started = (await start_upload(owner, project_id, "handbook.md", len(HANDBOOK))).json()

    early = await confirm(owner, project_id, started["upload_id"])
    await put_to_memory_store(app, started["url"], HANDBOOK, "text/markdown")
    confirmed = await confirm(owner, project_id, started["upload_id"])
    again = await confirm(owner, project_id, started["upload_id"])

    assert (early.status_code, early.json()["detail"]) == (
        409,
        "The file hasn't reached storage yet. Upload it, then confirm.",
    )
    assert confirmed.status_code == 201, confirmed.text
    assert (again.status_code, again.json()["detail"]) == (
        409,
        "This upload wasn't found or has expired. Start the upload again.",
    )
    assert len(await documents(owner, project_id)) == 1


async def test_an_upload_is_confirmed_only_in_its_own_project(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    other_project_id = await create_project(owner, "Other")
    started = (await start_upload(owner, project_id, "handbook.md", len(HANDBOOK))).json()
    await put_to_memory_store(app, started["url"], HANDBOOK, "text/markdown")

    crossed = await confirm(owner, other_project_id, started["upload_id"])

    assert crossed.status_code == 409
    assert await documents(owner, other_project_id) == []


async def test_an_archived_project_takes_no_uploads(app: FastAPI, owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    started = (await start_upload(owner, project_id, "handbook.md", len(HANDBOOK))).json()
    await put_to_memory_store(app, started["url"], HANDBOOK, "text/markdown")
    archived = await owner.client.post(f"{project_path(owner, project_id)}/archive")
    assert archived.status_code == 200, archived.text

    refused_start = await start_upload(owner, project_id, "more.md", 10)
    refused_confirm = await confirm(owner, project_id, started["upload_id"])

    archived_message = "This Project is archived. An Owner can restore it."
    assert (refused_start.status_code, refused_start.json()["detail"]) == (409, archived_message)
    assert (refused_confirm.status_code, refused_confirm.json()["detail"]) == (
        409,
        archived_message,
    )
    assert await documents(owner, project_id) == []


async def test_document_routes_of_an_unknown_project_or_document_are_not_found(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    unknown = "00000000-0000-4000-8000-000000000000"
    unknown_project = project_path(owner, unknown)

    answers = [
        await start_upload(owner, unknown, "a.md", 1),
        await confirm(owner, unknown, unknown),
        await owner.client.get(f"{unknown_project}/documents"),
        await owner.client.get(f"{unknown_project}/documents/statuses"),
        await owner.client.get(f"{unknown_project}/documents/{unknown}/chunks"),
        await owner.client.get(f"{project_path(owner, project_id)}/documents/{unknown}/chunks"),
    ]

    assert {(a.status_code, a.json()["detail"]) for a in answers} == {(404, "Not found")}


async def test_chunks_are_no_longer_than_the_chunk_size_setting(
    app: FastAPI, owner: SignedUpMember, settings_env: pytest.MonkeyPatch
) -> None:
    # The fake embedder's tokenizer counts words, so the setting is in words here.
    settings_env.setenv("CHUNK_MAX_TOKENS", "8")
    project_id = await create_project(owner)
    words = " ".join(f"word{n}" for n in range(30))

    document = await upload(app, owner, project_id, "long.md", f"# Long\n\n{words}".encode())

    listed = await chunks(owner, project_id, document["id"])
    assert len(listed) >= 4
    # Each Chunk plus its heading fits in 8 words, and together they hold the whole text.
    assert max(len(c["text"].split()) + 1 for c in listed) <= 8
    assert " ".join(c["text"] for c in listed).split() == words.split()
