import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api";
import { ProjectRequestError } from "./projects";

export type ProjectDocument = Schemas["DocumentOut"];
export type DocumentStatus = Schemas["DocumentStatus"];
export type FailureCategory = Schemas["FailureCategory"];
export type UploadLimits = Schemas["UploadLimitsOut"];

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
    return status ? { ...document, ...status } : document;
  });
  return { isError: list.isError, data: documents };
}

const limitsKey = (organisationId: string, projectId: string) => [...documentsKey(organisationId, projectId), "limits"] as const;

/** What an upload must satisfy: accepted types, the size limit, and room in the Document quota. */
export function useUploadLimits(organisationId: string, projectId: string) {
  return useQuery({
    queryKey: limitsKey(organisationId, projectId),
    queryFn: async (): Promise<UploadLimits> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/projects/{project_id}/uploads/limits", {
        params: { path: { organisation_id: organisationId, project_id: projectId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

/** Puts a Failed Document back to Queued; the list then polls it to Ready or Failed again. */
export function useRetryDocument(organisationId: string, projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (documentId: string) => {
      const { data, error, response } = await api.POST(
        "/api/organisations/{organisation_id}/projects/{project_id}/documents/{document_id}/retry",
        { params: { path: { organisation_id: organisationId, project_id: projectId, document_id: documentId } } },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: documentsKey(organisationId, projectId) }),
  });
}

export const UNSUPPORTED_TYPE = "This file type isn't supported. Upload a PDF, DOCX, PPTX, HTML, Markdown or TXT file.";

function quotaMessage(quota: number): string {
  return `This Project has reached its quota of ${String(quota)} ${quota === 1 ? "Document" : "Documents"}. Delete a Document, or ask an Owner to raise the quota.`;
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot).toLowerCase();
}

/**
 * Why each file can't be uploaded, checked before anything is sent: its type, its size, and
 * whether the Project's Document quota has room for it after the files before it. `undefined`
 * means the file may go ahead. The API checks all of this again.
 */
export function refusals(files: File[], limits: UploadLimits): (string | undefined)[] {
  let room = limits.document_quota - limits.documents_counted;
  return files.map((file) => {
    if (!limits.accepted_extensions.includes(extensionOf(file.name))) return UNSUPPORTED_TYPE;
    if (file.size > limits.max_upload_bytes) {
      return `This file is larger than the ${String(Math.floor(limits.max_upload_bytes / (1024 * 1024)))} MB upload limit.`;
    }
    if (room <= 0) return quotaMessage(limits.document_quota);
    room -= 1;
    return undefined;
  });
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
 * Uploads files to the Project: each is checked against the upload limits first, and one that
 * can't be uploaded is refused at once with the reason. For the others, ask the API for a
 * presigned URL (it checks again), PUT the file straight to storage, then confirm. Tracks each
 * file's progress.
 */
export function useUploads(organisationId: string, projectId: string, limits: UploadLimits | undefined) {
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
    // Until the limits have loaded, the API's own checks refuse what doesn't fit.
    const refused = limits ? refusals(files, limits) : files.map(() => undefined);
    const added = files.map((file, index) => ({ key: crypto.randomUUID(), name: file.name, file, refusal: refused[index] }));
    setUploads((current) => [
      ...current,
      ...added.map(({ key, name, refusal }) => ({
        key,
        name,
        state: refusal === undefined ? ({ phase: "uploading", progress: 0 } as const) : ({ phase: "failed", message: refusal } as const),
      })),
    ]);
    for (const { key, file, refusal } of added) if (refusal === undefined) void uploadOne(key, file);
  }

  return { uploads, upload };
}
