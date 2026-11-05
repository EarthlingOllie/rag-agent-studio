import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

export const healthy: Schemas["HealthResponse"] = {
  status: "ok",
  checks: { database: "ok", redis: "ok" },
};

export const workerHealthy: Schemas["WorkerHealthResponse"] = { status: "ok", reply: "pong" };

/** Default handlers describe a healthy stack; tests override them per scenario. */
export const server = setupServer(
  http.get("*/api/health", () => HttpResponse.json(healthy)),
  http.get("*/api/health/worker", () => HttpResponse.json(workerHealthy)),
);
