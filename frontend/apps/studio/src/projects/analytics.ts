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

export type VersionComparison = Schemas["VersionComparisonOut"];
export type MetricRow = VersionComparison["metrics"][number];

const COMPARISON_PATH = "/api/organisations/{organisation_id}/projects/{project_id}/agents/{agent_id}/comparison" as const;

/** The query of a comparison of Versions `a` and `b` over the range. */
function comparisonQuery(a: string, b: string, range: MetricsRange) {
  return { a, b, ...(range.from && { start: range.from }), ...(range.to && { end: range.to }) };
}

/** Versions `a` and `b` side by side over the range, with the config diff from `a` to `b`; nothing is fetched for the
 * same Version twice. */
export function useVersionComparison(
  organisationId: string,
  projectId: string,
  agentId: string,
  sides: { a: string; b: string },
  range: MetricsRange,
) {
  return useQuery({
    queryKey: ["version-comparison", organisationId, projectId, agentId, sides, range],
    enabled: sides.a !== sides.b,
    queryFn: async (): Promise<VersionComparison> => {
      const { data, response } = await api.GET(COMPARISON_PATH, {
        params: {
          path: { organisation_id: organisationId, project_id: projectId, agent_id: agentId },
          query: comparisonQuery(sides.a, sides.b, range),
        },
      });
      if (!data) throw new ProjectRequestError(response.status);
      return data;
    },
  });
}

/** Where the comparison downloads as CSV (same origin as the Studio, so the session cookie goes with it). */
export function comparisonCsvUrl(
  organisationId: string,
  projectId: string,
  agentId: string,
  sides: { a: string; b: string },
  range: MetricsRange,
): string {
  const query = new URLSearchParams(comparisonQuery(sides.a, sides.b, range));
  return `/api/organisations/${organisationId}/projects/${projectId}/agents/${agentId}/comparison.csv?${query.toString()}`;
}
