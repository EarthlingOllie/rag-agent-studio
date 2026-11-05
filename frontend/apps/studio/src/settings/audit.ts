import type { Schemas } from "@studio/api-client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "../api";

export type AuditEventPage = Schemas["AuditEventPage"];
export type AuditFacets = Schemas["AuditFacetsOut"];

export const PAGE_SIZE = 25;

/** Filters as the Owner enters them: dates are `YYYY-MM-DD` UTC days, both inclusive; "" means any. */
export interface AuditFilters {
  actorId: string;
  action: string;
  from: string;
  to: string;
}

export const NO_FILTERS: AuditFilters = { actorId: "", action: "", from: "", to: "" };

const DAY_MS = 24 * 60 * 60 * 1000;

function startOfUtcDay(day: string, plusDays = 0): string {
  return new Date(Date.parse(`${day}T00:00:00Z`) + plusDays * DAY_MS).toISOString();
}

/** The API query for these filters; a filter left empty is left out. */
function auditQuery(filters: AuditFilters) {
  return {
    ...(filters.actorId ? { actor_id: filters.actorId } : {}),
    ...(filters.action ? { action: filters.action } : {}),
    ...(filters.from ? { start: startOfUtcDay(filters.from) } : {}),
    // The To day is inclusive here; the API's end is exclusive.
    ...(filters.to ? { end: startOfUtcDay(filters.to, 1) } : {}),
  };
}

export class AuditRequestError extends Error {
  constructor(readonly status: number) {
    super(`The API answered ${String(status)}`);
  }
}

export function useAuditEvents(organisationId: string, filters: AuditFilters, page: number) {
  return useQuery({
    queryKey: ["audit-events", organisationId, filters, page],
    placeholderData: keepPreviousData,
    queryFn: async (): Promise<AuditEventPage> => {
      const { data, response } = await api.GET("/api/organisations/{organisation_id}/audit-events", {
        params: {
          path: { organisation_id: organisationId },
          query: { ...auditQuery(filters), page, page_size: PAGE_SIZE },
        },
      });
      if (!data) throw new AuditRequestError(response.status);
      return data;
    },
  });
}

export function useAuditFacets(organisationId: string) {
  return useQuery({
    queryKey: ["audit-facets", organisationId],
    queryFn: async (): Promise<AuditFacets> => {
      const { data, response } = await api.GET("/api/organisations/{organisation_id}/audit-events/facets", {
        params: { path: { organisation_id: organisationId } },
      });
      if (!data) throw new AuditRequestError(response.status);
      return data;
    },
  });
}
