import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

export const healthy: Schemas["HealthResponse"] = {
  status: "ok",
  checks: { database: "ok", redis: "ok" },
};

export const workerHealthy: Schemas["WorkerHealthResponse"] = { status: "ok", reply: "pong" };

export const notSignedIn: Schemas["ErrorResponse"] = { detail: "Not signed in" };

/** Default handlers describe a healthy stack, a visitor who is not signed in, and no Projects, Documents, Tags, Agents or
 * Conversations (so no Instructions rollout). */
export const server = setupServer(
  http.get("*/api/health", () => HttpResponse.json(healthy)),
  http.get("*/api/organisations/:organisationId/projects", () => HttpResponse.json([])),
  http.get("*/api/organisations/:organisationId/projects/:projectId/documents", () => HttpResponse.json([])),
  http.get("*/api/organisations/:organisationId/projects/:projectId/tags", () => HttpResponse.json([])),
  http.get("*/api/organisations/:organisationId/projects/:projectId/agents", () => HttpResponse.json([])),
  http.get("*/api/organisations/:organisationId/projects/:projectId/instructions/rollout", () =>
    HttpResponse.json({ current_version: null, behind: 0, agents: [] }),
  ),
  http.get("*/api/organisations/:organisationId/projects/:projectId/conversations", () =>
    HttpResponse.json({ items: [], page: 1, page_size: 25, total: 0 }),
  ),
  http.get("*/api/health/worker", () => HttpResponse.json(workerHealthy)),
  http.get("*/api/auth/me", () => HttpResponse.json(notSignedIn, { status: 401 })),
);
