import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { server } from "./server";

export type ProjectDocument = Schemas["DocumentOut"];

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
    edition: 1,
    chunk_count: 12,
    created_at: "2026-11-05T09:00:00Z",
    updated_at: "2026-11-05T09:01:00Z",
    ...overrides,
  };
}

const NEXT: Partial<Record<ProjectDocument["status"], ProjectDocument["status"]>> = { queued: "processing", processing: "ready" };

export const IN_PROGRESS = "This Document is still being processed. Retry it once it is Ready or Failed.";

/**
 * A stateful stand-in for the Documents API and the object store. Starting an upload refuses
 * what the API refuses; the PUT goes to a fake storage host; confirming adds a Queued Document.
 * Retrying a Ready or Failed Document sets it back to Queued. Each poll of the status endpoint
 * moves every unfinished Document one step on, to Ready.
 */
export function fakeDocumentsApi(options: { documents?: ProjectDocument[] } = {}) {
  let documents = [...(options.documents ?? [])];
  const stored = new Map<string, string>();
  const requests: { route: string; body?: unknown; contentType?: string | null }[] = [];
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/documents", () => HttpResponse.json(documents)),
    http.get("*/api/organisations/:organisationId/projects/:projectId/documents/statuses", () => {
      documents = documents.map((document) => {
        const status = NEXT[document.status];
        return status ? { ...document, status, error_message: null, chunk_count: status === "ready" ? 4 : 0 } : document;
      });
      requests.push({ route: "statuses" });
      return HttpResponse.json(
        documents.map(({ id, status, error_message, chunk_count }) => ({ id, status, error_message, chunk_count })),
      );
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
    http.post("*/api/organisations/:organisationId/projects/:projectId/documents/:documentId/retry", ({ params }) => {
      const documentId = params.documentId as string;
      requests.push({ route: "retry", body: documentId });
      const document = documents.find((candidate) => candidate.id === documentId) as ProjectDocument;
      if (!["ready", "failed"].includes(document.status)) return HttpResponse.json({ detail: IN_PROGRESS }, { status: 409 });
      const queued: ProjectDocument = { ...document, status: "queued", error_message: null };
      documents = documents.map((candidate) => (candidate.id === documentId ? queued : candidate));
      return HttpResponse.json(queued, { status: 202 });
    }),
  );
  return { requests };
}
