import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { failed } from "../settings/credentials";

export type ReviewSampleNext = Schemas["ReviewSampleNextOut"];
export type ReviewSampleItem = Schemas["ReviewSampleItemOut"];
export type SampleReview = Schemas["SampleReviewOut"];
export type EvaluationAgreement = Schemas["EvaluationAgreementOut"];
export type ReviewOutcome = Schemas["SampleReviewRequest"]["outcome"];

/** The longest reason an Editor may give when they differ from the Evaluation Model. */
export const REASON_MAX = 1000;

const nextKey = (organisationId: string) => ["review-sample", organisationId] as const;
const agreementKey = (organisationId: string) => ["evaluation-agreement", organisationId] as const;

/**
 * One judged Verdict drawn at random from those not yet reviewed (null when there are none), without the
 * Evaluation Model's outcome or reason. It is drawn again only when asked (Skip, Next).
 */
export function useReviewSampleItem(organisationId: string) {
  return useQuery({
    queryKey: nextKey(organisationId),
    queryFn: async (): Promise<ReviewSampleNext> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/review-sample/next", {
        params: { path: { organisation_id: organisationId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

/** Stores the Editor's pass or fail (and any reason), and reveals the Evaluation Model's. */
export function useSubmitSampleReview(organisationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["SampleReviewRequest"]): Promise<SampleReview> => {
      const { data, error, response } = await api.POST("/api/organisations/{organisation_id}/review-sample/reviews", {
        params: { path: { organisation_id: organisationId } },
        body,
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: agreementKey(organisationId) }),
  });
}

/** How many Review sample reviews of the current Evaluation Model agreed with it. */
export function useEvaluationAgreement(organisationId: string) {
  return useQuery({
    queryKey: agreementKey(organisationId),
    queryFn: async (): Promise<EvaluationAgreement> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/evaluation-agreement", {
        params: { path: { organisation_id: organisationId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}
