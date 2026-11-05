import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { failed } from "./credentials";

export type DefaultModel = Schemas["DefaultModelOut"];
export type ModelInfo = Schemas["ModelOut"];

const defaultModelKey = (organisationId: string) => ["default-model", organisationId] as const;

export function useDefaultModel(organisationId: string) {
  return useQuery({
    queryKey: defaultModelKey(organisationId),
    queryFn: async (): Promise<DefaultModel | null> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/default-model", {
        params: { path: { organisation_id: organisationId } },
      });
      if (!response.ok) throw failed(response, error);
      return data ?? null;
    },
  });
}

/** The models a credential offers for chat. */
export function useChatModels(organisationId: string, credentialId: string) {
  return useQuery({
    queryKey: ["credential-models", organisationId, credentialId, "chat"],
    queryFn: async (): Promise<ModelInfo[]> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/credentials/{credential_id}/models/{capability}",
        { params: { path: { organisation_id: organisationId, credential_id: credentialId, capability: "chat" } } },
      );
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

export function useSetDefaultModel(organisationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["SetDefaultModelRequest"]): Promise<DefaultModel> => {
      const { data, error, response } = await api.PUT("/api/organisations/{organisation_id}/default-model", {
        params: { path: { organisation_id: organisationId } },
        body,
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(defaultModelKey(organisationId), saved);
    },
  });
}
