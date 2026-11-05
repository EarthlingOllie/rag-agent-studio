import type { Schemas } from "@studio/api-client";
import { useQuery } from "@tanstack/react-query";

import { api } from "../api";

export type Health = Schemas["HealthResponse"];
export type WorkerHealth = Schemas["WorkerHealthResponse"];

/**
 * Both health endpoints answer 503 with the same body shape when something is down, so a 503
 * is still a readable report. Anything else without a body is an unreachable API.
 */
function reportFrom<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data !== undefined) {
    return result.data;
  }
  if (result.response.status === 503) {
    return result.error as T;
  }
  throw new Error(`Unexpected response: ${String(result.response.status)}`);
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => reportFrom<Health>(await api.GET("/api/health")),
  });
}

export function useWorkerHealth() {
  return useQuery({
    queryKey: ["health", "worker"],
    queryFn: async () => reportFrom<WorkerHealth>(await api.GET("/api/health/worker")),
  });
}
