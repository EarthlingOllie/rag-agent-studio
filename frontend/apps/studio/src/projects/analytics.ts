import type { Schemas } from "@studio/api-client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "../api";
import { ProjectRequestError } from "./projects";

export type VersionMetrics = Schemas["VersionMetricsOut"];
export type VersionKpis = VersionMetrics["versions"][number];

/** UTC days (`YYYY-MM-DD`), both inclusive; the API's defaults (the last 30 days) when left out. */
export interface MetricsRange {
  from?: string;
  to?: string;
}

/** Every Version's KPIs for the Agent over the range. */
export function useVersionMetrics(organisationId: string, projectId: string, agentId: string, range: MetricsRange) {
  return useQuery({
    queryKey: ["version-metrics", organisationId, projectId, agentId, range],
    placeholderData: keepPreviousData,
    queryFn: async (): Promise<VersionMetrics> => {
      const { data, response } = await api.GET("/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/metrics", {
        params: {
          path: { organisation_id: organisationId, project_id: projectId, agent_id: agentId },
          query: { ...(range.from && { start: range.from }), ...(range.to && { end: range.to }) },
        },
      });
      if (!data) throw new ProjectRequestError(response.status);
      return data;
    },
  });
}
