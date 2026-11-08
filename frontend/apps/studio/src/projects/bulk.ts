import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { ProjectRequestError } from "./projects";

export type BulkResult = Schemas["BulkResultOut"];
export type BulkOutcome = Schemas["BulkOutcomeOut"];
export type InstructionsRollout = Schemas["InstructionsRolloutOut"];
export type RolloutAgent = Schemas["RolloutAgentOut"];
export type BulkRevertCandidate = Schemas["BulkRevertCandidateOut"];

function failed(response: Response, error: unknown): ProjectRequestError {
  const detail = (error as { detail?: unknown }).detail;
  return new ProjectRequestError(response.status, typeof detail === "string" ? detail : undefined);
}

/** What to tell the Editor about a bulk action the API refused as a whole. */
export function bulkFailure(error: Error | null): string | undefined {
  if (error === null) return undefined;
  if (error instanceof ProjectRequestError && error.detail) return error.detail;
  return "Something went wrong, so nothing was changed. Try again.";
}

export const rolloutKey = (organisationId: string, projectId: string) => ["instructions-rollout", organisationId, projectId] as const;

/** Which Instructions Version each active Agent's Live Version pins, and how many are behind the Current Version. */
export function useInstructionsRollout(organisationId: string, projectId: string) {
  return useQuery({
    queryKey: rolloutKey(organisationId, projectId),
    queryFn: async (): Promise<InstructionsRollout> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/projects/{project_id}/instructions/rollout", {
        params: { path: { organisation_id: organisationId, project_id: projectId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

function useAfterBulk(organisationId: string, projectId: string) {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: rolloutKey(organisationId, projectId) }),
      queryClient.invalidateQueries({ queryKey: ["agents", organisationId, projectId] }),
    ]);
}

/** Publishes each Agent from its Live configuration with the chosen Instructions Version; one result per Agent. */
export function useBulkPublish(organisationId: string, projectId: string) {
  const onSettled = useAfterBulk(organisationId, projectId);
  return useMutation({
    mutationFn: async ({ agentIds, instructionsVersionId }: { agentIds: string[]; instructionsVersionId: string }): Promise<BulkResult> => {
      const { data, error, response } = await api.POST("/api/organisations/{organisation_id}/projects/{project_id}/agents/bulk-publish", {
        params: { path: { organisation_id: organisationId, project_id: projectId } },
        body: { agent_ids: agentIds, instructions_version_id: instructionsVersionId },
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSettled,
  });
}

/** Reverts each Agent one step back in its Live History; one result per Agent. */
export function useBulkRevert(organisationId: string, projectId: string) {
  const onSettled = useAfterBulk(organisationId, projectId);
  return useMutation({
    mutationFn: async (agentIds: string[]): Promise<BulkResult> => {
      const { data, error, response } = await api.POST("/api/organisations/{organisation_id}/projects/{project_id}/agents/bulk-revert", {
        params: { path: { organisation_id: organisationId, project_id: projectId } },
        body: { agent_ids: agentIds },
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSettled,
  });
}
