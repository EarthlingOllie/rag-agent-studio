"""Theme routes: every Member reads the Theme, Owners replace it; Owners upload, replace and
remove its logo and default avatar, which every Member can fetch; and the font allowlist."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, StringConstraints
from redis.asyncio import Redis

from app.auth.api import Db, ErrorResponse
from app.core.clock import Clock, get_clock
from app.core.settings import Settings
from app.storage.port import ObjectStore
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY, OwnerScope, Scope
from app.theme import images, service
from app.theme.fonts import FONT_ALLOWLIST, Font, FontCategory
from app.theme.schema import ThemeSettings
from app.theme.service import StoredImage, ThemeImageKind

router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["theme"])
fonts_router = APIRouter(prefix="/api/themes", tags=["theme"])

ClockDep = Annotated[Clock, Depends(get_clock)]

UNSUPPORTED_IMAGE = "Upload a PNG, JPEG or WebP image."
UPLOAD_NOT_FOUND = "This upload wasn't found or has expired. Start the upload again."
IMAGE_NOT_UPLOADED = "The image hasn't reached storage yet. Upload it, then save."
# Image URLs carry the image's content hash, so a URL always names the same bytes.
IMAGE_CACHE_CONTROL = "private, max-age=31536000, immutable"


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


def _store(request: Request) -> ObjectStore:
    store: ObjectStore = request.app.state.ingestion.object_store
    return store


SettingsDep = Annotated[Settings, Depends(_settings)]
RedisDep = Annotated[Redis, Depends(_redis)]
StoreDep = Annotated[ObjectStore, Depends(_store)]

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": NOT_FOUND}
}


class ThemeImageOut(BaseModel):
    # Where any Member fetches the image; it changes whenever the image does.
    url: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime


class ThemeOut(ThemeSettings):
    updated_at: datetime | None
    # The logo shown in the widget's header, if one was uploaded.
    logo: ThemeImageOut | None
    # The default Agent avatar, if one was uploaded.
    avatar: ThemeImageOut | None


class StartImageUploadRequest(BaseModel):
    filename: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    size_bytes: int = Field(ge=0)


class StartImageUploadResponse(BaseModel):
    upload_id: uuid.UUID
    # PUT the image's bytes here, with the given Content-Type header, before ``expires_at``.
    url: str
    method: str = "PUT"
    content_type: str
    expires_at: datetime


class ConfirmImageUploadRequest(BaseModel):
    upload_id: uuid.UUID


class FontOut(BaseModel):
    family: Font
    category: FontCategory


def _image_out(
    scope_organisation: uuid.UUID, kind: ThemeImageKind, image: StoredImage | None
) -> ThemeImageOut | None:
    if image is None:
        return None
    return ThemeImageOut(
        url=f"{ORGANISATION_PREFIX.format(organisation_id=scope_organisation)}/theme/images/"
        f"{kind.value}?v={image.content_hash[:16]}",
        content_type=image.content_type,
        size_bytes=image.size_bytes,
        uploaded_at=image.uploaded_at,
    )


def _out(saved: service.SavedTheme, organisation_id: uuid.UUID) -> ThemeOut:
    return ThemeOut(
        **saved.settings.model_dump(),
        updated_at=saved.updated_at,
        logo=_image_out(organisation_id, ThemeImageKind.LOGO, saved.images[ThemeImageKind.LOGO]),
        avatar=_image_out(
            organisation_id, ThemeImageKind.AVATAR, saved.images[ThemeImageKind.AVATAR]
        ),
    )


def image_too_large(settings: Settings) -> str:
    return f"Images can be up to {settings.max_theme_image_bytes // (1024 * 1024)} MB."


@router.get("/theme", responses=_NOT_FOUND, operation_id="getTheme")
async def get_theme(scope: Scope, db: Db) -> ThemeOut:
    """The Organisation's Theme; the default until an Owner saves one. Any Member can read it."""
    return _out(await service.read_theme(db, scope), scope.organisation_id)


@router.put(
    "/theme",
    responses={403: {"model": ErrorResponse, "description": OWNERS_ONLY}, **_NOT_FOUND},
    operation_id="saveTheme",
)
async def save_theme(body: ThemeSettings, scope: OwnerScope, db: Db, clock: ClockDep) -> ThemeOut:
    """Replaces the Theme's settings; its images stay. It applies at once. Colours that fail
    contrast are saved: the Studio warns about them but never blocks."""
    return _out(await service.save_theme(db, scope, body, now=clock.now()), scope.organisation_id)


