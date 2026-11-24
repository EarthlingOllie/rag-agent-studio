import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { failed } from "./credentials";

export type JudgingGuidance = Schemas["JudgingGuidanceOut"];
export type GuidanceVersion = Schemas["GuidanceVersionOut"];

/** The longest Judging guidance, in characters. */
export const GUIDANCE_MAX = 2000;

const guidanceKey = (organisationId: string) => ["judging-guidance", organisationId] as const;

/** The Judging guidance every new judgement uses (null until first saved) and its versions, newest first. */
export function useJudgingGuidance(organisationId: string) {
  return useQuery({
    queryKey: guidanceKey(organisationId),
    queryFn: async (): Promise<JudgingGuidance> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/judging-guidance", {
        params: { path: { organisation_id: organisationId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

/** Saves the Judging guidance as a new current version; empty text removes it (Owners only). */
export function useSaveJudgingGuidance(organisationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (text: string): Promise<JudgingGuidance> => {
      const { data, error, response } = await api.PUT("/api/organisations/{organisation_id}/judging-guidance", {
        params: { path: { organisation_id: organisationId } },
        body: { text },
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(guidanceKey(organisationId), saved);
    },
  });
}
