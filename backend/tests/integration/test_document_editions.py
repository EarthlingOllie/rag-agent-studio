"""API seam plus task seam: duplicate uploads are refused, deleting a Document stops it being
retrieved at once, and a newer edition replaces a Document in place, with the old edition
serving until the new one is Ready. Ingestion runs eagerly through the fakes."""

import asyncio
import threading
from typing import Any

import pytest
from docling_core.types.doc.document import DoclingDocument
from fastapi import FastAPI
from sqlalchemy import text

from app.documents.converter import FakeConverter
from app.storage.memory import InMemoryObjectStore
from tests.conftest import MemberFactory, SignedUpMember
from tests.documents import (
    chunks,
    confirm,
    create_project,
    documents,
    project_path,
    put_to_memory_store,
    replace,
    start_upload,
    upload,
)
from tests.fakes.clock import ControllableClock

HANDBOOK = b"# Handbook\n\nEveryone gets 25 days of annual leave.\n"
# The SHA-256 of HANDBOOK, computed outside the app.
HANDBOOK_SHA256 = "ea7ef7515db6ec42372ea55177347155b7d15134889467d7ced15480bbf5f98f"


async def test_uploading_an_identical_file_is_refused_with_a_link_to_the_existing_document(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    existing = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    started = (await start_upload(owner, project_id, "copy of handbook.md", len(HANDBOOK))).json()
    await put_to_memory_store(app, started["url"], HANDBOOK, "text/markdown")

    refused = await confirm(owner, project_id, started["upload_id"])

    assert refused.status_code == 409
    assert refused.json() == {
        "detail": "This file is already in the Project as handbook.md.",
        "document_id": existing["id"],
        "document_name": "handbook.md",
    }
    assert [d["id"] for d in await documents(owner, project_id)] == [existing["id"]]
    # The refused copy is discarded: only the existing Document's original and markdown are kept.
    assert len(stored(app)) == 2


async def test_a_failed_documents_file_can_be_uploaded_again_as_a_new_document(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")
    failed = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    app.state.ingestion.converter.failure = None

    retried = await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    listed = {d["id"]: d["status"] for d in await documents(owner, project_id)}
    assert listed == {failed["id"]: "failed", retried["id"]: "ready"}


async def test_a_failed_documents_file_can_be_uploaded_again_as_its_new_edition(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")
    failed = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    app.state.ingestion.converter.failure = None

    retried = await replace(app, owner, project_id, failed["id"], "handbook.md", HANDBOOK)

    assert retried.status_code == 202, retried.text
    (listed,) = await documents(owner, project_id)
    assert (listed["edition"], listed["status"], listed["replacement"]) == (2, "ready", None)
    assert texts(await chunks(owner, project_id, failed["id"])) == [
        "Everyone gets 25 days of annual leave."
    ]


# Deleting


def stored(app: FastAPI) -> list[bytes]:
    """What the in-memory object store holds, sorted: originals and converted markdown. Stored
    files have no API surface to observe."""
    store = app.state.ingestion.object_store
    assert isinstance(store, InMemoryObjectStore)
    return sorted(data for data, _ in store.objects.values())


async def chunk_rows(app: FastAPI, document_id: str) -> int:
    """Chunk rows of a Document, read from the table: a deleted Document's Chunk list is a 404,
    so whether its rows are gone has no API surface."""
    async with app.state.sessionmaker() as session:
        count: int = await session.scalar(
            text("SELECT count(*) FROM chunks WHERE document_id = :id"), {"id": document_id}
        )
    return count


async def audit_events(owner: SignedUpMember, action: str) -> list[dict[str, Any]]:
    response = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/audit-events", params={"action": action}
    )
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def test_an_editor_deletes_a_document_and_it_stops_being_retrieved_at_once(
    app: FastAPI, owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    editor = await member_factory(owner, "editor")
    project_id = await create_project(editor)
    kept = await upload(app, editor, project_id, "faq.md", b"# FAQ\n\nAsk HR.")
    document = await upload(app, editor, project_id, "handbook.md", HANDBOOK)
    assert len(await chunks(editor, project_id, document["id"])) == 1
    assert len(stored(app)) == 4

    deleted = await editor.client.delete(
        f"{project_path(editor, project_id)}/documents/{document['id']}"
    )

    assert deleted.status_code == 204, deleted.text
    assert [d["id"] for d in await documents(editor, project_id)] == [kept["id"]]
    gone = await editor.client.get(
        f"{project_path(editor, project_id)}/documents/{document['id']}/chunks"
    )
    assert gone.status_code == 404
    assert await chunk_rows(app, document["id"]) == 0
    assert len(await chunks(editor, project_id, kept["id"])) == 1
    # The original and its converted markdown are deleted from storage; the other's stay.
    assert stored(app) == [b"# FAQ\n\nAsk HR.", b"## FAQ\n\nAsk HR."]
    (event,) = await audit_events(owner, "document.deleted")
    assert (event["actor"]["id"], event["target"]) == (
        editor.member_id,
        {"type": "document", "id": document["id"]},
    )
    assert (event["before"], event["after"]) == (
        {"project_id": project_id, "name": "handbook.md", "content_hash": HANDBOOK_SHA256},
        None,
    )
    assert event["occurred_at"] == "2026-11-05T09:00:00Z"


# Replacing an edition

HANDBOOK_2027 = (
    b"# Handbook\n\nEveryone gets 28 days of annual leave.\n\n## Expenses\n\nClaim in 30 days.\n"
)
FAILED_MESSAGE = "This Document couldn't be processed. Try uploading it again."
BUSY = "This Document is still being processed. Try again once it is Ready or Failed."


class GatedConverter(FakeConverter):
    """The fake converter, held at the start of each conversion until the test releases it, so
    the test can look at the API while a Document is Processing."""

    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def convert(self, data: bytes, filename: str) -> DoclingDocument:
        self.started.set()
        assert self.release.wait(timeout=10)
        return super().convert(data, filename)

    async def wait_until_started(self) -> None:
        assert await asyncio.to_thread(self.started.wait, 10)


def texts(listed: list[dict[str, Any]]) -> list[str]:
    return [c["text"] for c in listed]


async def test_a_newer_edition_replaces_the_document_in_place(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    original = await upload(app, owner, project_id, "handbook-2026.md", HANDBOOK)

    replaced = await replace(
        app, owner, project_id, original["id"], "handbook-2027.md", HANDBOOK_2027
    )

    assert replaced.status_code == 202, replaced.text
    accepted = replaced.json()
    assert (accepted["id"], accepted["edition"], accepted["status"]) == (original["id"], 1, "ready")
    assert accepted["replacement"] == {
        "edition": 2,
        "name": "handbook-2027.md",
        "status": "queued",
        "error_message": None,
    }
    (listed,) = await documents(owner, project_id)
    assert (listed["id"], listed["created_at"]) == (original["id"], original["created_at"])
    assert (listed["name"], listed["edition"], listed["status"]) == ("handbook-2027.md", 2, "ready")
    assert (listed["size_bytes"], listed["chunk_count"]) == (len(HANDBOOK_2027), 2)
    assert listed["content_hash"] != original["content_hash"]
    assert listed["replacement"] is None
    assert texts(await chunks(owner, project_id, original["id"])) == [
        "Everyone gets 28 days of annual leave.",
        "Claim in 30 days.",
    ]
    # The old edition's Chunk rows are gone, not just hidden.
    assert await chunk_rows(app, original["id"]) == 2
    # Only the new edition's original and markdown are kept; the old edition's are deleted.
    kept = stored(app)
    assert len(kept) == 2
    assert HANDBOOK_2027 in kept
    assert HANDBOOK not in kept


async def test_a_new_edition_keeps_the_documents_tags(app: FastAPI, owner: SignedUpMember) -> None:
    project_id = await create_project(owner)
    original = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    path = project_path(owner, project_id)
    created = await owner.client.post(f"{path}/tags", json={"name": "HR"})
    assert created.status_code == 201, created.text
    tag = created.json()
    tagged = await owner.client.put(
        f"{path}/documents/{original['id']}/tags", json={"tag_ids": [tag["id"]]}
    )
    assert tagged.status_code == 200, tagged.text

    replaced = await replace(app, owner, project_id, original["id"], "handbook.md", HANDBOOK_2027)

    assert replaced.status_code == 202, replaced.text
    assert [t["id"] for t in replaced.json()["tags"]] == [tag["id"]]
    (listed,) = await documents(owner, project_id)
    assert (listed["edition"], [t["id"] for t in listed["tags"]]) == (2, [tag["id"]])


async def test_the_old_edition_keeps_serving_until_the_new_one_is_ready(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    original = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    gate = GatedConverter()
    app.state.ingestion.converter = gate

    replacing = asyncio.create_task(
        replace(app, owner, project_id, original["id"], "handbook.md", HANDBOOK_2027)
    )
    await gate.wait_until_started()

    (during,) = await documents(owner, project_id)
    assert (during["edition"], during["status"], during["chunk_count"]) == (1, "ready", 1)
    assert during["replacement"] == {
        "edition": 2,
        "name": "handbook.md",
        "status": "processing",
        "error_message": None,
    }
    statuses = await owner.client.get(f"{project_path(owner, project_id)}/documents/statuses")
    (status,) = statuses.json()
    assert (status["status"], status["replacement"]["status"]) == ("ready", "processing")
    assert texts(await chunks(owner, project_id, original["id"])) == [
        "Everyone gets 25 days of annual leave."
    ]
    # While the new edition is processing, another replacement is refused, and so is a copy of
    # the new edition uploaded as a Document of its own.
    again = await replace(app, owner, project_id, original["id"], "other.md", b"# Other")
    assert (again.status_code, again.json()["detail"]) == (409, BUSY)
    started = (await start_upload(owner, project_id, "copy.md", len(HANDBOOK_2027))).json()
    await put_to_memory_store(app, started["url"], HANDBOOK_2027, "text/markdown")
    copy = await confirm(owner, project_id, started["upload_id"])
    assert (copy.status_code, copy.json()["document_id"]) == (409, original["id"])

    gate.release.set()
    assert (await replacing).status_code == 202

    (after,) = await documents(owner, project_id)
    assert (after["edition"], after["status"], after["replacement"]) == (2, "ready", None)
    assert texts(await chunks(owner, project_id, original["id"])) == [
        "Everyone gets 28 days of annual leave.",
        "Claim in 30 days.",
    ]


async def test_a_failed_replacement_leaves_the_old_edition_serving(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    original = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")

    failed = await replace(app, owner, project_id, original["id"], "broken.md", b"# Broken")

    assert failed.status_code == 202, failed.text
    (listed,) = await documents(owner, project_id)
    assert (listed["name"], listed["edition"], listed["status"]) == ("handbook.md", 1, "ready")
    assert listed["replacement"] == {
        "edition": 2,
        "name": "broken.md",
        "status": "failed",
        "error_message": FAILED_MESSAGE,
    }
    assert texts(await chunks(owner, project_id, original["id"])) == [
        "Everyone gets 25 days of annual leave."
    ]

    # A failed replacement's file can be uploaded again as a new Document or edition.
    app.state.ingestion.converter.failure = None
    retried = await replace(app, owner, project_id, original["id"], "fixed.md", b"# Broken")

    assert retried.status_code == 202, retried.text
    (listed,) = await documents(owner, project_id)
    assert (listed["name"], listed["edition"], listed["replacement"]) == ("fixed.md", 2, None)
    assert stored(app) == [b"# Broken", b"## Broken"]


async def test_deleting_a_document_also_deletes_its_failed_replacements_file(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    original = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    app.state.ingestion.converter.failure = RuntimeError("Docling crashed")
    await replace(app, owner, project_id, original["id"], "broken.md", b"# Broken")

    deleted = await owner.client.delete(
        f"{project_path(owner, project_id)}/documents/{original['id']}"
    )

    assert deleted.status_code == 204
    assert await documents(owner, project_id) == []
    assert stored(app) == []


async def test_replacing_with_the_same_content_is_refused_as_a_duplicate(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    original = await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    same = await replace(app, owner, project_id, original["id"], "handbook again.md", HANDBOOK)

    assert same.status_code == 409
    assert same.json() == {
        "detail": "This file is already in the Project as handbook.md.",
        "document_id": original["id"],
        "document_name": "handbook.md",
    }
    (listed,) = await documents(owner, project_id)
    assert (listed["edition"], listed["replacement"]) == (1, None)


@pytest.mark.parametrize("conversion_fails", [False, True])
async def test_a_document_deleted_while_it_is_processing_stays_deleted(
    app: FastAPI, owner: SignedUpMember, conversion_fails: bool
) -> None:
    project_id = await create_project(owner)
    gate = GatedConverter()
    app.state.ingestion.converter = gate
    if conversion_fails:
        gate.failure = RuntimeError("Docling crashed")
    started = (await start_upload(owner, project_id, "handbook.md", len(HANDBOOK))).json()
    await put_to_memory_store(app, started["url"], HANDBOOK, "text/markdown")
    confirming = asyncio.create_task(confirm(owner, project_id, started["upload_id"]))
    await gate.wait_until_started()
    (processing,) = await documents(owner, project_id)
    assert processing["status"] == "processing"

    busy = await replace(app, owner, project_id, processing["id"], "new.md", b"# New")
    deleted = await owner.client.delete(
        f"{project_path(owner, project_id)}/documents/{processing['id']}"
    )
    gate.release.set()
    await confirming

    assert (busy.status_code, busy.json()["detail"]) == (409, BUSY)
    assert deleted.status_code == 204
    assert await documents(owner, project_id) == []
    assert await chunk_rows(app, processing["id"]) == 0
    # Whatever ingestion stored after the delete is deleted too. Only the refused replacement's
    # upload is left, pending, for confirming once the Document is Ready.
    assert stored(app) == [b"# New"]


async def test_an_archived_project_takes_no_replacements_or_deletes(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    original = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    started = (await start_upload(owner, project_id, "new.md", 5)).json()
    await put_to_memory_store(app, started["url"], b"# New", "text/markdown")
    archived = await owner.client.post(f"{project_path(owner, project_id)}/archive")
    assert archived.status_code == 200, archived.text
    document_path = f"{project_path(owner, project_id)}/documents/{original['id']}"

    refused_replace = await owner.client.post(
        f"{document_path}/editions", json={"upload_id": started["upload_id"]}
    )
    refused_delete = await owner.client.delete(document_path)

    message = "This Project is archived. An Owner can restore it."
    assert (refused_replace.status_code, refused_replace.json()["detail"]) == (409, message)
    assert (refused_delete.status_code, refused_delete.json()["detail"]) == (409, message)
    (listed,) = await documents(owner, project_id)
    assert (listed["edition"], listed["replacement"]) == (1, None)


async def test_replacing_or_deleting_an_unknown_document_is_not_found(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    unknown = "00000000-0000-4000-8000-000000000000"
    path = f"{project_path(owner, project_id)}/documents/{unknown}"

    answers = [
        await owner.client.post(f"{path}/editions", json={"upload_id": unknown}),
        await owner.client.delete(path),
        await owner.client.delete(f"{project_path(owner, unknown)}/documents/{unknown}"),
    ]

    assert {(a.status_code, a.json()["detail"]) for a in answers} == {(404, "Not found")}


async def test_a_replacement_upload_must_be_confirmed_once_and_match_its_hash(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    original = await upload(app, owner, project_id, "handbook.md", HANDBOOK)
    editions = f"{project_path(owner, project_id)}/documents/{original['id']}/editions"
    started = (await start_upload(owner, project_id, "new.md", 5)).json()

    early = await owner.client.post(editions, json={"upload_id": started["upload_id"]})
    await put_to_memory_store(app, started["url"], b"# New", "text/markdown")
    mismatch = await owner.client.post(
        editions, json={"upload_id": started["upload_id"], "content_hash": "0" * 64}
    )
    unknown = await owner.client.post(
        editions, json={"upload_id": "00000000-0000-4000-8000-000000000000"}
    )

    assert (early.status_code, early.json()["detail"]) == (
        409,
        "The file hasn't reached storage yet. Upload it, then confirm.",
    )
    assert mismatch.status_code == 422
    assert (unknown.status_code, unknown.json()["detail"]) == (
        409,
        "This upload wasn't found or has expired. Start the upload again.",
    )
