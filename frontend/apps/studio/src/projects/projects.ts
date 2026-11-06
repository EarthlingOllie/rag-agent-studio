import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";

export type Project = Schemas["ProjectOut"];
export type ProjectDetails = Schemas["CreateProjectRequest"];
/** The fields a change sets; the others are left as they are. */
export type ProjectChanges = Schemas["UpdateProjectRequest"];

/** A failed Projects request; `status` is the HTTP status and `detail` the API's message, if any. */
export class ProjectRequestError extends Error {
  constructor(
    readonly status: number,
    readonly detail?: string,
  ) {
    super(`The API answered ${String(status)}`);
  }
}

function failed(response: Response, error: unknown): ProjectRequestError {
  // openapi-fetch gives the parsed JSON body, or the text of a body that isn't JSON.
  const detail = (error as { detail?: unknown }).detail;
  return new ProjectRequestError(response.status, typeof detail === "string" ? detail : undefined);
}

/** What to tell the Member about a failed change: the API's reason for a refusal, or a retry hint. */
export function projectFailure(error: Error | null): string | undefined {
  if (error === null) return undefined;
  if (error instanceof ProjectRequestError) {
    if (error.status === 409 && error.detail) return error.detail;
    if (error.status === 422) return "Give the Project a name of up to 200 characters, and a description of up to 2,000.";
  }
  return "Something went wrong. Try again.";
}

const projectsKey = (organisationId: string) => ["projects", organisationId] as const;
const listKey = (organisationId: string, archived: boolean) => [...projectsKey(organisationId), "list", { archived }] as const;
const projectKey = (organisationId: string, projectId: string) => [...projectsKey(organisationId), "one", projectId] as const;

/** The Organisation's active Projects, or its archived ones. */
export function useProjects(organisationId: string, archived: boolean) {
  return useQuery({
    queryKey: listKey(organisationId, archived),
    queryFn: async (): Promise<Project[]> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/projects", {
        params: { path: { organisation_id: organisationId }, query: { archived } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

export function useProject(organisationId: string, projectId: string) {
  return useQuery({
    queryKey: projectKey(organisationId, projectId),
    queryFn: async (): Promise<Project> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/projects/{project_id}", {
        params: { path: { organisation_id: organisationId, project_id: projectId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

/** After a change, the changed Project is stored and every Projects list is refetched. */
function useStoreProject(organisationId: string) {
  const queryClient = useQueryClient();
  return async (project: Project) => {
    queryClient.setQueryData(projectKey(organisationId, project.id), project);
    await queryClient.invalidateQueries({ queryKey: [...projectsKey(organisationId), "list"] });
  };
}

export function useCreateProject(organisationId: string) {
  const store = useStoreProject(organisationId);
  return useMutation({
    mutationFn: async (details: ProjectDetails): Promise<Project> => {
      const { data, error, response } = await api.POST("/api/organisations/{organisation_id}/projects", {
        params: { path: { organisation_id: organisationId } },
        body: details,
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: store,
  });
}

export function useUpdateProject(organisationId: string, projectId: string) {
  const store = useStoreProject(organisationId);
  return useMutation({
    mutationFn: async (details: ProjectChanges): Promise<Project> => {
      const { data, error, response } = await api.PATCH("/api/organisations/{organisation_id}/projects/{project_id}", {
        params: { path: { organisation_id: organisationId, project_id: projectId } },
        body: details,
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: store,
  });
}

/** Archive (any Member) or restore (Owners) a Project. */
export function useArchiveOrRestore(organisationId: string, action: "archive" | "restore") {
  const store = useStoreProject(organisationId);
  return useMutation({
    mutationFn: async (projectId: string): Promise<Project> => {
      const path =
        action === "archive"
          ? ("/api/organisations/{organisation_id}/projects/{project_id}/archive" as const)
          : ("/api/organisations/{organisation_id}/projects/{project_id}/restore" as const);
      const { data, error, response } = await api.POST(path, {
        params: { path: { organisation_id: organisationId, project_id: projectId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: store,
  });
}
