import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { ME_QUERY_KEY } from "../auth/session";

export type Invite = Schemas["InviteOut"];
export type IssuedInvite = Schemas["IssuedInviteOut"];
export type InvitePreview = Schemas["InvitePreviewOut"];
export type NewInvite = Schemas["CreateInviteRequest"];
export type Role = Invite["role"];

/** A failed invite request; `status` is the HTTP status and `detail` the API's message, if any. */
export class InviteRequestError extends Error {
  constructor(
    readonly status: number,
    readonly detail?: string,
  ) {
    super(detail ?? `The API answered ${String(status)}`);
  }
}

function failed(response: Response, error: unknown): InviteRequestError {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  return new InviteRequestError(response.status, typeof detail === "string" ? detail : undefined);
}

export const ROLE_NAMES: Record<Role, string> = { owner: "Owner", editor: "Editor" };

const invitesKey = (organisationId: string) => ["invites", organisationId] as const;

export function usePendingInvites(organisationId: string) {
  return useQuery({
    queryKey: invitesKey(organisationId),
    queryFn: async (): Promise<Invite[]> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/invites", {
        params: { path: { organisation_id: organisationId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

export function useCreateInvite(organisationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: NewInvite): Promise<IssuedInvite> => {
      const { data, error, response } = await api.POST("/api/organisations/{organisation_id}/invites", {
        params: { path: { organisation_id: organisationId } },
        body,
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: invitesKey(organisationId) }),
  });
}

export function useRenewInvite(organisationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (inviteId: string): Promise<IssuedInvite> => {
      const { data, error, response } = await api.POST(
        "/api/organisations/{organisation_id}/invites/{invite_id}/renew",
        { params: { path: { organisation_id: organisationId, invite_id: inviteId } }, body: { send_email: false } },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: invitesKey(organisationId) }),
  });
}

export function useRevokeInvite(organisationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (inviteId: string) => {
      const { error, response } = await api.DELETE("/api/organisations/{organisation_id}/invites/{invite_id}", {
        params: { path: { organisation_id: organisationId, invite_id: inviteId } },
      });
      if (!response.ok) throw failed(response, error);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: invitesKey(organisationId) }),
  });
}

/** What the invite link offers; the token is in the link the person opened. */
export function useInvitePreview(token: string) {
  return useQuery({
    queryKey: ["invite-preview", token],
    // A link that doesn't work won't start working on a retry; say so straight away.
    retry: false,
    queryFn: async (): Promise<InvitePreview> => {
      const { data, error, response } = await api.POST("/api/invites/lookup", { body: { token } });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

export function useAcceptInvite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (token: string) => {
      const { data, error, response } = await api.POST("/api/invites/accept", { body: { token } });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: (session) => {
      queryClient.setQueryData(ME_QUERY_KEY, session);
    },
  });
}

export function useSignUpWithInvite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["InviteSignUpRequest"]) => {
      const { data, error, response } = await api.POST("/api/invites/sign-up", { body });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: (session) => {
      queryClient.setQueryData(ME_QUERY_KEY, session);
    },
  });
}