_OWNERS_ONLY = (403, OWNERS_ONLY)


def _errors(*codes: tuple[int, str]) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ErrorResponse, "description": text} for code, text in codes}


@router.post(
    "/theme/images/{kind}/uploads",
    status_code=status.HTTP_201_CREATED,
    operation_id="startThemeImageUpload",
    responses=_errors(
        _OWNERS_ONLY,
        (404, NOT_FOUND),
        (413, "The image is larger than the Theme image limit."),
        (415, UNSUPPORTED_IMAGE),
    ),
)
async def start_image_upload(
    kind: ThemeImageKind,
    body: StartImageUploadRequest,
    scope: OwnerScope,
    redis: RedisDep,
    store: StoreDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> StartImageUploadResponse:
    """Checks the image type (PNG, JPEG or WebP) and size, then answers with a presigned URL to
    PUT the image to."""
    try:
        pending = await images.start_upload(
            redis,
            store,
            scope,
            kind,
            filename=body.filename,
            size_bytes=body.size_bytes,
            max_bytes=settings.max_theme_image_bytes,
            ttl_seconds=settings.upload_url_ttl_seconds,
            now=clock.now(),
        )
    except images.UnsupportedImageTypeError:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, UNSUPPORTED_IMAGE) from None
    except images.ImageTooLargeError:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, image_too_large(settings)) from None
    return StartImageUploadResponse(
        upload_id=pending.upload_id,
        url=pending.url,
        content_type=pending.content_type,
        expires_at=pending.expires_at,
    )


@router.put(
    "/theme/images/{kind}",
    operation_id="confirmThemeImageUpload",
    responses=_errors(
        _OWNERS_ONLY,
        (404, NOT_FOUND),
        (409, f"{IMAGE_NOT_UPLOADED} / {UPLOAD_NOT_FOUND}"),
        (422, "The stored file isn't an image of the declared type, or is too large."),
    ),
)
async def confirm_image_upload(
    kind: ThemeImageKind,
    body: ConfirmImageUploadRequest,
    scope: OwnerScope,
    db: Db,
    redis: RedisDep,
    store: StoreDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> ThemeOut:
    """Checks the uploaded image and makes it the Theme's logo or avatar, replacing the one it
    had. It applies at once and is recorded as ``theme.updated``."""
    try:
        saved = await images.confirm_upload(
            db,
            redis,
            store,
            scope,
            kind,
            upload_id=body.upload_id,
            max_bytes=settings.max_theme_image_bytes,
            now=clock.now(),
        )
    except images.UploadNotFoundError:
        raise HTTPException(status.HTTP_409_CONFLICT, UPLOAD_NOT_FOUND) from None
    except images.ImageNotUploadedError:
        raise HTTPException(status.HTTP_409_CONFLICT, IMAGE_NOT_UPLOADED) from None
    except images.ImageTooLargeError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, image_too_large(settings)
        ) from None
    except images.NotDeclaredTypeError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"The file isn't a {error.type_name} image. Upload it again.",
        ) from None
    return _out(saved, scope.organisation_id)


@router.delete(
    "/theme/images/{kind}",
    operation_id="removeThemeImage",
    responses=_errors(_OWNERS_ONLY, (404, NOT_FOUND)),
)
async def remove_image(
    kind: ThemeImageKind, scope: OwnerScope, db: Db, store: StoreDep, clock: ClockDep
) -> ThemeOut:
    """Removes the Theme's logo or avatar and deletes its file. Removing one there is none of
    changes nothing."""
    saved = await images.remove_image(db, store, scope, kind, now=clock.now())
    return _out(saved, scope.organisation_id)


@router.get(
    "/theme/images/{kind}",
    operation_id="getThemeImage",
    response_class=Response,
    responses={
        200: {"content": {t: {} for t in images.TYPE_NAMES}, "description": "The image."},
        **_NOT_FOUND,
    },
)
async def get_image(kind: ThemeImageKind, scope: Scope, db: Db, store: StoreDep) -> Response:
    """The Theme's logo or avatar itself. Any Member can fetch it."""
    try:
        image = await images.read_image(db, store, scope, kind)
    except images.ImageNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND) from None
    return Response(
        image.data,
        media_type=image.content_type,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": IMAGE_CACHE_CONTROL},
    )


@fonts_router.get("/fonts", operation_id="listThemeFonts")
async def list_fonts() -> list[FontOut]:
    """The Google Fonts a Theme may use, the default first."""
    return [FontOut(family=font.family, category=font.category) for font in FONT_ALLOWLIST]
