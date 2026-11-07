"""Uploading the Theme's logo and default Agent avatar: presign, direct upload, confirm.

1. ``start_upload`` checks the image type (by extension) and the declared size, and answers
   with a presigned PUT URL. The pending upload is remembered in Redis until the URL expires.
2. The browser PUTs the image straight to the object store.
3. ``confirm_upload`` claims the pending upload (only one confirmation can), reads the stored
   bytes and checks them again, because a presigned PUT accepts whatever is sent: the size,
   and that the bytes really are the declared type. A file that fails is deleted. Otherwise
   the image becomes the Theme's, and the one it replaces is deleted from the store.

Only PNG, JPEG and WebP are accepted. SVG is not: it can carry script.
"""

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PurePath

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.port import ObjectNotFoundError, ObjectStore
from app.tenancy.repository import OrganisationScope
from app.theme import service
from app.theme.service import SavedTheme, StoredImage, ThemeImageKind

# The image types a Theme image can be, by extension, with the MIME type stored.
IMAGE_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
# How people know each type, for messages.
TYPE_NAMES = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WebP"}

_PENDING = "theme-image-upload:{organisation}:{kind}:{upload_id}"


class UnsupportedImageTypeError(Exception):
    """The file's extension isn't a PNG, JPEG or WebP one."""


class ImageTooLargeError(Exception):
    """The image is larger than the Theme image limit."""


class UploadNotFoundError(Exception):
    """No pending upload with that ID for this image: unknown, expired or already used."""


class ImageNotUploadedError(Exception):
    """The object store has nothing under the upload's key yet."""


class NotDeclaredTypeError(Exception):
    """The stored bytes aren't an image of the type the upload was started for."""

    def __init__(self, content_type: str) -> None:
        super().__init__(content_type)
        self.type_name = TYPE_NAMES[content_type]


class ImageNotFoundError(Exception):
    """The Theme has no such image."""


def _is_type(data: bytes, content_type: str) -> bool:
    """Whether ``data`` starts with the signature of ``content_type``."""
    if content_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


@dataclass(frozen=True)
class PendingUpload:
    upload_id: uuid.UUID
    url: str
    content_type: str
    expires_at: datetime


def _pending_key(scope: OrganisationScope, kind: ThemeImageKind, upload_id: uuid.UUID) -> str:
    return _PENDING.format(organisation=scope.organisation_id, kind=kind.value, upload_id=upload_id)


async def start_upload(
    redis: Redis,
    store: ObjectStore,
    scope: OrganisationScope,
    kind: ThemeImageKind,
    *,
    filename: str,
    size_bytes: int,
    max_bytes: int,
    ttl_seconds: int,
    now: datetime,
) -> PendingUpload:
    return await start_image_upload(
        redis,
        store,
        pending_key=lambda upload_id: _pending_key(scope, kind, upload_id),
        object_prefix=f"organisations/{scope.organisation_id}/theme/{kind.value}",
        filename=filename,
        size_bytes=size_bytes,
        max_bytes=max_bytes,
        ttl_seconds=ttl_seconds,
        now=now,
    )


async def start_image_upload(
    redis: Redis,
    store: ObjectStore,
    *,
    pending_key: Callable[[uuid.UUID], str],
    object_prefix: str,
    filename: str,
    size_bytes: int,
    max_bytes: int,
    ttl_seconds: int,
    now: datetime,
) -> PendingUpload:
    """Starts the upload of an image (a Theme's, or an Agent's avatar): checks its type and
    size, remembers it under ``pending_key`` and presigns a PUT under ``object_prefix``."""
    try:
        content_type = IMAGE_TYPES[PurePath(filename).suffix.lower()]
    except KeyError:
        raise UnsupportedImageTypeError from None
    if size_bytes > max_bytes:
        raise ImageTooLargeError
    upload_id = uuid.uuid4()
    object_key = f"{object_prefix}/{upload_id}"
    pending = {"content_type": content_type, "object_key": object_key}
    await redis.set(pending_key(upload_id), json.dumps(pending), ex=ttl_seconds)
    url = store.presign_put(object_key, content_type=content_type, expires_in=ttl_seconds)
    return PendingUpload(
        upload_id=upload_id,
        url=url,
        content_type=content_type,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )


