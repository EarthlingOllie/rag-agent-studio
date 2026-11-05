import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { server } from "./server";

export type ProjectDocument = Schemas["DocumentOut"];
export type UploadLimits = Schemas["UploadLimitsOut"];

/** Uploads go to the object store's bucket on the Studio's own origin (the dev proxy forwards it). */
export const STORAGE = "*/studio-documents";
export const UNSUPPORTED = "This file type isn't supported. Upload a PDF, DOCX, PPTX, HTML, Markdown or TXT file.";
const SUPPORTED = /\.(pdf|docx|pptx|html?|md|markdown|txt)$/i;

export function aDocument(overrides: Partial<ProjectDocument> = {}): ProjectDocument {
  return {
    id: "d0c00000-0000-4000-8000-000000000001",
    name: "handbook.pdf",
    mime_type: "application/pdf",
    size_bytes: 2_621_440,
    content_hash: "a".repeat(64),
    status: "ready",
    error_message: null,
    error_category: null,
    attempt_count: 1,
    edition: 1,
    chunk_count: 12,
    created_at: "2026-11-05T09:00:00Z",
    updated_at: "2026-11-05T09:01:00Z",
    ...overrides,
  };
}

const NEXT: Partial<Record<ProjectDocument["status"], ProjectDocument["status"]>> = { queued: "processing", processing: "ready" };

/**
 * A stateful stand-in for the Documents API and the object store. Starting an upload refuses
 * what the API refuses; the PUT goes to a fake storage host; confirming adds a Queued Document.
 * Each poll of the status endpoint moves every unfinished Document one step on, to Ready.
 */
export function anUploadLimits(overrides: Partial<UploadLimits> = {}): UploadLimits {
  return {
    accepted_extensions: [".pdf", ".docx", ".pptx", ".html", ".htm", ".md", ".markdown", ".txt"],
    max_upload_bytes: 50 * 1024 * 1024,
    document_quota: 500,
    documents_counted: 0,
    ...overrides,
  };
}

/**
 * Retrying a Failed Document puts it back to Queued, and the polls then move it on to Ready.
 * The upload limits count the Documents that aren't Failed, against `limits.document_quota`.
 */
export function fakeDocumentsApi(options: { documents?: ProjectDocument[]; limits?: Partial<UploadLimits> } = {}) {
  let documents = [...(options.documents ?? [])];
  const stored = new Map<string, string>();
  const requests: { route: string; body?: unknown; contentType?: string | null }[] = [];
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/documents", () => HttpResponse.json(documents)),
    http.get("*/api/organisations/:organisationId/projects/:projectId/documents/statuses", () => {
      documents = documents.map((document) => {
        const status = NEXT[document.status];
        return status ? { ...document, status, chunk_count: status === "ready" ? 4 : 0 } : document;
      });
      requests.push({ route: "statuses" });
      return HttpResponse.json(
        documents.map(({ id, status, error_message, error_category, attempt_count, chunk_count }) => ({
          id,
          status,
          error_message,
          error_category,
          attempt_count,
          chunk_count,
        })),
      );
    }),
    http.get("*/api/organisations/:organisationId/projects/:projectId/uploads/limits", () =>
      HttpResponse.json(
        anUploadLimits({ documents_counted: documents.filter((d) => d.status !== "failed").length, ...options.limits }),
      ),
    ),
    http.post("*/api/organisations/:organisationId/projects/:projectId/documents/:documentId/retry", ({ params }) => {
      requests.push({ route: "retry", body: params.documentId });
      const retried = documents.find((d) => d.id === params.documentId);
      if (retried?.status !== "failed") {
        return HttpResponse.json({ detail: "Only a Failed Document can be retried." }, { status: 409 });
      }
      const queued = { ...retried, status: "queued" as const, error_message: null, error_category: null };
      documents = documents.map((d) => (d.id === queued.id ? queued : d));
      return HttpResponse.json(queued);
    }),
    http.post("*/api/organisations/:organisationId/projects/:projectId/uploads", async ({ request }) => {
      const body = (await request.json()) as Schemas["StartUploadRequest"];
      requests.push({ route: "start", body });
      if (!SUPPORTED.test(body.filename)) return HttpResponse.json({ detail: UNSUPPORTED }, { status: 415 });
      const uploadId = `u${String(requests.length)}`;
      stored.set(uploadId, body.filename);
      return HttpResponse.json(
        {
          upload_id: uploadId,
          url: `${new URL(request.url).origin}/studio-documents/${uploadId}?X-Amz-Signature=abc`,
          method: "PUT",
          content_type: "text/markdown",
          expires_at: "2026-11-05T09:15:00Z",
        },
        { status: 201 },
      );
    }),
    http.put(`${STORAGE}/:uploadId`, async ({ request }) => {
      requests.push({ route: "put", body: await request.text(), contentType: request.headers.get("Content-Type") });
      return new HttpResponse(null, { status: 200 });
    }),
    http.post("*/api/organisations/:organisationId/projects/:projectId/documents", async ({ request }) => {
      const body = (await request.json()) as Schemas["ConfirmUploadRequest"];
      requests.push({ route: "confirm", body });
      const created = aDocument({
        id: `d0c00000-0000-4000-8000-0000000001${String(documents.length).padStart(2, "0")}`,
        name: stored.get(body.upload_id) ?? "",
        status: "queued",
        chunk_count: 0,
        size_bytes: 512,
      });
      documents = [created, ...documents];
      return HttpResponse.json(created, { status: 201 });
    }),
  );
  return { requests };
}
