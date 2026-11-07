"""Theme override routes: every Member reads an Agent's Theme override and fetches its avatar;
Owners change its colours and upload, replace or remove its avatar (presign, PUT, confirm, as
for the Theme's images)."""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel

from app.agents.api import NOT_FOUND_RESPONSE, ClockDep, not_found
from app.agents.service import AgentNotFoundError
from app.auth.api import Db, ErrorResponse
from app.embed import branding
from app.projects.service import ProjectNotFoundError
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY, OwnerScope, Scope
from app.theme import images
from app.theme.api import (
    IMAGE_CACHE_CONTROL,
    IMAGE_NOT_UPLOADED,
    UNSUPPORTED_IMAGE,
    UPLOAD_NOT_FOUND,
    ConfirmImageUploadRequest,
    RedisDep,
    SettingsDep,
    StartImageUploadRequest,
    StartImageUploadResponse,
    StoreDep,
    ThemeImageOut,
    image_too_large,
)
from app.theme.schema import ColourToken
from app.theme.service import StoredImage

AGENT_PREFIX = ORGANISATION_PREFIX + "/projects/{project_id}/agents/{agent_id}"
router = APIRouter(prefix=AGENT_PREFIX + "/theme-override", tags=["embed"])


class ThemeOverrideOut(BaseModel):
    # The colour tokens the Agent overrides; the others follow the Organisation's Theme.
    colours: dict[str, ColourToken]
    # The Agent's own avatar, if one was uploaded.
    avatar: ThemeImageOut | None


def _errors(*codes: tuple[int, str]) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ErrorResponse, "description": text} for code, text in codes}


_OWNERS = _errors((403, OWNERS_ONLY), (404, NOT_FOUND))


def _avatar_out(
    organisation_id: uuid.UUID, project_id: uuid.UUID, agent_id: uuid.UUID, image: StoredImage
) -> ThemeImageOut:
    path = AGENT_PREFIX.format(
        organisation_id=organisation_id, project_id=project_id, agent_id=agent_id
    )
    return ThemeImageOut(
        url=f"{path}/theme-override/avatar?v={image.content_hash[:16]}",
        content_type=image.content_type,
        size_bytes=image.size_bytes,
        uploaded_at=image.uploaded_at,
    )


def _out(
    found: branding.ThemeOverride,
    organisation_id: uuid.UUID,
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
) -> ThemeOverrideOut:
    avatar = found.avatar
    return ThemeOverrideOut(
        colours=found.colours,
        avatar=None
        if avatar is None
        else _avatar_out(organisation_id, project_id, agent_id, avatar),
    )


@router.get("", operation_id="getThemeOverride", responses=NOT_FOUND_RESPONSE)
async def get_theme_override(
    project_id: uuid.UUID, agent_id: uuid.UUID, scope: Scope, db: Db
) -> ThemeOverrideOut:
    """The Agent's Theme override. Any Member can read it."""
    try:
        found = await branding.read_override(db, scope, project_id, agent_id)
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
    return _out(found, scope.organisation_id, project_id, agent_id)


@router.put("", operation_id="setThemeOverrideColours", responses=_OWNERS)
async def set_theme_override_colours(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: branding.ColourOverride,
    scope: OwnerScope,
    db: Db,
    clock: ClockDep,
) -> ThemeOverrideOut:
    """Replaces the colour tokens the Agent overrides (an empty map follows the Theme). It
    applies to the widget at once, without publishing."""
    try:
        found = await branding.set_colours(db, scope, project_id, agent_id, body, now=clock.now())
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
    return _out(found, scope.organisation_id, project_id, agent_id)


@router.post(
    "/avatar/uploads",
    status_code=status.HTTP_201_CREATED,
    operation_id="startAgentAvatarUpload",
    responses=_errors(
        (403, OWNERS_ONLY),
        (404, NOT_FOUND),
        (413, "The image is larger than the Theme image limit."),
        (415, UNSUPPORTED_IMAGE),
    ),
)
async def start_avatar_upload(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: StartImageUploadRequest,
    scope: OwnerScope,
    db: Db,
    redis: RedisDep,
    store: StoreDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> StartImageUploadResponse:
    """Checks the image type (PNG, JPEG or WebP) and size, then answers with a presigned URL to
    PUT the Agent's avatar to."""
    try:
        pending = await branding.start_avatar_upload(
            db,
            redis,
            store,
            scope,
            project_id,
            agent_id,
            filename=body.filename,
            size_bytes=body.size_bytes,
            max_bytes=settings.max_theme_image_bytes,
            ttl_seconds=settings.upload_url_ttl_seconds,
            now=clock.now(),
        )
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
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
    "/avatar",
    operation_id="confirmAgentAvatarUpload",
    responses=_errors(
        (403, OWNERS_ONLY),
        (404, NOT_FOUND),
        (409, f"{IMAGE_NOT_UPLOADED} / {UPLOAD_NOT_FOUND}"),
        (422, "The stored file isn't an image of the declared type, or is too large."),
    ),
)
async def confirm_avatar_upload(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: ConfirmImageUploadRequest,
    scope: OwnerScope,
    db: Db,
    redis: RedisDep,
    store: StoreDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> ThemeOverrideOut:
    """Checks the uploaded image and makes it the Agent's avatar, replacing the one it had. It
    applies to the widget at once."""
    try:
        found = await branding.confirm_avatar_upload(
            db,
            redis,
            store,
            scope,
            project_id,
            agent_id,
            upload_id=body.upload_id,
            max_bytes=settings.max_theme_image_bytes,
            now=clock.now(),
        )
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
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
    return _out(found, scope.organisation_id, project_id, agent_id)


@router.delete("/avatar", operation_id="removeAgentAvatar", responses=_OWNERS)
async def remove_avatar(
    project_id: uuid.UUID,
    agent_id: uuid.UUID,
    scope: OwnerScope,
    db: Db,
    store: StoreDep,
    clock: ClockDep,
) -> ThemeOverrideOut:
    """Removes the Agent's avatar and deletes its file."""
    try:
        found = await branding.remove_avatar(
            db, store, scope, project_id, agent_id, now=clock.now()
        )
    except (ProjectNotFoundError, AgentNotFoundError):
        raise not_found() from None
    return _out(found, scope.organisation_id, project_id, agent_id)


@router.get(
    "/avatar",
    operation_id="getAgentAvatar",
    response_class=Response,
    responses={
        200: {"content": {t: {} for t in images.TYPE_NAMES}, "description": "The image."},
        **NOT_FOUND_RESPONSE,
    },
)
async def get_avatar(
    project_id: uuid.UUID, agent_id: uuid.UUID, scope: Scope, db: Db, store: StoreDep
) -> Response:
    """The Agent's avatar itself. Any Member can fetch it."""
    try:
        found = await branding.read_override(db, scope, project_id, agent_id)
        image = await images.read_stored(store, found.avatar)
    except (ProjectNotFoundError, AgentNotFoundError, images.ImageNotFoundError):
        raise not_found() from None
    return Response(
        image.data,
        media_type=image.content_type,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": IMAGE_CACHE_CONTROL},
    )
