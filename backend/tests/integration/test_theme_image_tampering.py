"""ORG-F2: a presigned image upload URL stays writable until it expires, so the image a confirm
checked must not be the one that is served afterwards. API seam: the "attacker" PUTs to the URL
the Studio was given, after the confirm, as a browser could; the image is fetched through the
API."""

from typing import Any

import pytest
from fastapi import FastAPI

from app.storage.memory import InMemoryObjectStore
from tests import theme_images as images
from tests.conftest import SignedUpMember
from tests.documents import app_of
from tests.theme_images import png

SCRIPT = b"<html><script>alert(document.cookie)</script></html>" + bytes(2 * 1024 * 1024)


def _objects(member: SignedUpMember) -> dict[str, tuple[bytes, str]]:
    app: FastAPI = app_of(member)
    store = app.state.ingestion.object_store
    assert isinstance(store, InMemoryObjectStore)
    return store.objects


async def _confirmed(owner: SignedUpMember, kind: str, data: bytes) -> tuple[dict[str, Any], Any]:
    ticket = await images.uploaded_ticket(owner, kind, data)
    confirmed = await images.confirm(owner, kind, ticket["upload_id"])
    assert confirmed.status_code == 200, confirmed.text
    return ticket, confirmed.json()[kind]


@pytest.mark.parametrize("kind", ["logo", "avatar"])
async def test_a_file_put_to_the_upload_url_after_confirm_is_never_served(
    kind: str, owner: SignedUpMember
) -> None:
    data = png()
    ticket, image = await _confirmed(owner, kind, data)

    # The URL is still within its lifetime: an oversized non-image goes to it.
    await images.put_file(owner, ticket, SCRIPT)

    fetched = await owner.client.get(image["url"])
    assert fetched.status_code == 200
    assert (fetched.content, fetched.headers["content-type"]) == (data, "image/png")


async def test_the_checked_image_is_kept_where_no_upload_url_reaches(
    owner: SignedUpMember,
) -> None:
    data = png()
    ticket, _ = await _confirmed(owner, "logo", data)
    upload_key = ticket["url"].removeprefix("memory://objects/")

    stored = _objects(owner)

    assert upload_key not in stored
    assert [value for value, _ in stored.values()] == [data]
