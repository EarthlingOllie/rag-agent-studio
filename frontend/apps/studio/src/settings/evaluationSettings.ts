import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { failed } from "./credentials";

export type EvaluationSettings = Schemas["EvaluationSettingsOut"];

/** The Evaluation repeats an Owner can choose: odd, so a majority always decides. */
export const REPEATS = [1, 3, 5, 7, 9] as const;

const settingsKey = (organisationId: string) => ["evaluation-settings", organisationId] as const;

/** The Evaluation Model (null while the Default Model judges) and the Evaluation repeats. */
export function useEvaluationSettings(organisationId: string) {
  return useQuery({
    queryKey: settingsKey(organisationId),
    queryFn: async (): Promise<EvaluationSettings> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/evaluation-settings", {
        params: { path: { organisation_id: organisationId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

/** Sets the Evaluation Model, or with both fields null goes back to the Default Model. */
export function useSetEvaluationModel(organisationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["SetEvaluationModelRequest"]): Promise<EvaluationSettings> => {
      const { data, error, response } = await api.PUT("/api/organisations/{organisation_id}/evaluation-model", {
        params: { path: { organisation_id: organisationId } },
        body,
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(settingsKey(organisationId), saved);
    },
  });
}

export function useSetEvaluationRepeats(organisationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (repeats: Schemas["SetEvaluationRepeatsRequest"]["repeats"]): Promise<EvaluationSettings> => {
      const { data, error, response } = await api.PUT("/api/organisations/{organisation_id}/evaluation-repeats", {
        params: { path: { organisation_id: organisationId } },
        body: { repeats },
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(settingsKey(organisationId), saved);
    },
  });
}
