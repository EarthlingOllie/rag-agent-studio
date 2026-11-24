import type { Schemas } from "@studio/api-client";
import { type QueryKey, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { type CredentialRequestError, failed } from "../settings/credentials";

export type ReviewSampleNext = Schemas["ReviewSampleNextOut"];
export type ReviewSampleItem = Schemas["ReviewSampleItemOut"];
export type SampleReview = Schemas["SampleReviewOut"];
export type EvaluationAgreement = Schemas["EvaluationAgreementOut"];
export type ReviewOutcome = Schemas["SampleReviewRequest"]["outcome"];

/** What a review of the item names: its Run Verdict, or its Live Verdict and which check. */
export function targetOf(item: ReviewSampleItem): Pick<Schemas["SampleReviewRequest"], "verdict_id" | "live_verdict_id" | "check"> {
  return item.verdict_id === null ? { live_verdict_id: item.live_verdict_id, check: item.check } : { verdict_id: item.verdict_id };
}

/** The longest reason an Editor may give when they differ from the Evaluation Model. */
export const REASON_MAX = 1000;

const nextKey = (organisationId: string) => ["review-sample", organisationId] as const;
const agreementKey = (organisationId: string) => ["evaluation-agreement", organisationId] as const;

/**
 * One judged Verdict or Live Verdict check drawn at random from those not yet reviewed (null when there are none), without the
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

/** Counts a skipped item against the current Evaluation Model; no review is stored, so the item stays in the sample. */
export function useSkipSampleItem(organisationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<void> => {
      const { error, response } = await api.POST("/api/organisations/{organisation_id}/review-sample/skips", {
        params: { path: { organisation_id: organisationId } },
      });
      if (!response.ok) throw failed(response, error);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: agreementKey(organisationId) }),
  });
}

/**
 * Evaluation Model agreement over Review sample reviews: the current Evaluation Model's figures overall and per check, earlier
 * Evaluation Models that have reviews, and how many sample reviews the Organisation and you gave and items were skipped.
 */
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

export type VerdictReview = Schemas["VerdictReviewOut"];
export type ReviewRequest = Schemas["ReviewRequest"];
type LiveCheck = "grounding" | "answers_question";

/** What a review given where Verdicts are shown names: a Run Verdict, or one check of a Live Verdict. */
export type ReviewTarget = { verdict_id: string } | { live_verdict_id: string; check: LiveCheck };

/**
 * Agree or disagree with a judged Verdict or Live Verdict check where it is shown (Run results, the Trace), as the Editor's own pass
 * or fail, or remove the review. Either reads `shownKey` (what shows the Verdict) again, and the Review sample and agreement, since a
 * review takes its target out of the sample and replacing a sample review stops it counting.
 */
export function useVerdictReview(organisationId: string, target: ReviewTarget, shownKey: QueryKey) {
  const queryClient = useQueryClient();
  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: shownKey }),
      queryClient.invalidateQueries({ queryKey: nextKey(organisationId) }),
      queryClient.invalidateQueries({ queryKey: agreementKey(organisationId) }),
    ]);
  const put = useMutation({
    mutationFn: async (body: ReviewRequest): Promise<VerdictReview> => {
      const { data, error, response } =
        "verdict_id" in target
          ? await api.PUT("/api/organisations/{organisation_id}/verdicts/{verdict_id}/review", {
              params: { path: { organisation_id: organisationId, verdict_id: target.verdict_id } },
              body,
            })
          : await api.PUT("/api/organisations/{organisation_id}/live-verdicts/{live_verdict_id}/checks/{check}/review", {
              params: { path: { organisation_id: organisationId, ...target } },
              body,
            });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: async (): Promise<void> => {
      const { error, response } =
        "verdict_id" in target
          ? await api.DELETE("/api/organisations/{organisation_id}/verdicts/{verdict_id}/review", {
              params: { path: { organisation_id: organisationId, verdict_id: target.verdict_id } },
            })
          : await api.DELETE("/api/organisations/{organisation_id}/live-verdicts/{live_verdict_id}/checks/{check}/review", {
              params: { path: { organisation_id: organisationId, ...target } },
            });
      if (!response.ok) throw failed(response, error);
    },
    onSuccess: refresh,
  });
  return { put, remove };
}

/** What to tell an Editor whose review couldn't be saved or removed. */
export function reviewFailure(error: Error | null): string | undefined {
  if (error === null) return undefined;
  if ((error as Partial<CredentialRequestError>).status === 404)
    return "This can no longer be reviewed: its text may have been purged, or the review was already removed. Reload to see it as it is now.";
  return "Something went wrong. Try again.";
}
