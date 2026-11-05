"""API seam: the Theme's logo and default Agent avatar.

Owners upload each image through a presigned upload to the object store (the in-memory fake
here; RustFS in ``test_object_store.py``), restricted by image type and size. Every Member
reads the Theme with each image's URL and fetches the image from it. Images can be replaced
and removed, and every change is a ``theme.updated`` Audit Event.
"""

import hashlib
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI

from app.storage.memory import InMemoryObjectStore
from tests import theme_images as images
from tests.conftest import MemberFactory, SignedUpMember
from tests.fakes.clock import ControllableClock
from tests.theme_images import JPEG, WEBP, png


def iso(clock: ControllableClock) -> str:
    return clock.now().isoformat().replace("+00:00", "Z")


async def theme_of(member: SignedUpMember) -> dict[str, Any]:
    response = await member.client.get(f"/api/organisations/{member.organisation_id}/theme")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def theme_events(owner: SignedUpMember) -> list[dict[str, Any]]:
    response = await owner.client.get(
        f"/api/organisations/{owner.organisation_id}/audit-events",
        params={"action": "theme.updated"},
    )
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def stored_objects(app: FastAPI) -> dict[str, tuple[bytes, str]]:
    store = app.state.ingestion.object_store
    assert isinstance(store, InMemoryObjectStore)
    return store.objects


# Uploading


async def test_a_new_theme_has_no_logo_or_avatar(owner: SignedUpMember) -> None:
    theme = await theme_of(owner)

    assert (theme["logo"], theme["avatar"]) == (None, None)


@pytest.mark.parametrize("kind", ["logo", "avatar"])
async def test_an_owner_uploads_an_image_through_a_presigned_upload_and_every_member_sees_it(
    kind: str, owner: SignedUpMember, member_factory: MemberFactory, clock: ControllableClock
) -> None:
    data = png()
    started = await images.start(owner, kind, "Brand Mark.PNG", len(data))

    assert started.status_code == 201, started.text
    ticket = started.json()
    assert ticket["method"] == "PUT"
    assert ticket["content_type"] == "image/png"
    assert ticket["url"].startswith("memory://objects/")
    assert ticket["expires_at"] == (clock.now() + timedelta(minutes=15)).isoformat().replace(
        "+00:00", "Z"
    )
    await images.put_file(owner, ticket, data)

    confirmed = await images.confirm(owner, kind, ticket["upload_id"])

    assert confirmed.status_code == 200, confirmed.text
    image = confirmed.json()[kind]
    digest = hashlib.sha256(data).hexdigest()
    assert image == {
        "url": f"/api/organisations/{owner.organisation_id}/theme/images/{kind}?v={digest[:16]}",
        "content_type": "image/png",
        "size_bytes": len(data),
        "uploaded_at": iso(clock),
    }
    assert confirmed.json()["updated_at"] == iso(clock)
    # Every Member sees it in the Theme, and fetches the image itself from its URL.
    editor = await member_factory(owner, "editor")
    assert (await theme_of(editor))[kind] == image
    fetched = await editor.client.get(image["url"])
    assert fetched.status_code == 200
    assert fetched.content == data
    assert fetched.headers["content-type"] == "image/png"
    assert fetched.headers["x-content-type-options"] == "nosniff"
    assert fetched.headers["cache-control"] == "private, max-age=31536000, immutable"


async def test_the_logo_and_the_avatar_are_separate_images(owner: SignedUpMember) -> None:
    await images.upload(owner, "logo", png(255, 0, 0))
    await images.upload(owner, "avatar", JPEG, "face.jpg")

    theme = await theme_of(owner)
    logo = await owner.client.get(theme["logo"]["url"])
    avatar = await owner.client.get(theme["avatar"]["url"])

    assert (logo.content, avatar.content) == (png(255, 0, 0), JPEG)
    assert (theme["logo"]["content_type"], theme["avatar"]["content_type"]) == (
        "image/png",
        "image/jpeg",
    )


@pytest.mark.parametrize(
    ("filename", "data", "content_type"),
    [
        ("logo.png", png(), "image/png"),
        ("logo.jpg", JPEG, "image/jpeg"),
        ("logo.JPEG", JPEG, "image/jpeg"),
        ("logo.webp", WEBP, "image/webp"),
    ],
)
async def test_png_jpeg_and_webp_images_are_accepted(
    owner: SignedUpMember, filename: str, data: bytes, content_type: str
) -> None:
    theme = await images.upload(owner, "logo", data, filename)

    assert theme["logo"]["content_type"] == content_type
    assert (await owner.client.get(theme["logo"]["url"])).headers["content-type"] == content_type


