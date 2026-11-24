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

export type GuidanceJob = Schemas["GuidanceJobOut"];
export type GuidanceCheck = Schemas["GuidanceCheckOut"];

/** How often a draft or check in progress is read again, in milliseconds. */
export const GUIDANCE_JOB_POLL_MS = 1000;

const jobKey = (organisationId: string) => ["guidance-job", organisationId] as const;

/** Whether a draft or check is still queued or running. */
export function jobInProgress(job: GuidanceJob): boolean {
  return job.status === "queued" || job.status === "running";
}

/** The latest draft or check, read again while it is in progress (Owners only). */
export function useLatestGuidanceJob(organisationId: string, enabled: boolean) {
  return useQuery({
    queryKey: jobKey(organisationId),
    enabled,
    queryFn: async (): Promise<GuidanceJob | null> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/guidance-jobs/latest", {
        params: { path: { organisation_id: organisationId } },
      });
      if (!response.ok) throw failed(response, error);
      return data ?? null;
    },
    refetchInterval: (query) => (query.state.data && jobInProgress(query.state.data) ? GUIDANCE_JOB_POLL_MS : false),
  });
}

/** Starts checking guidance text on the held-out reviews (Owners only). */
export function useStartGuidanceCheck(organisationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (text: string): Promise<GuidanceJob> => {
      const { data, error, response } = await api.POST("/api/organisations/{organisation_id}/judging-guidance/checks", {
        params: { path: { organisation_id: organisationId } },
        body: { text },
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: (job) => {
      queryClient.setQueryData(jobKey(organisationId), job);
    },
  });
}

/** Cancels the draft or check in progress (Owners only). */
export function useCancelGuidanceJob(organisationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (jobId: string): Promise<GuidanceJob> => {
      const { data, error, response } = await api.POST("/api/organisations/{organisation_id}/guidance-jobs/{job_id}/cancel", {
        params: { path: { organisation_id: organisationId, job_id: jobId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: (job) => {
      queryClient.setQueryData(jobKey(organisationId), job);
    },
  });
}
