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
