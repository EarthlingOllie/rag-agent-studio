"""Theme resolution on the server: the Organisation's Theme with an Agent's colour override,
as the CSS custom properties the widget's UI primitives read.

It produces exactly what the Studio's ``themeStylesheet`` (``@studio/ui``) produces for the same
Theme, so the widget shell renders what the Theme preview shows. Both are tested against the
same literal stylesheets.
"""

from typing import Any

from app.theme.schema import ColourToken, ThemeSettings

# The colour tokens in the order the stylesheet declares them, as ``@studio/ui`` orders them.
COLOUR_TOKENS = ("primary", "on_primary", "surface", "on_surface", "accent", "muted")


def with_colours(theme: ThemeSettings, colours: dict[str, ColourToken]) -> ThemeSettings:
    """The Theme with some colour tokens replaced, such as by an Agent's Theme override."""
    if not colours:
        return theme
    return theme.model_copy(
        update={"colours": theme.colours.model_copy(update=dict(colours))}, deep=True
    )


def _block(selector: str, theme: ThemeSettings, scheme: str) -> str:
    declarations: list[str] = []
    for token in COLOUR_TOKENS:
        colour: ColourToken = getattr(theme.colours, token)
        declarations.append(f"--theme-{token.replace('_', '-')}:{getattr(colour, scheme)};")
    declarations.append(f"--theme-radius:{theme.radius}px;")
    declarations.append(
        f'--theme-font-family:"{theme.font.value}", ui-sans-serif, system-ui, sans-serif;'
    )
    return f"{selector}{{color-scheme:{scheme};{''.join(declarations)}}}"


def theme_stylesheet(theme: ThemeSettings, selector: str) -> str:
    """A stylesheet applying the Theme to ``selector``; in auto mode it follows the Visitor's
    ``prefers-color-scheme``."""
    if theme.mode.value != "auto":
        return _block(selector, theme, theme.mode.value)
    return (
        _block(selector, theme, "light")
        + "@media (prefers-color-scheme: dark){"
        + _block(selector, theme, "dark")
        + "}"
    )


def font_stylesheet_url(theme: ThemeSettings) -> str:
    """The Google Fonts stylesheet for the Theme's allowlisted family, regular and semibold."""
    family = theme.font.value.replace(" ", "+")
    return f"https://fonts.googleapis.com/css2?family={family}:wght@400;600&display=swap"


def widget_theme(theme: ThemeSettings) -> dict[str, Any]:
    """What the widget app needs of the Theme beyond its CSS: the mode and the Launcher."""
    return {
        "mode": theme.mode.value,
        "launcher_type": theme.launcher_type.value,
        "launcher_position": theme.launcher_position.value,
        "font": theme.font.value,
    }
