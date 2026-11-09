import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";

export type OrganisationDetails = Schemas["OrganisationOut"];

export const MIN_RETENTION_DAYS = 7;
export const MAX_RETENTION_DAYS = 3650;

/** A refused or failed request for the Organisation's settings, with the API's status. */
export class RetentionRequestError extends Error {
  constructor(readonly status: number) {
    super(`The API answered ${String(status)}`);
  }
}

const organisationKey = (organisationId: string) => ["organisation", organisationId];

/** The Organisation as the signed-in Member sees it, with its Retention Window. */
export function useOrganisationDetails(organisationId: string) {
  return useQuery({
    queryKey: organisationKey(organisationId),
    queryFn: async (): Promise<OrganisationDetails> => {
      const { data, response } = await api.GET("/api/organisations/{organisation_id}", {
        params: { path: { organisation_id: organisationId } },
      });
      if (!data) throw new RetentionRequestError(response.status);
      return data;
    },
  });
}

/** Sets the Organisation's Retention Window in days (Owners only). */
export function useSetRetentionWindow(organisationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (days: number): Promise<OrganisationDetails> => {
      const { data, response } = await api.PUT("/api/organisations/{organisation_id}/retention-window", {
        params: { path: { organisation_id: organisationId } },
        body: { retention_days: days },
      });
      if (!data) throw new RetentionRequestError(response.status);
      return data;
    },
    onSuccess: (organisation) => {
      queryClient.setQueryData(organisationKey(organisationId), organisation);
    },
  });
}