@pytest.mark.parametrize("filename", ["logo.svg", "logo.gif", "logo.pdf", "logo"])
async def test_other_file_types_are_refused_before_upload(
    owner: SignedUpMember, filename: str
) -> None:
    response = await images.start(owner, "logo", filename, 100)

    assert response.status_code == 415
    assert response.json() == {"detail": "Upload a PNG, JPEG or WebP image."}


async def test_an_image_over_the_size_limit_is_refused_before_upload(
    owner: SignedUpMember,
) -> None:
    limit = 1024 * 1024
    assert (await images.start(owner, "avatar", "a.png", limit)).status_code == 201

    response = await images.start(owner, "avatar", "a.png", limit + 1)

    assert response.status_code == 413
    assert response.json() == {"detail": "Images can be up to 1 MB."}


async def test_a_stored_file_that_is_not_the_declared_image_type_is_refused_and_removed(
    app: FastAPI, owner: SignedUpMember
) -> None:
    # A presigned PUT can't check what is sent, so confirming checks the stored bytes.
    ticket = await images.uploaded_ticket(owner, "logo", b"<svg onload=alert(1)>", "logo.png")

    response = await images.confirm(owner, "logo", ticket["upload_id"])

    assert response.status_code == 422
    assert response.json() == {"detail": "The file isn't a PNG image. Upload it again."}
    assert (await theme_of(owner))["logo"] is None
    assert stored_objects(app) == {}
    assert await theme_events(owner) == []


async def test_a_jpeg_named_png_is_refused(owner: SignedUpMember) -> None:
    ticket = await images.uploaded_ticket(owner, "logo", JPEG, "logo.png")

    response = await images.confirm(owner, "logo", ticket["upload_id"])

    assert response.status_code == 422


async def test_a_stored_file_over_the_size_limit_is_refused_and_removed(
    app: FastAPI, owner: SignedUpMember
) -> None:
    # The browser declared a small file but PUT a large one.
    started = await images.start(owner, "logo", "logo.png", 10)
    ticket = started.json()
    await images.put_file(owner, ticket, png() + bytes(1024 * 1024))

    response = await images.confirm(owner, "logo", ticket["upload_id"])

    assert response.status_code == 422
    assert response.json() == {"detail": "Images can be up to 1 MB."}
    assert stored_objects(app) == {}
    assert (await theme_of(owner))["logo"] is None


async def test_an_upload_is_confirmed_only_once_after_the_file_arrives(
    owner: SignedUpMember,
) -> None:
    started = await images.start(owner, "logo", "logo.png", 100)
    ticket = started.json()

    early = await images.confirm(owner, "logo", ticket["upload_id"])
    assert early.status_code == 409
    assert early.json() == {"detail": "The image hasn't reached storage yet. Upload it, then save."}

    await images.put_file(owner, ticket, png())
    assert (await images.confirm(owner, "logo", ticket["upload_id"])).status_code == 200

    again = await images.confirm(owner, "logo", ticket["upload_id"])
    assert again.status_code == 409
    assert again.json() == {
        "detail": "This upload wasn't found or has expired. Start the upload again."
    }


async def test_an_upload_is_confirmed_only_as_the_image_it_was_started_for(
    owner: SignedUpMember,
) -> None:
    ticket = await images.uploaded_ticket(owner, "logo", png())

    response = await images.confirm(owner, "avatar", ticket["upload_id"])

    assert response.status_code == 409
    assert (await theme_of(owner))["avatar"] is None


async def test_an_unknown_image_kind_is_refused(owner: SignedUpMember) -> None:
    response = await images.start(owner, "banner", "a.png", 10)

    assert response.status_code == 422


async def test_an_image_that_was_never_uploaded_is_not_found(owner: SignedUpMember) -> None:
    response = await owner.client.get(images.images_path(owner, "logo"))

    assert (response.status_code, response.json()) == (404, {"detail": "Not found"})


# Replacing and removing


