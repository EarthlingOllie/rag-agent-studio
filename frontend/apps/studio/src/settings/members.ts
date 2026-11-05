import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { ME_QUERY_KEY } from "../auth/session";

export type OrganisationMember = Schemas["OrganisationMemberOut"];
export type Role = OrganisationMember["role"];

/** A failed Members request; `status` is the HTTP status and `detail` the API's message, if any. */
export class MemberRequestError extends Error {
  constructor(
    readonly status: number,
    readonly detail?: string,
  ) {
    super(detail ?? `The API answered ${String(status)}`);
  }
}

function failed(response: Response, error: unknown): MemberRequestError {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  return new MemberRequestError(response.status, typeof detail === "string" ? detail : undefined);
}

/** What to tell the Member about a failed change: the last-Owner refusal says why. */
export function memberFailure(error: Error | null): string | undefined {
  if (error === null) return undefined;
  if (error instanceof MemberRequestError && error.status === 409 && error.detail) return error.detail;
  return "Something went wrong. Try again.";
}

const membersKey = (organisationId: string) => ["members", organisationId] as const;

export function useMembers(organisationId: string) {
  return useQuery({
    queryKey: membersKey(organisationId),
    queryFn: async (): Promise<OrganisationMember[]> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/members", {
        params: { path: { organisation_id: organisationId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

/** Role changes and removals can change the signed-in Member's own access, so `me` is refreshed too. */
function useRefreshAfterChange(organisationId: string) {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: membersKey(organisationId) }),
      queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),
    ]);
}

export function useChangeRole(organisationId: string) {
  const refresh = useRefreshAfterChange(organisationId);
  return useMutation({
    mutationFn: async ({ memberId, role }: { memberId: string; role: Role }): Promise<OrganisationMember> => {
      const { data, error, response } = await api.PATCH("/api/organisations/{organisation_id}/members/{member_id}", {
        params: { path: { organisation_id: organisationId, member_id: memberId } },
        body: { role },
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSettled: refresh,
  });
}

export function useRemoveMember(organisationId: string) {
  const refresh = useRefreshAfterChange(organisationId);
  return useMutation({
    mutationFn: async (memberId: string) => {
      const { error, response } = await api.DELETE("/api/organisations/{organisation_id}/members/{member_id}", {
        params: { path: { organisation_id: organisationId, member_id: memberId } },
      });
      if (!response.ok) throw failed(response, error);
    },
    onSettled: refresh,
  });
}

export function useLeaveOrganisation(organisationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { error, response } = await api.POST("/api/organisations/{organisation_id}/leave", {
        params: { path: { organisation_id: organisationId } },
      });
      if (!response.ok) throw failed(response, error);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),
  });
}
