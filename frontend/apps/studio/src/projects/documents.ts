import type { Schemas } from "@studio/api-client";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import { ProjectRequestError } from "./projects";

export type ProjectDocument = Schemas["DocumentOut"];
export type DocumentStatus = Schemas["DocumentStatus"];
export type FailureCategory = Schemas["FailureCategory"];
export type UploadLimits = Schemas["UploadLimitsOut"];
export type Replacement = Schemas["ReplacementOut"];

/** How often the Document list asks for statuses while a Document is still being processed. */
export const STATUS_POLL_MS = 2000;

export const FINAL_STATUSES: readonly DocumentStatus[] = ["ready", "failed"];

const documentsKey = (organisationId: string, projectId: string) =>
  ["documents", organisationId, projectId] as const;
const limitsKey = (organisationId: string, projectId: string) => [...documentsKey(organisationId, projectId), "limits"] as const;
const statusesKey = (organisationId: string, projectId: string) =>
  [...documentsKey(organisationId, projectId), "statuses"] as const;

function failed(response: Response, error: unknown): ProjectRequestError {
  const detail = (error as { detail?: unknown }).detail;
  return new ProjectRequestError(
    response.status,
    typeof detail === "string" ? detail : undefined,
  );
}

/** Narrows the Document list: part of the name, a status and a Tag. Empty means no filter. */
export interface DocumentFilters {
  q: string;
  status: DocumentStatus | "";
  tagId: string;
}

export const NO_FILTERS: DocumentFilters = { q: "", status: "", tagId: "" };

/**
 * The Project's Documents, filtered on the server. While any isn't Ready or Failed, their statuses are polled from the
 * lightweight status endpoint and merged in, so the list updates without a refresh.
 */
export function useDocuments(
  organisationId: string,
  projectId: string,
  filters: DocumentFilters = NO_FILTERS,
) {
  const path = { organisation_id: organisationId, project_id: projectId };
  const q = filters.q.trim();
  const query = {
    ...(q && { q }),
    ...(filters.status && { status: [filters.status] }),
    ...(filters.tagId && { tag_id: [filters.tagId] }),
  };
  const list = useQuery({
    queryKey: [...documentsKey(organisationId, projectId), "list", query],
    queryFn: async (): Promise<ProjectDocument[]> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/documents",
        {
          params: { path, query },
        },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    // While a new filter loads, the previous list stays up.
    placeholderData: keepPreviousData,
  });
  const inProgress = (list.data ?? []).some((document) => !isSettled(document));
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
      query.state.data?.every(isSettled) ? false : STATUS_POLL_MS,
  });
  // Statuses read before the list was last read (say, before a new edition was uploaded) are
  // older than the list, so they are left out until the next poll.
  const fresh =
    statuses.data !== undefined && statuses.dataUpdatedAt >= list.dataUpdatedAt;
  const latest = new Map(
    (fresh ? statuses.data : []).map((status) => [status.id, status]),
  );
  const documents = list.data?.map((document) => {
    const status = latest.get(document.id);
    return status ? { ...document, ...status } : document;
  });
  // When a new edition becomes Ready its name, size and edition change: read the full list again.
  const swapped = (list.data ?? []).some(
    (document) =>
      document.replacement !== null &&
      latest.has(document.id) &&
      latest.get(document.id)?.replacement === null,
  );
  const queryClient = useQueryClient();
  useEffect(() => {
    if (swapped)
      void queryClient.invalidateQueries({
        queryKey: [...documentsKey(organisationId, projectId), "list"],
      });
  }, [swapped, queryClient, organisationId, projectId]);
  // Failed Documents don't count towards the quota: when one fails, or a retried one leaves
  // Failed, read the upload limits again.
  const failedCount = (documents ?? []).filter((document) => document.status === "failed").length;
  const lastFailedCount = useRef(failedCount);
  useEffect(() => {
    if (lastFailedCount.current === failedCount) return;
    lastFailedCount.current = failedCount;
    void queryClient.invalidateQueries({ queryKey: limitsKey(organisationId, projectId) });
  }, [failedCount, queryClient, organisationId, projectId]);
  return { isError: list.isError, data: documents };
}


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
    const refused = fileRefusal(file, limits);
    if (refused !== undefined) return refused;
    if (room <= 0) return quotaMessage(limits.document_quota);
    room -= 1;
    return undefined;
  });
}

