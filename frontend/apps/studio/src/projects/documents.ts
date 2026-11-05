import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api";
import { ProjectRequestError } from "./projects";

export type ProjectDocument = Schemas["DocumentOut"];
export type DocumentStatus = Schemas["DocumentStatus"];

/** How often the Document list asks for statuses while a Document is still being processed. */
export const STATUS_POLL_MS = 2000;

export const FINAL_STATUSES: readonly DocumentStatus[] = ["ready", "failed"];

const documentsKey = (organisationId: string, projectId: string) => ["documents", organisationId, projectId] as const;
const statusesKey = (organisationId: string, projectId: string) => [...documentsKey(organisationId, projectId), "statuses"] as const;

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
    queryKey: statusesKey(organisationId, projectId),
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
    // Measured against the file's own size, which is known even when the event's total isn't.
    request.upload.addEventListener("progress", (event) => {
      onProgress(Math.min(100, Math.round((100 * event.loaded) / Math.max(file.size, 1))));
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

const RETRY_FAILED = "The retry failed. Try again.";

/**
 * Sends a Ready or Failed Document through ingestion again, with the Project's current settings
 * (such as OCR). The list then shows it Queued and polls its status until it is final again.
 */
export function useRetryDocument(organisationId: string, projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (documentId: string): Promise<ProjectDocument> => {
      const { data, error, response } = await api.POST(
        "/api/organisations/{organisation_id}/projects/{project_id}/documents/{document_id}/retry",
        { params: { path: { organisation_id: organisationId, project_id: projectId, document_id: documentId } } },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: async () => {
      // The last polled statuses would otherwise show the Document's old, final status.
      queryClient.removeQueries({ queryKey: statusesKey(organisationId, projectId) });
      await queryClient.invalidateQueries({ queryKey: documentsKey(organisationId, projectId) });
    },
  });
}

/** What to tell the Member about a failed retry: the API's reason, or a retry hint. */
export function retryFailure(error: Error | null): string | undefined {
  if (error === null) return undefined;
  // Every failed retry is a ProjectRequestError (see `failed`).
  return (error as ProjectRequestError).detail ?? RETRY_FAILED;
}
