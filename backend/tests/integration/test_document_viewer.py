"""API seam plus task seam: the Document viewer. An Editor opens a Document and reads the
markdown Docling converted it to, pages through its Chunks with their heading paths and pages,
and downloads the original file through a presigned GET."""

from fastapi import FastAPI

from tests.conftest import SignedUpMember
from tests.documents import create_project, get_from_memory_store, project_path, upload

HANDBOOK = b"""# Northwind staff handbook

Welcome to Northwind Traders.

## Annual leave

Everyone gets 25 days of annual leave a year.
"""


async def test_an_editor_opens_a_document_and_reads_its_converted_markdown(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    response = await owner.client.get(
        f"{project_path(owner, project_id)}/documents/{document['id']}"
    )

    assert response.status_code == 200, response.text
    opened = response.json()
    assert (opened["id"], opened["name"], opened["status"]) == (
        document["id"],
        "handbook.md",
        "ready",
    )
    assert opened["chunk_count"] == 2
    # Docling's markdown export: section headings start at level 2 (level 1 is the title).
    assert opened["markdown"] == (
        "## Northwind staff handbook\n\n"
        "Welcome to Northwind Traders.\n\n"
        "### Annual leave\n\n"
        "Everyone gets 25 days of annual leave a year."
    )


async def test_a_document_that_failed_to_convert_opens_without_markdown(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")
    document = await upload(app, owner, project_id, "broken.md", b"# Broken")

    response = await owner.client.get(
        f"{project_path(owner, project_id)}/documents/{document['id']}"
    )

    assert response.status_code == 200, response.text
    opened = response.json()
    assert (opened["status"], opened["chunk_count"], opened["markdown"]) == ("failed", 0, None)
    assert opened["error_message"] == "This Document couldn't be processed. Try uploading it again."


async def test_the_original_file_downloads_through_a_presigned_get(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "Staff handbook.md", HANDBOOK)

    response = await owner.client.get(
        f"{project_path(owner, project_id)}/documents/{document['id']}/download"
    )

    # The API answers with a redirect to a short-lived presigned GET on the object store.
    assert response.status_code == 307, response.text
    downloaded = await get_from_memory_store(app, response.headers["location"])
    assert downloaded.data == HANDBOOK
    assert downloaded.content_type == "text/markdown"
    assert downloaded.content_disposition == (
        "attachment; filename=\"Staff handbook.md\"; filename*=UTF-8''Staff%20handbook.md"
    )
    assert downloaded.expires_in == 300


def _sections(count: int) -> bytes:
    """A Document of ``count`` sections, each its own Chunk."""
    return "".join(f"# Section {n}\n\nPolicy number {n}.\n\n" for n in range(1, count + 1)).encode()


async def test_the_chunk_list_of_a_large_document_comes_a_page_at_a_time(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "policies.md", _sections(7))
    chunks_path = f"{project_path(owner, project_id)}/documents/{document['id']}/chunks"

    pages = [
        (await owner.client.get(chunks_path, params={"offset": offset, "limit": 3})).json()
        for offset in (0, 3, 6, 9)
    ]

    assert [(p["total"], p["offset"], p["limit"]) for p in pages] == [
        (7, 0, 3),
        (7, 3, 3),
        (7, 6, 3),
        (7, 9, 3),
    ]
    assert [[c["ordinal"] for c in p["items"]] for p in pages] == [[0, 1, 2], [3, 4, 5], [6], []]
    assert [c["heading_path"] for c in pages[2]["items"]] == [["Section 7"]]
    assert pages[2]["items"][0]["text"] == "Policy number 7."


async def test_the_chunk_list_pages_fifty_chunks_by_default_and_at_most_two_hundred(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    document = await upload(app, owner, project_id, "policies.md", _sections(51))
    chunks_path = f"{project_path(owner, project_id)}/documents/{document['id']}/chunks"

    first = await owner.client.get(chunks_path)
    too_many = await owner.client.get(chunks_path, params={"limit": 201})
    negative = await owner.client.get(chunks_path, params={"offset": -1})
    empty = await owner.client.get(chunks_path, params={"limit": 0})

    assert first.status_code == 200, first.text
    assert (first.json()["total"], first.json()["limit"], len(first.json()["items"])) == (
        51,
        50,
        50,
    )
    assert (too_many.status_code, negative.status_code, empty.status_code) == (422, 422, 422)