/** Why a file can't be uploaded at all: its type or its size. A new edition only checks these, as it doesn't add a Document. */
export function fileRefusal(file: File, limits: UploadLimits): string | undefined {
  if (!limits.accepted_extensions.includes(extensionOf(file.name))) return UNSUPPORTED_TYPE;
  if (file.size > limits.max_upload_bytes) {
    return `This file is larger than the ${String(Math.floor(limits.max_upload_bytes / (1024 * 1024)))} MB upload limit.`;
  }
  return undefined;
}

/** Whether the Document and any new edition of it are Ready or Failed: nothing left to poll for. */
function isSettled(document: {
  status: DocumentStatus;
  replacement: Replacement | null;
}): boolean {
  return (
    FINAL_STATUSES.includes(document.status) &&
    (document.replacement === null ||
      FINAL_STATUSES.includes(document.replacement.status))
  );
}

/** Whether a new edition can be uploaded: not while the Document or an earlier edition is processing. */
export function canReplace(document: ProjectDocument): boolean {
  return isSettled(document);
}

/** Deletes a Document; the list is refetched. */
export function useDeleteDocument(organisationId: string, projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (documentId: string) => {
      const { error, response } = await api.DELETE(
        "/api/organisations/{organisation_id}/projects/{project_id}/documents/{document_id}",
        {
          params: {
            path: {
              organisation_id: organisationId,
              project_id: projectId,
              document_id: documentId,
            },
          },
        },
      );
      if (!response.ok) throw failed(response, error);
    },
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: documentsKey(organisationId, projectId),
      }),
  });
}

/** The Document that already holds an uploaded file's content. */
export interface ExistingDocument {
  id: string;
  name: string;
}

export type UploadState =
  | { phase: "uploading"; progress: number }
  | { phase: "uploaded" }
  | { phase: "failed"; message: string; existing?: ExistingDocument };

export interface Upload {
  key: string;
  name: string;
  /** For a new edition, the Document it replaces. */
  replacing?: string;
  state: UploadState;
}

