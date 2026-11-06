"""Helpers for driving the upload flow through the API, as the Studio does."""

from typing import Any
from urllib.parse import unquote, urlsplit

import httpx
from fastapi import FastAPI

from app.storage.memory import InMemoryObjectStore
from tests.conftest import SignedUpMember


def project_path(member: SignedUpMember, project_id: str) -> str:
    return f"/api/organisations/{member.organisation_id}/projects/{project_id}"


async def create_project(member: SignedUpMember, name: str = "Handbook") -> str:
    response = await member.client.post(
        f"/api/organisations/{member.organisation_id}/projects", json={"name": name}
    )
    assert response.status_code == 201, response.text
    project_id: str = response.json()["id"]
    return project_id


async def start_upload(
    member: SignedUpMember,
    project_id: str,
    filename: str,
    size: int,
    *,
    replacing: str | None = None,
) -> httpx.Response:
    """Starts an upload; ``replacing`` names the Document the file will be a new edition of."""
    body: dict[str, Any] = {"filename": filename, "size_bytes": size}
    if replacing is not None:
        body["replacing_document_id"] = replacing
    return await member.client.post(f"{project_path(member, project_id)}/uploads", json=body)


async def put_to_memory_store(app: FastAPI, url: str, data: bytes, content_type: str) -> None:
    """What the browser's PUT to a presigned URL does, for the in-memory object store."""
    store = app.state.ingestion.object_store
    assert isinstance(store, InMemoryObjectStore)
    parts = urlsplit(url)
    assert (parts.scheme, parts.netloc) == ("memory", "objects")
    await store.put(unquote(parts.path.removeprefix("/")), data, content_type=content_type)


def app_of(member: SignedUpMember) -> FastAPI:
    """The app a Member's in-process client talks to."""
    transport = member.client._transport
    assert isinstance(transport, httpx.ASGITransport)
    app = transport.app
    assert isinstance(app, FastAPI)
    return app


async def confirm(
    member: SignedUpMember, project_id: str, upload_id: str, content_hash: str | None = None
) -> httpx.Response:
    body: dict[str, Any] = {"upload_id": upload_id}
    if content_hash is not None:
        body["content_hash"] = content_hash
    return await member.client.post(f"{project_path(member, project_id)}/documents", json=body)


async def upload(
    app: FastAPI, member: SignedUpMember, project_id: str, filename: str, data: bytes
) -> dict[str, Any]:
    """Presign, PUT to the in-memory store, confirm; returns the confirmed Document."""
    started = await start_upload(member, project_id, filename, len(data))
    assert started.status_code == 201, started.text
    ticket = started.json()
    await put_to_memory_store(app, ticket["url"], data, ticket["content_type"])
    confirmed = await confirm(member, project_id, ticket["upload_id"])
    assert confirmed.status_code == 201, confirmed.text
    document: dict[str, Any] = confirmed.json()
    return document


async def documents(member: SignedUpMember, project_id: str) -> list[dict[str, Any]]:
    response = await member.client.get(f"{project_path(member, project_id)}/documents")
    assert response.status_code == 200, response.text
    listed: list[dict[str, Any]] = response.json()
    return listed


async def chunks(member: SignedUpMember, project_id: str, document_id: str) -> list[dict[str, Any]]:
    response = await member.client.get(
        f"{project_path(member, project_id)}/documents/{document_id}/chunks"
    )
    assert response.status_code == 200, response.text
    listed: list[dict[str, Any]] = response.json()
    return listed


async def replace(
    app: FastAPI,
    member: SignedUpMember,
    project_id: str,
    document_id: str,
    filename: str,
    data: bytes,
) -> httpx.Response:
    """Presign, PUT to the in-memory store, then confirm the file as the Document's new
    edition; returns the confirmation's response."""
    started = await start_upload(member, project_id, filename, len(data), replacing=document_id)
    assert started.status_code == 201, started.text
    ticket = started.json()
    await put_to_memory_store(app, ticket["url"], data, ticket["content_type"])
    return await member.client.post(
        f"{project_path(member, project_id)}/documents/{document_id}/editions",
        json={"upload_id": ticket["upload_id"]},
    )
