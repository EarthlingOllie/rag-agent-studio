import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { ProjectRequestError } from "./projects";

export type Tag = Schemas["TagOut"];

const tagsKey = (organisationId: string, projectId: string) => ["tags", organisationId, projectId] as const;

function failed(response: Response, error: unknown): ProjectRequestError {
  const detail = (error as { detail?: unknown }).detail;
  return new ProjectRequestError(response.status, typeof detail === "string" ? detail : undefined);
}

/** What to tell the Editor about a failed Tag change: the API's reason, or a retry hint. */
export function tagFailure(error: Error | null): string | undefined {
  if (error === null) return undefined;
  if (error instanceof ProjectRequestError && error.detail && [409, 422].includes(error.status)) return error.detail;
  return "Something went wrong. Try again.";
}

/** The Project's Tags, by name, with how many Documents carry each. */
export function useTags(organisationId: string, projectId: string) {
  return useQuery({
    queryKey: tagsKey(organisationId, projectId),
    queryFn: async (): Promise<Tag[]> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/projects/{project_id}/tags", {
        params: { path: { organisation_id: organisationId, project_id: projectId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

/** After any Tag change, the Tags and the Documents (which show Tag names) are refetched. */
function useRefresh(organisationId: string, projectId: string) {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: tagsKey(organisationId, projectId) }),
      queryClient.invalidateQueries({ queryKey: ["documents", organisationId, projectId] }),
    ]);
  };
}

type Change =
  | { kind: "create"; name: string }
  | { kind: "rename"; tagId: string; name: string }
  | { kind: "delete"; tagId: string }
  | { kind: "set"; documentId: string; tagIds: string[] }
  | { kind: "bulk"; documentIds: string[]; action: "add" | "remove"; tagId: string };

async function send(organisationId: string, projectId: string, change: Change): Promise<void> {
  const path = { organisation_id: organisationId, project_id: projectId };
  const tags = "/api/organisations/{organisation_id}/projects/{project_id}/tags" as const;
  const tag = "/api/organisations/{organisation_id}/projects/{project_id}/tags/{tag_id}" as const;
  let result: { error?: unknown; response: Response };
  switch (change.kind) {
    case "create":
      result = await api.POST(tags, { params: { path }, body: { name: change.name } });
      break;
    case "rename":
      result = await api.PATCH(tag, { params: { path: { ...path, tag_id: change.tagId } }, body: { name: change.name } });
      break;
    case "delete":
      result = await api.DELETE(tag, { params: { path: { ...path, tag_id: change.tagId } } });
      break;
    case "set":
      result = await api.PUT("/api/organisations/{organisation_id}/projects/{project_id}/documents/{document_id}/tags", {
        params: { path: { ...path, document_id: change.documentId } },
        body: { tag_ids: change.tagIds },
      });
      break;
    case "bulk":
      result = await api.POST("/api/organisations/{organisation_id}/projects/{project_id}/documents/tags", {
        params: { path },
        body: { document_ids: change.documentIds, [change.action]: [change.tagId] },
      });
      break;
  }
  if (!result.response.ok) throw failed(result.response, result.error);
}

/** Creates, renames and deletes Tags, and applies them to Documents one at a time or in bulk. */
export function useTagChange(organisationId: string, projectId: string) {
  const refresh = useRefresh(organisationId, projectId);
  return useMutation({
    mutationFn: (change: Change) => send(organisationId, projectId, change),
    onSuccess: refresh,
  });
}
