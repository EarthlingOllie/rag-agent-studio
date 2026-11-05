import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";

export type Credential = Schemas["CredentialOut"];
export type ProviderInfo = Schemas["ProviderOut"];
export type ProviderId = Credential["provider"];
export type Capability = Credential["capabilities"][number];
export type CheckFailure = Schemas["CheckFailedResponse"]["reason"];
export type CredentialReference = Schemas["CredentialReferenceOut"];

/** Why a credential check failed, in words an Owner can act on. */
export const FAILURE_MESSAGES: Record<CheckFailure, string> = {
  invalid_key: "The provider rejected this API key. Check it was copied in full.",
  missing_model_access: "The key works, but it can't use this provider's models. Check the key's permissions in your provider account.",
  quota_exceeded: "The provider says this key is over its rate limit or quota. Try again later, or check your plan.",
  provider_unreachable: "We couldn't reach the provider to check the key. Try again in a few minutes.",
};

export const CAPABILITY_NAMES: Record<Capability, string> = { chat: "Chat", embeddings: "Embeddings", rerank: "Reranking" };

/** A failed credentials request, with what the API said about it. */
export class CredentialRequestError extends Error {
  constructor(
    readonly status: number,
    readonly detail?: string,
    readonly reason?: CheckFailure,
    readonly references: CredentialReference[] = [],
  ) {
    super(detail ?? `The API answered ${String(status)}`);
  }
}

export function failed(response: Response, error: unknown): CredentialRequestError {
  // `Object()` turns a missing or non-JSON body into an empty object.
  const body = Object(error) as { detail?: unknown; reason?: CheckFailure; references?: CredentialReference[] };
  const detail = typeof body.detail === "string" ? body.detail : undefined;
  return new CredentialRequestError(response.status, detail, body.reason, body.references);
}

/** What to tell an Owner about a failed change. */
export function credentialFailure(error: Error | null): string | undefined {
  if (error === null) return undefined;
  // A network failure is a plain Error, with none of these.
  const { status, detail, reason } = error as Partial<CredentialRequestError>;
  if (reason) return `The check failed. ${FAILURE_MESSAGES[reason]}`;
  // A malformed key, an unsupported capability or a taken name: the API says which.
  if ((status === 409 || status === 422) && detail) return detail;
  return "Something went wrong. Try again.";
}

const credentialsKey = (organisationId: string) => ["credentials", organisationId] as const;

export function useCredentials(organisationId: string) {
  return useQuery({
    queryKey: credentialsKey(organisationId),
    queryFn: async (): Promise<Credential[]> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/credentials", {
        params: { path: { organisation_id: organisationId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

export function useProviders() {
  return useQuery({
    queryKey: ["providers"],
    staleTime: Infinity,
    queryFn: async (): Promise<ProviderInfo[]> => {
      const { data, error, response } = await api.GET("/api/providers");
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

function useRefresh(organisationId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: credentialsKey(organisationId) });
}

export type NewCredential = Schemas["CreateCredentialRequest"];

export function useAddCredential(organisationId: string) {
  const refresh = useRefresh(organisationId);
  return useMutation({
    mutationFn: async (body: NewCredential): Promise<Credential> => {
      const { data, error, response } = await api.POST("/api/organisations/{organisation_id}/credentials", {
        params: { path: { organisation_id: organisationId } },
        body,
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSettled: refresh,
  });
}

export function useCheckCredential(organisationId: string) {
  const refresh = useRefresh(organisationId);
  return useMutation({
    mutationFn: async (credentialId: string): Promise<Credential> => {
      const { data, error, response } = await api.POST("/api/organisations/{organisation_id}/credentials/{credential_id}/check", {
        params: { path: { organisation_id: organisationId, credential_id: credentialId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSettled: refresh,
  });
}

export function useRotateCredential(organisationId: string) {
  const refresh = useRefresh(organisationId);
  return useMutation({
    mutationFn: async ({ credentialId, apiKey }: { credentialId: string; apiKey: string }): Promise<Credential> => {
      const { data, error, response } = await api.POST("/api/organisations/{organisation_id}/credentials/{credential_id}/rotate", {
        params: { path: { organisation_id: organisationId, credential_id: credentialId } },
        body: { api_key: apiKey },
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSettled: refresh,
  });
}

export function useDeleteCredential(organisationId: string) {
  const refresh = useRefresh(organisationId);
  return useMutation({
    mutationFn: async (credentialId: string) => {
      const { error, response } = await api.DELETE("/api/organisations/{organisation_id}/credentials/{credential_id}", {
        params: { path: { organisation_id: organisationId, credential_id: credentialId } },
      });
      if (!response.ok) throw failed(response, error);
    },
    onSettled: refresh,
  });
}