/** PUTs the file to the presigned URL, reporting progress as a percentage. */
function putFile(
  url: string,
  file: File,
  contentType: string,
  onProgress: (percent: number) => void,
): Promise<boolean> {
  return new Promise((resolve) => {
    const request = new XMLHttpRequest();
    request.open("PUT", url);
    request.setRequestHeader("Content-Type", contentType);
    // Measured against the file's own size, which is known even when the event's total isn't.
    request.upload.addEventListener("progress", (event) => {
      onProgress(
        Math.min(
          100,
          Math.round((100 * event.loaded) / Math.max(file.size, 1)),
        ),
      );
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

/** Why a confirmation was refused, and for a duplicate, the Document that has the same content. */
function refusal(response: Response, error: unknown): UploadState {
  const conflict = error as
    | Partial<Schemas["UploadConflictResponse"]>
    | undefined;
  const message = failed(response, error).detail ?? TRY_AGAIN;
  if (conflict?.document_id) {
    return {
      phase: "failed",
      message,
      existing: {
        id: conflict.document_id,
        name: conflict.document_name as string,
      },
    };
  }
  return { phase: "failed", message };
}

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
    setUploads((current) =>
      current.map((upload) =>
        upload.key === key ? { ...upload, state } : upload,
      ),
    );
  };

  async function uploadOne(
    key: string,
    file: File,
    replacing?: ProjectDocument,
  ) {
    const started = await api.POST(
      "/api/organisations/{organisation_id}/projects/{project_id}/uploads",
      {
        params: { path },
        body: {
          filename: file.name,
          size_bytes: file.size,
          ...(replacing && { replacing_document_id: replacing.id }),
        },
      },
    );
    if (!started.data) {
      update(key, {
        phase: "failed",
        message: failed(started.response, started.error).detail ?? TRY_AGAIN,
      });
      return;
    }
    const ticket = started.data;
    const stored = await putFile(
      ticket.url,
      file,
      ticket.content_type,
      (progress) => {
        update(key, { phase: "uploading", progress });
      },
    );
    if (!stored) {
      update(key, { phase: "failed", message: TRY_AGAIN });
      return;
    }
    const body = { upload_id: ticket.upload_id };
    const confirmed = replacing
      ? await api.POST(
          "/api/organisations/{organisation_id}/projects/{project_id}/documents/{document_id}/editions",
          {
            params: { path: { ...path, document_id: replacing.id } },
            body,
          },
        )
      : await api.POST(
          "/api/organisations/{organisation_id}/projects/{project_id}/documents",
          { params: { path }, body },
        );
    if (!confirmed.data) {
      update(key, refusal(confirmed.response, confirmed.error));
      return;
    }
    update(key, { phase: "uploaded" });
    await queryClient.invalidateQueries({
      queryKey: documentsKey(organisationId, projectId),
    });
  }

  function upload(files: File[]) {
    // Until the limits have loaded, the API's own checks refuse what doesn't fit.
    const refused = limits ? refusals(files, limits) : files.map(() => undefined);
    const added = files.map((file, index) => ({
      key: crypto.randomUUID(),
      name: file.name,
      file,
      refusal: refused[index],
    }));
    setUploads((current) => [
      ...current,
      ...added.map(({ key, name, refusal }) => ({
        key,
        name,
        state:
          refusal === undefined
            ? ({ phase: "uploading", progress: 0 } as const)
            : ({ phase: "failed", message: refusal } as const),
      })),
    ]);
    for (const { key, file, refusal } of added) if (refusal === undefined) void uploadOne(key, file);
  }

  /** Uploads a newer edition of the Document; its current edition serves until the new one is Ready. */
  function replace(document: ProjectDocument, file: File) {
    const key = crypto.randomUUID();
    const refused = limits ? fileRefusal(file, limits) : undefined;
    setUploads((current) => [
      ...current,
      {
        key,
        name: file.name,
        replacing: document.name,
        state:
          refused === undefined
            ? { phase: "uploading", progress: 0 }
            : { phase: "failed", message: refused },
      },
    ]);
    if (refused === undefined) void uploadOne(key, file, document);
  }

  return { uploads, upload, replace };
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
      queryClient.removeQueries({
        queryKey: statusesKey(organisationId, projectId),
      });
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

export type DocumentDetail = Schemas["DocumentDetailOut"];
export type ChunkPage = Schemas["ChunkPageOut"];

/** How many Chunks the Document viewer shows at a time. */
export const CHUNK_PAGE_SIZE = 50;

/** One Document, with the markdown Docling converted it to. */
export function useDocument(organisationId: string, projectId: string, documentId: string) {
  return useQuery({
    queryKey: [...documentsKey(organisationId, projectId), documentId],
    queryFn: async (): Promise<DocumentDetail> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/documents/{document_id}",
        { params: { path: { organisation_id: organisationId, project_id: projectId, document_id: documentId } } },
      );
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

/** One page of the Document's Chunks, ``page`` counting from 0. */
export function useChunkPage(organisationId: string, projectId: string, documentId: string, page: number) {
  const offset = page * CHUNK_PAGE_SIZE;
  return useQuery({
    queryKey: [...documentsKey(organisationId, projectId), documentId, "chunks", offset],
    queryFn: async (): Promise<ChunkPage> => {
      const { data, error, response } = await api.GET(
        "/api/organisations/{organisation_id}/projects/{project_id}/documents/{document_id}/chunks",
        {
          params: {
            path: { organisation_id: organisationId, project_id: projectId, document_id: documentId },
            query: { offset, limit: CHUNK_PAGE_SIZE },
          },
        },
      );
      if (!data) throw failed(response, error);
      return data;
    },
    // The current page stays on screen while the next one loads.
    placeholderData: keepPreviousData,
  });
}

/** Where the original file downloads from: the API redirects it to a presigned GET. */
export function downloadPath(organisationId: string, projectId: string, documentId: string): string {
  return `/api/organisations/${organisationId}/projects/${projectId}/documents/${documentId}/download`;
}

/**
 * Clears the ingestion Guardrail scan's flag on a Chunk an Editor judges a false positive (the
 * API audits it). The Document and its Chunks are read again, so the count and the note go.
 */
export function useClearChunkFlag(organisationId: string, projectId: string, documentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (chunkId: string) => {
      const { error, response } = await api.DELETE(
        "/api/organisations/{organisation_id}/projects/{project_id}/documents/{document_id}/chunks/{chunk_id}/flag",
        {
          params: {
            path: { organisation_id: organisationId, project_id: projectId, document_id: documentId, chunk_id: chunkId },
          },
        },
      );
      if (!response.ok) throw failed(response, error);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: documentsKey(organisationId, projectId) }),
  });
}

export const CLEAR_FLAG_FAILED = "The flag could not be cleared. Try again shortly.";

/** What to tell the Editor about a failed clear: the API's reason, or a retry hint. */
export function clearFlagFailure(error: Error | null): string | undefined {
  if (error === null) return undefined;
  // Every failed clear is a ProjectRequestError (see `failed`).
  return (error as ProjectRequestError).detail ?? CLEAR_FLAG_FAILED;
}
