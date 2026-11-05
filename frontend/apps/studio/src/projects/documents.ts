import type { Schemas } from "@studio/api-client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api";
import { ProjectRequestError } from "./projects";

export type ProjectDocument = Schemas["DocumentOut"];
export type DocumentStatus = Schemas["DocumentStatus"];

/** How often the Document list asks for statuses while a Document is still being processed. */
export const STATUS_POLL_MS = 2000;

export const FINAL_STATUSES: readonly DocumentStatus[] = ["ready", "failed"];

const documentsKey = (organisationId: string, projectId: string) => ["documents", organisationId, projectId] as const;

function failed(response: Response, error: unknown): ProjectRequestError {
  const detail = (error as { detail?: unknown }).detail;
  return new ProjectRequestError(response.status, typeof detail === "string" ? detail : undefined);
}

/**
 * The Project's Documents. While any isn't Ready or Failed, their statuses are polled from the
 * lightweight status endpoint and merged in, so the list updates without a refresh.
 */
export function useDocuments(organisationId: string, projectId: string) {
  const path = { organisation_id: organisationId, project_id: projectId };
  const list = useQuery({
    queryKey: documentsKey(organisationId, projectId),
    queryFn: async (): Promise<ProjectDocument[]> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/projects/{project_id}/documents", {
        params: { path },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
  const inProgress = (list.data ?? []).some((document) => !FINAL_STATUSES.includes(document.status));
  const statuses = useQuery({
    queryKey: [...documentsKey(organisationId, projectId), "statuses"],
    queryFn: async () => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/documents/statuses",
        { params: { path } },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    enabled: inProgress,
    // Polling stops once every Document has reached Ready or Failed.
    refetchInterval: (query) =>
      query.state.data?.every((status) => FINAL_STATUSES.includes(status.status)) ? false : STATUS_POLL_MS,
  });
  const latest = new Map((statuses.data ?? []).map((status) => [status.id, status]));
  const documents = list.data?.map((document) => {
    const status = latest.get(document.id);
    return status ? { ...document, status: status.status, error_message: status.error_message, chunk_count: status.chunk_count } : document;
  });
  return { isError: list.isError, data: documents };
}

export type UploadState =
  | { phase: "uploading"; progress: number }
  | { phase: "uploaded" }
  | { phase: "failed"; message: string };

export interface Upload {
  key: string;
  name: string;
  state: UploadState;
}

/** PUTs the file to the presigned URL, reporting progress as a percentage. */
function putFile(url: string, file: File, contentType: string, onProgress: (percent: number) => void): Promise<boolean> {
  return new Promise((resolve) => {
    const request = new XMLHttpRequest();
    request.open("PUT", url);
    request.setRequestHeader("Content-Type", contentType);
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    });
    request.addEventListener("load", () => {
      resolve(request.status >= 200 && request.status < 300);
    });
    request.addEventListener("error", () => {
      resolve(false);
    });
    request.send(file);
  });
}

const TRY_AGAIN = "The upload failed. Try again.";

/**
 * Uploads files to the Project: for each, ask the API for a presigned URL (it checks the type
 * and size first), PUT the file straight to storage, then confirm. Tracks each file's progress.
 */
export function useUploads(organisationId: string, projectId: string) {
  const queryClient = useQueryClient();
  const [uploads, setUploads] = useState<Upload[]>([]);
  const path = { organisation_id: organisationId, project_id: projectId };

  const update = (key: string, state: UploadState) => {
    setUploads((current) => current.map((upload) => (upload.key === key ? { ...upload, state } : upload)));
  };

  async function uploadOne(key: string, file: File) {
    const started = await api.POST("/api/organisations/{organisation_id}/projects/{project_id}/uploads", {
      params: { path },
      body: { filename: file.name, size_bytes: file.size },
    });
    if (!started.data) {
      update(key, { phase: "failed", message: failed(started.response, started.error).detail ?? TRY_AGAIN });
      return;
    }
    const ticket = started.data;
    const stored = await putFile(ticket.url, file, ticket.content_type, (progress) => {
      update(key, { phase: "uploading", progress });
    });
    if (!stored) {
      update(key, { phase: "failed", message: TRY_AGAIN });
      return;
    }
    const confirmed = await api.POST("/api/organisations/{organisation_id}/projects/{project_id}/documents", {
      params: { path },
      body: { upload_id: ticket.upload_id },
    });
    if (!confirmed.data) {
      update(key, { phase: "failed", message: failed(confirmed.response, confirmed.error).detail ?? TRY_AGAIN });
      return;
    }
    update(key, { phase: "uploaded" });
    await queryClient.invalidateQueries({ queryKey: documentsKey(organisationId, projectId) });
  }

  function upload(files: File[]) {
    const added = files.map((file) => ({ key: crypto.randomUUID(), name: file.name, file }));
    setUploads((current) => [
      ...current,
      ...added.map(({ key, name }) => ({ key, name, state: { phase: "uploading", progress: 0 } as const })),
    ]);
    for (const { key, file } of added) void uploadOne(key, file);
  }

  return { uploads, upload };
}