async def test_replacing_an_image_serves_the_new_one_and_removes_the_old_one(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    first = await images.upload(owner, "logo", png(255, 0, 0))
    clock.advance(60)

    second = await images.upload(owner, "logo", png(0, 0, 255))

    assert second["logo"]["url"] != first["logo"]["url"]
    assert second["logo"]["uploaded_at"] == iso(clock)
    assert (await owner.client.get(second["logo"]["url"])).content == png(0, 0, 255)
    # Only the new file is kept.
    assert [data for data, _ in stored_objects(app).values()] == [png(0, 0, 255)]


async def test_removing_an_image_clears_it_and_deletes_the_file(
    app: FastAPI, owner: SignedUpMember, clock: ControllableClock
) -> None:
    await images.upload(owner, "avatar", png())
    await images.upload(owner, "logo", png(1, 2, 3))
    clock.advance(60)

    removed = await owner.client.delete(images.images_path(owner, "avatar"))

    assert removed.status_code == 200, removed.text
    assert removed.json()["avatar"] is None
    assert removed.json()["logo"] is not None
    assert removed.json()["updated_at"] == iso(clock)
    assert (await theme_of(owner))["avatar"] is None
    assert (await owner.client.get(images.images_path(owner, "avatar"))).status_code == 404
    assert [data for data, _ in stored_objects(app).values()] == [png(1, 2, 3)]


async def test_removing_an_image_there_is_none_of_changes_nothing(owner: SignedUpMember) -> None:
    removed = await owner.client.delete(images.images_path(owner, "logo"))

    assert removed.status_code == 200
    assert removed.json()["logo"] is None
    assert removed.json()["updated_at"] is None
    assert await theme_events(owner) == []


async def test_images_are_kept_when_the_rest_of_the_theme_is_saved(owner: SignedUpMember) -> None:
    uploaded = await images.upload(owner, "logo", png())
    theme = await theme_of(owner)
    settings = {
        key: value for key, value in theme.items() if key not in {"updated_at", "logo", "avatar"}
    }

    saved = await owner.client.put(
        f"/api/organisations/{owner.organisation_id}/theme", json=settings | {"radius": 2}
    )

    assert saved.status_code == 200, saved.text
    assert saved.json()["logo"] == uploaded["logo"]
    assert saved.json()["radius"] == 2


async def test_an_image_uploaded_before_any_theme_save_keeps_the_default_theme(
    owner: SignedUpMember,
) -> None:
    before = await theme_of(owner)

    await images.upload(owner, "avatar", png())

    after = await theme_of(owner)
    ignored = {"updated_at", "avatar"}
    assert {k: v for k, v in after.items() if k not in ignored} == {
        k: v for k, v in before.items() if k not in ignored
    }


# Auditing


async def test_uploads_replacements_and_removals_are_audit_events(
    owner: SignedUpMember, clock: ControllableClock
) -> None:
    first, second = png(255, 0, 0), png(0, 255, 0)
    await images.upload(owner, "logo", first)
    clock.advance(1)
    await images.upload(owner, "logo", second)
    clock.advance(1)
    await owner.client.delete(images.images_path(owner, "logo"))

    events = await theme_events(owner)

    def described(data: bytes) -> dict[str, Any]:
        return {
            "content_type": "image/png",
            "size_bytes": len(data),
            "content_hash": hashlib.sha256(data).hexdigest(),
        }

    # Newest first.
    assert [(e["before"], e["after"]) for e in events] == [
        ({"logo": described(second)}, {"logo": None}),
        ({"logo": described(first)}, {"logo": described(second)}),
        ({"logo": None}, {"logo": described(first)}),
    ]
    assert {e["actor"]["id"] for e in events} == {owner.member_id}
    assert {e["target"]["type"] for e in events} == {"theme"}
    assert [e["occurred_at"] for e in events] == [
        iso(clock),
        (clock.now() - timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
        (clock.now() - timedelta(seconds=2)).isoformat().replace("+00:00", "Z"),
    ]


# Who can do what


async def test_editors_view_images_but_cannot_upload_or_remove_them(
    owner: SignedUpMember, member_factory: MemberFactory
) -> None:
    await images.upload(owner, "logo", png())
    editor = await member_factory(owner, "editor")

    started = await images.start(editor, "avatar", "a.png", 10)
    removed = await editor.client.delete(images.images_path(owner, "logo"))
    confirmed = await editor.client.put(
        images.images_path(owner, "logo"),
        json={"upload_id": "00000000-0000-4000-8000-000000000000"},
    )

    assert {r.status_code for r in (started, removed, confirmed)} == {403}
    assert (await theme_of(editor))["logo"] is not None


async def test_an_upload_is_confirmed_only_in_its_own_organisation(
    owner: SignedUpMember, tenant_factory: Any
) -> None:
    other = await tenant_factory()
    ticket = await images.uploaded_ticket(owner, "logo", png())

    response = await images.confirm(other, "logo", ticket["upload_id"])

    assert response.status_code == 409
    assert (await theme_of(other))["logo"] is None
