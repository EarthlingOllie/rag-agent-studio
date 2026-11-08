import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { server } from "./server";

/**
 * A stateful stand-in for the Retention Window: the Organisation reports it and setting it changes it,
 * unless it is outside 7 to 3650 days (422, as the API answers). `readStatus` or `saveStatus` answer
 * every read or save with that status instead. Returns the request bodies it received.
 */
export function fakeRetentionApi(options: { days?: number; readStatus?: number; saveStatus?: number } = {}) {
  let days = options.days ?? 90;
  const requests: Schemas["RetentionWindowRequest"][] = [];
  const organisation = (id: unknown) => ({
    id,
    name: "Analytical Engines",
    role: "owner",
    require_mfa: false,
    retention_days: days,
  });
  server.use(
    http.get("*/api/organisations/:organisationId", ({ params }) =>
      options.readStatus
        ? HttpResponse.json({ detail: "Failed" }, { status: options.readStatus })
        : HttpResponse.json(organisation(params.organisationId)),
    ),
    http.put("*/api/organisations/:organisationId/retention-window", async ({ params, request }) => {
      const body = (await request.json()) as Schemas["RetentionWindowRequest"];
      requests.push(body);
      if (options.saveStatus) return HttpResponse.json({ detail: "Failed" }, { status: options.saveStatus });
      if (body.retention_days < 7 || body.retention_days > 3650) {
        return HttpResponse.json({ detail: [{ msg: "out of range" }] }, { status: 422 });
      }
      days = body.retention_days;
      return HttpResponse.json(organisation(params.organisationId));
    }),
  );
  return { requests };
}