async def confirm_upload(
    session: AsyncSession,
    redis: Redis,
    store: ObjectStore,
    scope: OrganisationScope,
    kind: ThemeImageKind,
    *,
    upload_id: uuid.UUID,
    max_bytes: int,
    now: datetime,
) -> SavedTheme:
    """Makes the uploaded image the Theme's, replacing (and deleting) the one it had."""
    image = await claim_upload(
        redis, store, _pending_key(scope, kind, upload_id), max_bytes=max_bytes, now=now
    )
    change = await service.set_image(session, scope, kind, image, now=now)
    if change.replaced is not None and change.replaced.object_key != image.object_key:
        await store.delete(change.replaced.object_key)
    return change.theme


async def claim_upload(
    redis: Redis, store: ObjectStore, key: str, *, max_bytes: int, now: datetime
) -> StoredImage:
    """Claims the pending upload under ``key`` and checks the stored file is an image of its
    declared type within ``max_bytes``; a file that fails is deleted."""
    # Claim the upload: read and remove it in one step, so two confirmations of it at once
    # can't both use it (the second would take the first's image as the one it replaces, and
    # delete the file both point to).
    async with redis.pipeline(transaction=True) as claim:
        claim.get(key)
        claim.pttl(key)
        claim.delete(key)
        raw, ttl_ms, _ = await claim.execute()
    if raw is None:
        raise UploadNotFoundError
    pending = json.loads(raw)
    object_key: str = pending["object_key"]
    content_type: str = pending["content_type"]
    try:
        # The size first, from the store's metadata: a file far over the limit is never read.
        size_bytes = await store.size(object_key)
    except ObjectNotFoundError:
        # Not uploaded yet: give the claim back, for a confirmation once the file arrives. The
        # claim read the key and its time left together, so that time is always positive.
        await redis.set(key, raw, px=ttl_ms, nx=True)
        raise ImageNotUploadedError from None
    if size_bytes > max_bytes:
        await store.delete(object_key)
        raise ImageTooLargeError
    data = await store.get(object_key)
    if len(data) > max_bytes or not _is_type(data, content_type):
        # Over the limit here only if the file was replaced since its size was read.
        await store.delete(object_key)
        if len(data) > max_bytes:
            raise ImageTooLargeError
        raise NotDeclaredTypeError(content_type)
    return StoredImage(
        object_key=object_key,
        content_type=content_type,
        size_bytes=len(data),
        content_hash=hashlib.sha256(data).hexdigest(),
        uploaded_at=now,
    )


async def remove_image(
    session: AsyncSession,
    store: ObjectStore,
    scope: OrganisationScope,
    kind: ThemeImageKind,
    *,
    now: datetime,
) -> SavedTheme:
    change = await service.set_image(session, scope, kind, None, now=now)
    if change.replaced is not None:
        await store.delete(change.replaced.object_key)
    return change.theme


@dataclass(frozen=True)
class ImageFile:
    data: bytes
    content_type: str


async def read_image(
    session: AsyncSession, store: ObjectStore, scope: OrganisationScope, kind: ThemeImageKind
) -> ImageFile:
    return await read_stored(store, (await service.read_theme(session, scope)).images[kind])


async def read_stored(store: ObjectStore, image: StoredImage | None) -> ImageFile:
    """The stored image's bytes; ``ImageNotFoundError`` when there is none or it is missing."""
    if image is None:
        raise ImageNotFoundError
    try:
        data = await store.get(image.object_key)
    except ObjectNotFoundError:
        raise ImageNotFoundError from None
    return ImageFile(data, image.content_type)
