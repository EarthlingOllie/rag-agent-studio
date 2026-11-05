import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { server } from "./server";

export type SavedTheme = Schemas["ThemeOut"];
export type ThemeSettings = Schemas["ThemeSettings"];

/** The API's default Theme, as a new Organisation has it. */
export const defaultTheme: SavedTheme = {
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
  updated_at: null,
};

export const fonts: Schemas["FontOut"][] = [
  { family: "Inter", category: "sans-serif" },
  { family: "Roboto", category: "sans-serif" },
  { family: "Merriweather", category: "serif" },
];

/** A stateful stand-in for the Theme API: saving replaces the Theme the next read returns. */
export function fakeThemeApi(options: { theme?: SavedTheme } = {}) {
  let theme = options.theme ?? defaultTheme;
  const saved: ThemeSettings[] = [];
  server.use(
    http.get("*/api/themes/fonts", () => HttpResponse.json(fonts)),
    http.get("*/api/organisations/:organisationId/theme", () => HttpResponse.json(theme)),
    http.put("*/api/organisations/:organisationId/theme", async ({ request }) => {
      const body = (await request.json()) as ThemeSettings;
      saved.push(body);
      theme = { ...body, updated_at: "2026-11-05T09:00:00Z" };
      return HttpResponse.json(theme);
    }),
  );
  return { saved };
}
