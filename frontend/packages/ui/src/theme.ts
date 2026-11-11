/**
 * Theme resolution: the one pure function that turns the Organisation's Theme into CSS custom
 * properties. The Studio's Theme preview, the widget and the contrast checker all use it, so
 * what an Owner previews is what a Visitor sees.
 */
import type { Schemas } from "@studio/api-client";

export type Theme = Schemas["ThemeSettings"];
export type ThemeMode = Theme["mode"];
export type ColourToken = keyof Theme["colours"];
/** The colours on screen at one time: a light-mode or a dark-mode set. */
export type ColourScheme = "light" | "dark";

export type ThemeProperties = Record<`--theme-${string}`, string>;

/** The colour tokens in display order, with the name an Owner sees. */
export const COLOUR_TOKENS: readonly { token: ColourToken; label: string }[] = [
  { token: "primary", label: "Primary" },
  { token: "on_primary", label: "Text on primary" },
  { token: "surface", label: "Surface" },
  { token: "on_surface", label: "Text on surface" },
  { token: "accent", label: "Accent" },
  { token: "muted", label: "Muted text" },
];

/** The Theme an Organisation has until an Owner saves one; the API's default. */
export const DEFAULT_THEME: Theme = {
  colours: {
    primary: { light: "#4f46e5", dark: "#818cf8" },
    on_primary: { light: "#ffffff", dark: "#111827" },
    surface: { light: "#ffffff", dark: "#111827" },
    on_surface: { light: "#111827", dark: "#f9fafb" },
    accent: { light: "#0f766e", dark: "#2dd4bf" },
    muted: { light: "#4b5563", dark: "#9ca3af" },
  },
  radius: 12,
  font: "Inter",
  mode: "light",
  launcher_type: "bubble",
  launcher_position: "bottom-right",
};

/** The colour schemes a Theme can show: auto follows the Visitor's preference between both. */
export function schemesFor(mode: ThemeMode): ColourScheme[] {
  return mode === "auto" ? ["light", "dark"] : [mode];
}

/** The CSS custom properties for the Theme in one colour scheme. */
export function resolveTheme(theme: Theme, scheme: ColourScheme): ThemeProperties {
  const properties: ThemeProperties = {};
  for (const { token } of COLOUR_TOKENS) {
    properties[`--theme-${token.replace("_", "-")}`] = theme.colours[token][scheme];
  }
  properties["--theme-radius"] = `${String(theme.radius)}px`;
  properties["--theme-font-family"] = `"${theme.font}", ui-sans-serif, system-ui, sans-serif`;
  return properties;
}

function block(selector: string, theme: Theme, scheme: ColourScheme): string {
  const declarations = Object.entries(resolveTheme(theme, scheme))
    .map(([name, value]) => `${name}:${value};`)
    .join("");
  return `${selector}{color-scheme:${scheme};${declarations}}`;
}

/** A stylesheet applying the Theme to `selector`; in auto mode it follows `prefers-color-scheme`. */
export function themeStylesheet(theme: Theme, selector = ":root"): string {
  if (theme.mode !== "auto") return block(selector, theme, theme.mode);
  return `${block(selector, theme, "light")}@media (prefers-color-scheme: dark){${block(selector, theme, "dark")}}`;
}

/** The Google Fonts stylesheet for an allowlisted family, regular and semibold. */
export function fontStylesheetUrl(family: Theme["font"]): string {
  return `https://fonts.googleapis.com/css2?family=${family.replaceAll(" ", "+")}:wght@400;600&display=swap`;
}
