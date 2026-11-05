"""The font allowlist: a curated list of Google Fonts the Theme may use.

Only these families can be chosen, so the widget never loads an arbitrary font URL.
The first one is the default.
"""

import enum
from dataclasses import dataclass


class Font(enum.StrEnum):
    INTER = "Inter"
    ROBOTO = "Roboto"
    OPEN_SANS = "Open Sans"
    LATO = "Lato"
    SOURCE_SANS_3 = "Source Sans 3"
    NUNITO = "Nunito"
    WORK_SANS = "Work Sans"
    IBM_PLEX_SANS = "IBM Plex Sans"
    MERRIWEATHER = "Merriweather"
    LORA = "Lora"
    SOURCE_SERIF_4 = "Source Serif 4"
    JETBRAINS_MONO = "JetBrains Mono"


class FontCategory(enum.StrEnum):
    SANS_SERIF = "sans-serif"
    SERIF = "serif"
    MONOSPACE = "monospace"


@dataclass(frozen=True)
class AllowedFont:
    family: Font
    category: FontCategory


_SERIF = {Font.MERRIWEATHER, Font.LORA, Font.SOURCE_SERIF_4}
_MONOSPACE = {Font.JETBRAINS_MONO}


def _category(font: Font) -> FontCategory:
    if font in _SERIF:
        return FontCategory.SERIF
    if font in _MONOSPACE:
        return FontCategory.MONOSPACE
    return FontCategory.SANS_SERIF


FONT_ALLOWLIST = tuple(AllowedFont(font, _category(font)) for font in Font)
