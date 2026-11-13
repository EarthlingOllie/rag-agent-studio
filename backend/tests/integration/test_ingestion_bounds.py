"""KB-F4: ingestion is bounded. A run that takes too long fails with a readable message, a file
whose converted text is too long fails before it is chunked or embedded, the worker task has a
hard time limit behind that, and a Document deleted while it is processed stops being processed
at the next stage instead of running to the end. API seam plus task seam (eager tasks)."""

import asyncio
import re
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from docling_core.types.doc.document import DoclingDocument
from fastapi import FastAPI

from app.documents import limits, tasks
from app.documents.converter import FakeConverter
from app.embeddings.fake import HashEmbedder
from tests.conftest import SignedUpMember
from tests.documents import (
    confirm,
    create_project,
    documents,
    project_path,
    put_to_memory_store,
    start_upload,
    upload,
)
from tests.integration.test_document_editions import GatedConverter

HANDBOOK = b"# Handbook\n\nEveryone gets 25 days of annual leave a year."
LOCAL_MODEL = "multilingual-e5-small"
# Enough sections for more than one embedding batch (32 Chunks).
LONG_HANDBOOK = "\n\n".join(
    f"# Section {n}\n\nRule number {n} of the handbook says something different." for n in range(80)
).encode()


def failure_of(document: dict[str, Any]) -> tuple[str, str | None, str | None]:
    return document["status"], document["error_category"], document["error_message"]


class SlowConverter(FakeConverter):
    """Takes ``seconds`` to convert, like Docling on a huge PDF."""

    def __init__(self, seconds: float) -> None:
        super().__init__()
        self.seconds = seconds

    def convert(self, data: bytes, filename: str, *, ocr: bool) -> DoclingDocument:
        time.sleep(self.seconds)
        return super().convert(data, filename, ocr=ocr)


class CountingEmbedder(HashEmbedder):
    """Counts the batches it embeds; with ``gate``, holds the first batch until released."""

    def __init__(self, *, gate: bool = False) -> None:
        super().__init__()
        self.batches = 0
        self.gate = gate
        self.started = threading.Event()
        self.release = threading.Event()

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        self.batches += 1
        if self.gate and self.batches == 1:
            self.started.set()
            assert await asyncio.to_thread(self.release.wait, 10)
        return await super().embed_passages(texts)


async def _confirm_in_background(
    app: FastAPI, owner: SignedUpMember, project_id: str, data: bytes
) -> asyncio.Task[Any]:
    started = (await start_upload(owner, project_id, "handbook.md", len(data))).json()
    await put_to_memory_store(app, started["url"], data, "text/markdown")
    return asyncio.create_task(confirm(owner, project_id, started["upload_id"]))


async def _delete_only_document(owner: SignedUpMember, project_id: str) -> None:
    (listed,) = await documents(owner, project_id)
    deleted = await owner.client.delete(
        f"{project_path(owner, project_id)}/documents/{listed['id']}"
    )
    assert deleted.status_code == 204, deleted.text


async def test_ingestion_that_runs_too_long_fails_with_a_readable_message(
    app: FastAPI, owner: SignedUpMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tasks, "INGEST_MAX_SECONDS", 0.2)
    project_id = await create_project(owner)
    app.state.ingestion.converter = SlowConverter(1.0)

    await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    (listed,) = await documents(owner, project_id)
    assert failure_of(listed) == (
        "failed",
        "conversion",
        "Processing this file took too long, so it was stopped. Split it into smaller files, "
        "then upload them.",
    )
    assert listed["chunk_count"] == 0


def test_the_worker_kills_an_ingestion_task_soon_after_its_processing_limit() -> None:
    assert tasks.INGEST_MAX_SECONDS == 20 * 60
    assert tasks.ingest_document.time_limit == tasks.INGEST_MAX_SECONDS + 60


async def test_a_file_whose_converted_text_is_too_long_fails_before_it_is_embedded(
    app: FastAPI, owner: SignedUpMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(limits, "MAX_CONVERTED_CHARS", 40)
    project_id = await create_project(owner)
    embedder = CountingEmbedder()
    app.state.ingestion.embedders[LOCAL_MODEL] = embedder

    await upload(app, owner, project_id, "handbook.md", HANDBOOK)

    (listed,) = await documents(owner, project_id)
    assert failure_of(listed) == (
        "failed",
        "unsupported_content",
        "This file has more text than one Document can hold. Split it into smaller files, "
        "then upload them.",
    )
    assert embedder.batches == 0


def test_the_converted_text_limit_is_ten_million_characters() -> None:
    assert limits.MAX_CONVERTED_CHARS == 10_000_000


async def test_a_document_deleted_while_it_is_converted_is_never_embedded(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    converter = GatedConverter()
    app.state.ingestion.converter = converter
    embedder = CountingEmbedder()
    app.state.ingestion.embedders[LOCAL_MODEL] = embedder
    running = await _confirm_in_background(app, owner, project_id, HANDBOOK)
    await converter.wait_until_started()

    await _delete_only_document(owner, project_id)
    converter.release.set()
    await running

    assert embedder.batches == 0
    assert app.state.ingestion.object_store.objects == {}


async def test_a_document_deleted_while_it_is_embedded_stops_after_the_current_batch(
    app: FastAPI, owner: SignedUpMember
) -> None:
    project_id = await create_project(owner)
    embedder = CountingEmbedder(gate=True)
    app.state.ingestion.embedders[LOCAL_MODEL] = embedder
    running = await _confirm_in_background(app, owner, project_id, LONG_HANDBOOK)
    assert await asyncio.to_thread(embedder.started.wait, 10)

    await _delete_only_document(owner, project_id)
    embedder.release.set()
    await running

    assert embedder.batches == 1
    assert await documents(owner, project_id) == []
    assert app.state.ingestion.object_store.objects == {}


def test_the_compose_worker_has_a_memory_limit() -> None:
    compose = (Path(__file__).parents[3] / "docker-compose.yml").read_text()
    # The worker service's block: from its name to the next service at the same indent.
    worker = re.search(r"^  worker:\n(.*?)(?=^  \S)", compose, re.MULTILINE | re.DOTALL)

    assert worker is not None
    assert re.search(r"^    mem_limit: 6g$", worker[1], re.MULTILINE)
