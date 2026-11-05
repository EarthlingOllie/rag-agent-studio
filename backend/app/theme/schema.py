"""What a Theme is: its colour tokens, radius, font, mode and launcher, with validation."""

import enum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.theme.fonts import Font

MAX_RADIUS = 24


class ThemeMode(enum.StrEnum):
    LIGHT = "light"
    DARK = "dark"
    # Follows the Visitor's light or dark preference.
    AUTO = "auto"


class LauncherType(enum.StrEnum):
    # A floating button that opens the chat.
    BUBBLE = "bubble"
    # The chat sits in a container on the host page.
    INLINE = "inline"


class LauncherPosition(enum.StrEnum):
    BOTTOM_RIGHT = "bottom-right"
    BOTTOM_LEFT = "bottom-left"


HexColour = Annotated[
    str,
    Field(pattern=r"^#[0-9a-fA-F]{6}$", examples=["#4f46e5"]),
    AfterValidator(str.lower),
]


class ColourToken(BaseModel):
    """A colour token's light-mode value and its dark-mode value."""

    model_config = ConfigDict(frozen=True)

    light: HexColour
    dark: HexColour


class ThemeColours(BaseModel):
    """The colour tokens. ``on_*`` colours are for text and icons on the colour they name."""

    model_config = ConfigDict(frozen=True)

    primary: ColourToken
    on_primary: ColourToken
    surface: ColourToken
    on_surface: ColourToken
    accent: ColourToken
    muted: ColourToken


class ThemeSettings(BaseModel):
    """Everything an Owner sets on the Theme."""

    model_config = ConfigDict(frozen=True)

    colours: ThemeColours
    radius: int = Field(ge=0, le=MAX_RADIUS, description="Corner radius in pixels.")
    font: Font
    mode: ThemeMode
    launcher_type: LauncherType
    launcher_position: LauncherPosition


DEFAULT_THEME = ThemeSettings(
    colours=ThemeColours(
        primary=ColourToken(light="#4f46e5", dark="#818cf8"),
        on_primary=ColourToken(light="#ffffff", dark="#111827"),
        surface=ColourToken(light="#ffffff", dark="#111827"),
        on_surface=ColourToken(light="#111827", dark="#f9fafb"),
        accent=ColourToken(light="#0f766e", dark="#2dd4bf"),
        muted=ColourToken(light="#4b5563", dark="#9ca3af"),
    ),
    radius=12,
    font=Font.INTER,
    mode=ThemeMode.LIGHT,
    launcher_type=LauncherType.BUBBLE,
    launcher_position=LauncherPosition.BOTTOM_RIGHT,
)
