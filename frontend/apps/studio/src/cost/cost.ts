import type { Schemas } from "@studio/api-client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "../api";
import { ProjectRequestError } from "../projects/projects";

export type OrgCost = Schemas["OrgCostOut"];
export type CostGroup = OrgCost["group_by"];

/** What to show: the breakdown, and UTC days (`YYYY-MM-DD`), both inclusive; the last 30 days when left out. */
export interface CostQuery {
  groupBy: CostGroup;
  from?: string;
  to?: string;
}

/** What the Organisation spent over the period, by Project or by Agent. Owners only. */
export function useOrgCost(organisationId: string, query: CostQuery) {
  return useQuery({
    queryKey: ["org-cost", organisationId, query],
    placeholderData: keepPreviousData,
    queryFn: async (): Promise<OrgCost> => {
      const { data, response } = await api.GET("/api/organisations/{organisation_id}/cost", {
        params: {
          path: { organisation_id: organisationId },
          query: { group_by: query.groupBy, ...(query.from && { start: query.from }), ...(query.to && { end: query.to }) },
        },
      });
      if (!data) throw new ProjectRequestError(response.status);
      return data;
    },
  });
}
