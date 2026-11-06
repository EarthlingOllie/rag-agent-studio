import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { type Project, ProjectRequestError } from "./projects";

export type EmbeddingModelChoice = Schemas["EmbeddingModelChoiceOut"];
export type EmbeddingModelSelection = Schemas["SetEmbeddingModelRequest"];

function failed(response: Response, error: unknown): ProjectRequestError {
  const detail = (error as { detail?: unknown }).detail;
  return new ProjectRequestError(response.status, typeof detail === "string" ? detail : undefined);
}

/** The API's reason for a refused choice (a Project with Documents, an unusable credential), or a retry hint. */
export function embeddingFailure(error: Error | null): string | undefined {
  if (error === null) return undefined;
  if (error instanceof ProjectRequestError && error.detail && (error.status === 409 || error.status === 422)) return error.detail;
  return "Something went wrong. Try again.";
}

/** The Embedding Models the Organisation can choose: the built-in one, then each embedding-capable credential's. */
export function useEmbeddingChoices(organisationId: string) {
  return useQuery({
    queryKey: ["embedding-models", organisationId],
    queryFn: async (): Promise<EmbeddingModelChoice[]> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/embedding-models", {
        params: { path: { organisation_id: organisationId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

export function useSetEmbeddingModel(organisationId: string, projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (selection: EmbeddingModelSelection): Promise<Project> => {
      const { data, error, response } = await api.PUT("/api/organisations/{organisation_id}/projects/{project_id}/embedding-model", {
        params: { path: { organisation_id: organisationId, project_id: projectId } },
        body: selection,
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: (project) => {
      queryClient.setQueryData(["projects", organisationId, "one", project.id], project);
    },
  });
}

/** A choice as one select value: the model and the credential it is called through. */
export function choiceValue(modelId: string, credentialId: string | null | undefined): string {
  return `${modelId}|${credentialId ?? ""}`;
}

export function choiceLabel(choice: EmbeddingModelChoice): string {
  return choice.credential_name === null ? choice.name : `${choice.name} (${choice.credential_name})`;
}
