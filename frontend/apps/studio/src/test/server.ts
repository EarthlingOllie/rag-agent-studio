import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

export const healthy: Schemas["HealthResponse"] = {
  status: "ok",
  checks: { database: "ok", redis: "ok" },
};

export const workerHealthy: Schemas["WorkerHealthResponse"] = {
  status: "ok",
  reply: "pong",
};

export const notSignedIn: Schemas["ErrorResponse"] = {
  detail: "Not signed in",
};

/** Default handlers describe a healthy stack, a visitor who is not signed in, no Projects, Documents, Tags, Agents or
 * Conversations (so no Instructions rollout), no Evaluation Sets or Rollout evaluations, no Evaluation budget or Judging guidance, and the default Retention Window. */
export const server = setupServer(
  http.get("*/api/health", () => HttpResponse.json(healthy)),
  http.get("*/api/organisations/:organisationId/projects", () =>
    HttpResponse.json([]),
  ),
  http.get(
    "*/api/organisations/:organisationId/projects/:projectId/documents",
    () => HttpResponse.json([]),
  ),
  http.get("*/api/organisations/:organisationId/projects/:projectId/tags", () =>
    HttpResponse.json([]),
  ),
  http.get(
    "*/api/organisations/:organisationId/projects/:projectId/agents",
    () => HttpResponse.json([]),
  ),
  http.get(
    "*/api/organisations/:organisationId/projects/:projectId/instructions/rollout",
    () => HttpResponse.json({ current_version: null, behind: 0, agents: [] }),
  ),
  http.get(
    "*/api/organisations/:organisationId/projects/:projectId/conversations",
    () => HttpResponse.json({ items: [], page: 1, page_size: 25, total: 0 }),
  ),
  http.get("*/api/health/worker", () => HttpResponse.json(workerHealthy)),
  // No Agent has an Evaluation Set, so the Publish dialog only hints at creating one.
  http.get(
    "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/evaluation/publish-summary",
    () =>
      HttpResponse.json({
        state: "no_set",
        run: null,
        regressions: [],
        lower_score: false,
        evaluated_live_version_number: null,
        publishing_instructions_version_number: null,
      }),
  ),
  // No Agent has been through a Rollout evaluation.
  http.get(
    "*/api/organisations/:organisationId/projects/:projectId/instructions/versions/:versionId/evaluation",
    () => HttpResponse.json({ instructions_version_number: 1, agents: [] }),
  ),
  // Every Organisation keeps the default Retention Window.
  http.get("*/api/organisations/:organisationId", ({ params }) =>
    HttpResponse.json({
      id: params.organisationId,
      name: "Analytical Engines",
      role: "owner",
      require_mfa: false,
      retention_days: 90,
    }),
  ),
  // No Organisation has saved Judging guidance.
  http.get("*/api/organisations/:organisationId/judging-guidance", () => HttpResponse.json({ current: null, versions: [] })),
  // No Organisation has an Evaluation budget, so no Visitor reply is judged.
  http.get("*/api/organisations/:organisationId/evaluation-budget", () =>
    HttpResponse.json({
      evaluation_budget_usd: null,
      month: "2026-11-01",
      spent_usd: "0",
      exhausted: false,
      resets_at: "2026-12-01T00:00:00Z",
    }),
  ),
  http.get("*/api/auth/me", () =>
    HttpResponse.json(notSignedIn, { status: 401 }),
  ),
);
