import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { ProjectRequestError } from "./projects";

function failed(response: Response, error: unknown): ProjectRequestError {
  const detail = (error as { detail?: unknown }).detail;
  return new ProjectRequestError(response.status, typeof detail === "string" ? detail : undefined);
}

/** What to tell the Editor about Instructions the API refused. */
export function instructionsFailure(error: Error | null): string | undefined {
  if (error === null) return undefined;
  if (error instanceof ProjectRequestError && error.status === 409 && error.detail) return error.detail;
  if (error instanceof ProjectRequestError && error.status === 422) return "Instructions can be up to 20,000 characters.";
  return "Something went wrong. Try again.";
}

/** What to tell the Editor about a publish or revert the API refused. */
export function versionFailure(error: Error | null): string | undefined {
  if (error === null) return undefined;
  if (error instanceof ProjectRequestError && error.status === 422) return "Add a note of up to 500 characters.";
  return instructionsFailure(error);
}

export type InstructionsVersion = Schemas["InstructionsVersionOut"];
export type InstructionsHistory = Schemas["InstructionsHistoryOut"];

const instructionsKey = (organisationId: string, projectId: string) => ["instructions", organisationId, projectId] as const;

/** The Project Instructions: the markdown every Agent in the Project follows. */
export function useInstructions(organisationId: string, projectId: string) {
  return useQuery({
    queryKey: instructionsKey(organisationId, projectId),
    queryFn: async (): Promise<string> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/projects/{project_id}/instructions", {
        params: { path: { organisation_id: organisationId, project_id: projectId } },
      });
      if (!data) throw failed(response, error);
      return data.markdown;
    },
  });
}

export function useSaveInstructions(organisationId: string, projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (markdown: string): Promise<string> => {
      const { data, error, response } = await api.PUT("/api/organisations/{organisation_id}/projects/{project_id}/instructions", {
        params: { path: { organisation_id: organisationId, project_id: projectId } },
        body: { markdown },
      });
      if (!data) throw failed(response, error);
      return data.markdown;
    },
    onSuccess: (markdown) => {
      queryClient.setQueryData(instructionsKey(organisationId, projectId), markdown);
    },
  });
}

const versionsKey = (organisationId: string, projectId: string) => ["instructions-versions", organisationId, projectId] as const;

/** The Instructions Versions, newest first, and which one is Current. */
export function useInstructionsVersions(organisationId: string, projectId: string) {
  return useQuery({
    queryKey: versionsKey(organisationId, projectId),
    queryFn: async (): Promise<InstructionsHistory> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/projects/{project_id}/instructions/versions", {
        params: { path: { organisation_id: organisationId, project_id: projectId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

/** Saves the Draft as written, then publishes it with a note as the next Version, which becomes Current. */
export function usePublishInstructions(organisationId: string, projectId: string) {
  const queryClient = useQueryClient();
  const path = { organisation_id: organisationId, project_id: projectId };
  return useMutation({
    mutationFn: async ({ markdown, note }: { markdown: string; note: string }): Promise<InstructionsVersion> => {
      const saved = await api.PUT("/api/organisations/{organisation_id}/projects/{project_id}/instructions", {
        params: { path },
        body: { markdown },
      });
      if (!saved.data) throw failed(saved.response, saved.error);
      queryClient.setQueryData(instructionsKey(organisationId, projectId), saved.data.markdown);
      const { data, error, response } = await api.POST("/api/organisations/{organisation_id}/projects/{project_id}/instructions/versions", {
        params: { path },
        body: { note },
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: versionsKey(organisationId, projectId) }),
  });
}

/** Moves the Current Version back to the one that was Current before it. The Draft is unchanged. */
export function useRevertInstructions(organisationId: string, projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<InstructionsVersion> => {
      const { data, error, response } = await api.POST("/api/organisations/{organisation_id}/projects/{project_id}/instructions/revert", {
        params: { path: { organisation_id: organisationId, project_id: projectId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: versionsKey(organisationId, projectId) }),
  });
}
