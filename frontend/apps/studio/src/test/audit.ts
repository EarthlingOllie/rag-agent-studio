import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { adaSession } from "./auth";
import { server } from "./server";

export type AuditEvent = Schemas["AuditEventOut"];

const ada = adaSession.member;
const organisationId = adaSession.organisations[0]?.id ?? "";
export const grace = { id: "6a1b0c58-0d6e-4c1b-9d1e-1f1a6c0f0a03", name: "Grace Hopper", email: "grace@example.test" };

export const organisationCreated: AuditEvent = {
  id: "a0000000-0000-4000-8000-000000000001",
  occurred_at: "2026-06-01T09:30:00Z",
  actor: ada,
  action: "organisation.created",
  target: { type: "organisation", id: organisationId },
  before: null,
  after: { name: "Analytical Engines" },
};

export const roleChanged: AuditEvent = {
  id: "a0000000-0000-4000-8000-000000000002",
  occurred_at: "2026-06-02T14:05:00Z",
  actor: grace,
  action: "member.role_changed",
  target: { type: "member", id: "m-42" },
  before: { role: "editor" },
  after: { role: "owner" },
};

export const lockedOut: AuditEvent = {
  id: "a0000000-0000-4000-8000-000000000003",
  occurred_at: "2026-06-03T00:00:00Z",
  actor: null,
  action: "member.locked_out",
  target: { type: "settings", id: null },
  before: null,
  after: null,
};

/**
 * A stand-in for the audit API that serves `events` (newest first) with the real filtering and
 * paging rules, and records the query string of every list request.
 */
export function fakeAuditApi(events: AuditEvent[] = [lockedOut, roleChanged, organisationCreated]) {
  const queries: URLSearchParams[] = [];
  server.use(
    http.get("*/api/organisations/:organisationId/audit-events/facets", () =>
      HttpResponse.json({
        actors: [ada, grace],
        actions: [...new Set(events.map((event) => event.action))].sort(),
      }),
    ),
    http.get("*/api/organisations/:organisationId/audit-events", ({ request }) => {
      const query = new URL(request.url).searchParams;
      queries.push(query);
      const page = Number(query.get("page") ?? "1");
      const pageSize = Number(query.get("page_size") ?? "25");
      const actor = query.get("actor_id");
      const action = query.get("action");
      const start = query.get("start");
      const end = query.get("end");
      const matching = events.filter(
        (event) =>
          (actor === null || event.actor?.id === actor) &&
          (action === null || event.action === action) &&
          (start === null || Date.parse(event.occurred_at) >= Date.parse(start)) &&
          (end === null || Date.parse(event.occurred_at) < Date.parse(end)),
      );
      return HttpResponse.json({
        items: matching.slice((page - 1) * pageSize, page * pageSize),
        page,
        page_size: pageSize,
        total: matching.length,
      });
    }),
  );
  return { queries };
}
