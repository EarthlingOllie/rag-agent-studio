"""Theme routes: every Member reads the Theme, Owners replace it; and the font allowlist."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.api import Db, ErrorResponse
from app.core.clock import Clock, get_clock
from app.tenancy.api import ORGANISATION_PREFIX
from app.tenancy.policy import NOT_FOUND, OWNERS_ONLY, OwnerScope, Scope
from app.theme import service
from app.theme.fonts import FONT_ALLOWLIST, Font, FontCategory
from app.theme.schema import ThemeSettings

router = APIRouter(prefix=ORGANISATION_PREFIX, tags=["theme"])
fonts_router = APIRouter(prefix="/api/themes", tags=["theme"])

ClockDep = Annotated[Clock, Depends(get_clock)]

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": NOT_FOUND}
}


class ThemeOut(ThemeSettings):
    updated_at: datetime | None


class FontOut(BaseModel):
    family: Font
    category: FontCategory


def _out(saved: service.SavedTheme) -> ThemeOut:
    return ThemeOut(**saved.settings.model_dump(), updated_at=saved.updated_at)


@router.get("/theme", responses=_NOT_FOUND, operation_id="getTheme")
async def get_theme(scope: Scope, db: Db) -> ThemeOut:
    """The Organisation's Theme; the default until an Owner saves one. Any Member can read it."""
    return _out(await service.read_theme(db, scope))


@router.put(
    "/theme",
    responses={403: {"model": ErrorResponse, "description": OWNERS_ONLY}, **_NOT_FOUND},
    operation_id="saveTheme",
)
async def save_theme(body: ThemeSettings, scope: OwnerScope, db: Db, clock: ClockDep) -> ThemeOut:
    """Replaces the Theme. It applies at once. Colours that fail contrast are saved: the
    Studio warns about them but never blocks."""
    return _out(await service.save_theme(db, scope, body, now=clock.now()))


@fonts_router.get("/fonts", operation_id="listThemeFonts")
async def list_fonts() -> list[FontOut]:
    """The Google Fonts a Theme may use, the default first."""
    return [FontOut(family=font.family, category=font.category) for font in FONT_ALLOWLIST]
