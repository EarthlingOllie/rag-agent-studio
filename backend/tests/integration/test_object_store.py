"""The object-store port: the S3 adapter against RustFS, and the in-memory fake, behave alike.
And the whole upload flow works against RustFS, with the browser's PUT to a presigned URL."""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from botocore.exceptions import ClientError
from fastapi import FastAPI

from app.main import create_app
from app.storage.memory import InMemoryObjectStore
from app.storage.port import ObjectNotFoundError, ObjectStore
from app.storage.s3 import S3ObjectStore
from tests.conftest import BASE_URL, new_member_details
from tests.theme_images import png

RUSTFS_URL = os.environ.get("TEST_OBJECT_STORE_URL", "http://localhost:9000")
RUSTFS_KEYS = {"access_key_id": "studio", "secret_access_key": "studio-secret"}
BUCKET = "studio-documents-test"


def rustfs(bucket: str = BUCKET, **overrides: str) -> S3ObjectStore:
    keys = RUSTFS_KEYS | overrides
    return S3ObjectStore(
        bucket=bucket,
        endpoint_url=RUSTFS_URL,
        public_endpoint_url=None,
        region="us-east-1",
        access_key_id=keys["access_key_id"],
        secret_access_key=keys["secret_access_key"],
    )


@pytest.fixture(params=["rustfs", "memory"])
async def store(request: pytest.FixtureRequest) -> ObjectStore:
    chosen: ObjectStore = rustfs() if request.param == "rustfs" else InMemoryObjectStore()
    await chosen.prepare()
    return chosen


async def test_an_object_is_stored_read_and_deleted(store: ObjectStore) -> None:
    key = f"tests/{uuid.uuid4()}/handbook.md"

    await store.put(key, b"# Handbook", content_type="text/markdown")
    stored = await store.get(key)
    await store.delete(key)

    assert stored == b"# Handbook"
    with pytest.raises(ObjectNotFoundError):
        await store.get(key)
    await store.delete(key)  # deleting what isn't there is fine


async def test_a_browser_puts_a_file_to_a_presigned_url() -> None:
    store = rustfs()
    await store.prepare()
    key = f"tests/{uuid.uuid4()}/guide.pdf"

    url = store.presign_put(key, content_type="application/pdf", expires_in=60)
    async with httpx.AsyncClient() as browser:
        put = await browser.put(
            url, content=b"%PDF-1.4", headers={"Content-Type": "application/pdf"}
        )

    assert put.status_code == 200, put.text
    assert await store.get(key) == b"%PDF-1.4"


async def test_presigned_urls_are_signed_for_the_public_endpoint() -> None:
    store = S3ObjectStore(
        bucket=BUCKET,
        endpoint_url="http://rustfs:9000",
        public_endpoint_url="http://localhost:5173",
        region="us-east-1",
        **RUSTFS_KEYS,
    )

    url = store.presign_put("a/b.md", content_type="text/markdown", expires_in=60)

    assert url.startswith(f"http://localhost:5173/{BUCKET}/a/b.md?")
    assert "X-Amz-Signature=" in url


async def test_preparing_creates_a_missing_bucket_once() -> None:
    store = rustfs(bucket=f"test-{uuid.uuid4().hex[:12]}")

    await store.prepare()
    await store.prepare()
    await store.put("k", b"v", content_type="text/plain")

    assert await store.get("k") == b"v"


async def test_storage_errors_other_than_a_missing_object_are_raised() -> None:
    store = rustfs(secret_access_key="wrong-secret")  # noqa: S106 - a deliberately wrong key

    with pytest.raises(ClientError):
        await store.prepare()
    with pytest.raises(ClientError):
        await store.get("anything")


@pytest.fixture
async def rustfs_app(
    settings_env: pytest.MonkeyPatch, database_schema: None
) -> AsyncIterator[FastAPI]:
    settings_env.setenv("OBJECT_STORE", "s3")
    settings_env.setenv("OBJECT_STORE_BUCKET", f"test-{uuid.uuid4().hex[:12]}")
    settings_env.setenv("OBJECT_STORE_CREATE_BUCKET", "true")
    settings_env.setenv("OBJECT_STORE_ENDPOINT_URL", RUSTFS_URL)
    settings_env.setenv("OBJECT_STORE_ACCESS_KEY_ID", RUSTFS_KEYS["access_key_id"])
    settings_env.setenv("OBJECT_STORE_SECRET_ACCESS_KEY", RUSTFS_KEYS["secret_access_key"])
    application = create_app()
    async with LifespanManager(application):
        yield application


async def test_a_document_uploaded_through_rustfs_becomes_ready(rustfs_app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=rustfs_app)
    async with (
        httpx.AsyncClient(transport=transport, base_url=BASE_URL) as studio,
        httpx.AsyncClient() as browser,
    ):
        signed_up = (await studio.post("/api/auth/sign-up", json=new_member_details())).json()
        organisation = f"/api/organisations/{signed_up['organisations'][0]['id']}"
        project = (await studio.post(f"{organisation}/projects", json={"name": "HR"})).json()
        documents = f"{organisation}/projects/{project['id']}"
        data = b"# Leave\n\nEveryone gets 25 days."

        started = await studio.post(
            f"{documents}/uploads", json={"filename": "leave.md", "size_bytes": len(data)}
        )
        ticket = started.json()
        put = await browser.put(
            ticket["url"], content=data, headers={"Content-Type": ticket["content_type"]}
        )
        confirmed = await studio.post(
            f"{documents}/documents", json={"upload_id": ticket["upload_id"]}
        )
        listed = (await studio.get(f"{documents}/documents")).json()

    assert (started.status_code, put.status_code, confirmed.status_code) == (201, 200, 201)
    assert [(d["name"], d["status"], d["chunk_count"]) for d in listed] == [
        ("leave.md", "ready", 1)
    ]


async def test_a_theme_logo_uploaded_through_rustfs_is_served_and_replaced(
    rustfs_app: FastAPI,
) -> None:
    first, second = png(255, 0, 0), png(0, 0, 255)
    transport = httpx.ASGITransport(app=rustfs_app)
    async with (
        httpx.AsyncClient(transport=transport, base_url=BASE_URL) as studio,
        httpx.AsyncClient() as browser,
    ):
        signed_up = (await studio.post("/api/auth/sign-up", json=new_member_details())).json()
        logo = f"/api/organisations/{signed_up['organisations'][0]['id']}/theme/images/logo"

        async def upload(data: bytes) -> dict[str, Any]:
            started = await studio.post(
                f"{logo}/uploads", json={"filename": "logo.png", "size_bytes": len(data)}
            )
            ticket = started.json()
            put = await browser.put(
                ticket["url"], content=data, headers={"Content-Type": ticket["content_type"]}
            )
            assert (started.status_code, put.status_code) == (201, 200)
            confirmed = await studio.put(logo, json={"upload_id": ticket["upload_id"]})
            assert confirmed.status_code == 200, confirmed.text
            image: dict[str, Any] = confirmed.json()["logo"]
            return image

        replaced = await upload(first)
        current = await upload(second)
        served = await studio.get(current["url"])
        store = rustfs_app.state.ingestion.object_store
        assert isinstance(store, S3ObjectStore)
        listed = await asyncio.to_thread(store._client.list_objects_v2, Bucket=store.bucket)

    assert replaced["url"] != current["url"]
    assert (served.status_code, served.content) == (200, second)
    # The replaced logo's file is gone from the bucket; only the current one is kept.
    assert [item["Size"] for item in listed["Contents"]] == [len(second)]
