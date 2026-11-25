import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { agreementKey } from "../reviews/reviews";
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
      // A new Evaluation Model starts a new Judging setup, so agreement starts again under it.
      void queryClient.invalidateQueries({ queryKey: agreementKey(organisationId) });
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

export type EvaluationBudget = Schemas["EvaluationBudgetOut"];

const budgetKey = (organisationId: string) => ["evaluation-budget", organisationId] as const;

/** The monthly Evaluation budget (null while there is none, and then no reply is sampled) and this month's spend. */
export function useEvaluationBudget(organisationId: string) {
  return useQuery({
    queryKey: budgetKey(organisationId),
    queryFn: async (): Promise<EvaluationBudget> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/evaluation-budget", {
        params: { path: { organisation_id: organisationId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

/** Sets the Evaluation budget in US dollars, or with null removes it (Owners only). */
export function useSetEvaluationBudget(organisationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (budget: string | null): Promise<EvaluationBudget> => {
      const { data, error, response } = await api.PUT("/api/organisations/{organisation_id}/evaluation-budget", {
        params: { path: { organisation_id: organisationId } },
        body: { evaluation_budget_usd: budget },
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(budgetKey(organisationId), saved);
    },
  });
}
