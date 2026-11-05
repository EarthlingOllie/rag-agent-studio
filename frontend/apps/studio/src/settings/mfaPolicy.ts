import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { ME_QUERY_KEY } from "../auth/session";
import { MemberRequestError } from "./members";

/**
 * Turns the Organisation's Require MFA policy on or off (Owners only). The session lists the
 * policy for each Organisation, so it is refreshed once the change succeeds. A refusal (409)
 * carries the API's message.
 */
export function useSetMfaPolicy(organisationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (requireMfa: boolean) => {
      const { data, error, response } = await api.PUT("/api/organisations/{organisation_id}/mfa-policy", {
        params: { path: { organisation_id: organisationId } },
        body: { require_mfa: requireMfa },
      });
      if (!data) {
        const detail = (error as { detail?: unknown } | undefined)?.detail;
        throw new MemberRequestError(response.status, typeof detail === "string" ? detail : undefined);
      }
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),
  });
}
