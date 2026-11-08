import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { server } from "./server";
import { defaultTheme } from "./theme";

type ThemeOverride = Schemas["ThemeOverrideOut"];

const OVERRIDE = "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/theme-override";
const HEX = /^#[0-9a-fA-F]{6}$/;

/** An Agent avatar as the API describes it. */
export function anAvatar(version = "1"): NonNullable<ThemeOverride["avatar"]> {
  return {
    url: `/api/organisations/o1/projects/p1/agents/a1/theme-override/avatar?v=${version}`,
    content_type: "image/png",
    size_bytes: 2048,
    uploaded_at: "2026-11-07T09:00:00Z",
  };
}

/**
 * A stateful stand-in for an Agent's Theme override and the Organisation's Theme (read only):
 * saved colours come back on the next read; a colour that isn't a hex colour is a 422, as the
 * API has it; avatars go presign, PUT to a fake storage path, confirm.
 */
export function fakeBrandingApi(options: { override?: ThemeOverride } = {}) {
  let saved: ThemeOverride = options.override ?? { colours: {}, avatar: null };
  const requests: { route: string; body?: unknown }[] = [];
  let version = 0;
  server.use(
    http.get("*/api/organisations/:organisationId/theme", () => HttpResponse.json(defaultTheme)),
    http.get(OVERRIDE, () => HttpResponse.json(saved)),
    http.put(OVERRIDE, async ({ request }) => {
      const body = (await request.json()) as Schemas["ColourOverride"];
      requests.push({ route: "colours", body });
      const bad = Object.values(body.colours).some((value) => !HEX.test(value.light) || !HEX.test(value.dark));
      if (bad) {
        return HttpResponse.json(
          { detail: [{ loc: ["body", "colours"], msg: "String should match pattern '^#[0-9a-fA-F]{6}$'", type: "string_pattern_mismatch" }] },
          { status: 422 },
        );
      }
      saved = { ...saved, colours: body.colours };
      return HttpResponse.json(saved);
    }),
    http.post(`${OVERRIDE}/avatar/uploads`, async ({ request }) => {
      const body = (await request.json()) as Schemas["StartImageUploadRequest"];
      requests.push({ route: "start", body });
      if (!/\.(png|jpe?g|webp)$/i.test(body.filename)) {
        return HttpResponse.json({ detail: "Upload a PNG, JPEG or WebP image." }, { status: 415 });
      }
      return HttpResponse.json(
        {
          upload_id: "upload-avatar",
          url: `${new URL(request.url).origin}/studio-documents/agent-avatar?X-Amz-Signature=abc`,
          method: "PUT",
          content_type: "image/png",
          expires_at: "2026-11-07T09:15:00Z",
        },
        { status: 201 },
      );
    }),
    http.put("*/studio-documents/agent-avatar", async ({ request }) => {
      requests.push({ route: "put", body: await request.text() });
      return new HttpResponse(null, { status: 200 });
    }),
    http.put(`${OVERRIDE}/avatar`, async ({ request }) => {
      requests.push({ route: "confirm", body: await request.json() });
      version += 1;
      saved = { ...saved, avatar: anAvatar(String(version)) };
      return HttpResponse.json(saved);
    }),
    http.delete(`${OVERRIDE}/avatar`, () => {
      requests.push({ route: "remove" });
      saved = { ...saved, avatar: null };
      return HttpResponse.json(saved);
    }),
  );
  return requests;
}
