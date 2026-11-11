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
  logo: null,
  avatar: null,
};

export type ThemeImage = Schemas["ThemeImageOut"];
export type ThemeImageKind = Schemas["ThemeImageKind"];

/** A saved image as the API describes it. */
export function anImage(kind: ThemeImageKind, version = "1"): ThemeImage {
  return {
    url: `/api/organisations/o1/theme/images/${kind}?v=${version}`,
    content_type: "image/png",
    size_bytes: 2048,
    uploaded_at: "2026-11-05T09:00:00Z",
  };
}

export const UNSUPPORTED_IMAGE = "Upload a PNG, JPEG or WebP image.";
const IMAGE_FILE = /\.(png|jpe?g|webp)$/i;

export const fonts: Schemas["FontOut"][] = [
  { family: "Inter", category: "sans-serif" },
  { family: "Roboto", category: "sans-serif" },
  { family: "Merriweather", category: "serif" },
];

/**
 * A stateful stand-in for the Theme API and the object store: saving replaces the Theme the
 * next read returns. Images go presign, PUT to a fake storage path on the page's origin, then
 * confirm; the API's refusals of the file type are mirrored.
 */
export function fakeThemeApi(options: { theme?: SavedTheme } = {}) {
  let theme = options.theme ?? defaultTheme;
  const saved: ThemeSettings[] = [];
  const requests: { route: string; kind?: string; body?: unknown; contentType?: string | null }[] = [];
  let version = 0;
  server.use(
    http.post("*/api/organisations/:organisationId/theme/images/:kind/uploads", async ({ request, params }) => {
      const body = (await request.json()) as Schemas["StartImageUploadRequest"];
      const kind = params.kind as string;
      requests.push({ route: "start", kind, body });
      if (!IMAGE_FILE.test(body.filename)) return HttpResponse.json({ detail: UNSUPPORTED_IMAGE }, { status: 415 });
      return HttpResponse.json(
        {
          upload_id: `upload-${kind}`,
          url: `${new URL(request.url).origin}/studio-documents/theme-${kind}?X-Amz-Signature=abc`,
          method: "PUT",
          content_type: "image/png",
          expires_at: "2026-11-05T09:15:00Z",
        },
        { status: 201 },
      );
    }),
    http.put("*/studio-documents/:key", async ({ request, params }) => {
      requests.push({ route: "put", kind: params.key as string, body: await request.text(), contentType: request.headers.get("Content-Type") });
      return new HttpResponse(null, { status: 200 });
    }),
    http.put("*/api/organisations/:organisationId/theme/images/:kind", async ({ request, params }) => {
      const kind = params.kind as ThemeImageKind;
      requests.push({ route: "confirm", kind, body: await request.json() });
      version += 1;
      theme = { ...theme, [kind]: anImage(kind, String(version)), updated_at: "2026-11-05T09:00:00Z" };
      return HttpResponse.json(theme);
    }),
    http.delete("*/api/organisations/:organisationId/theme/images/:kind", ({ params }) => {
      const kind = params.kind as ThemeImageKind;
      requests.push({ route: "remove", kind });
      theme = { ...theme, [kind]: null };
      return HttpResponse.json(theme);
    }),
    http.get("*/api/themes/fonts", () => HttpResponse.json(fonts)),
    http.get("*/api/organisations/:organisationId/theme", () => HttpResponse.json(theme)),
    http.put("*/api/organisations/:organisationId/theme", async ({ request }) => {
      const body = (await request.json()) as ThemeSettings;
      saved.push(body);
      theme = { ...theme, ...body, updated_at: "2026-11-05T09:00:00Z" };
      return HttpResponse.json(theme);
    }),
  );
  return { saved, requests };
}
