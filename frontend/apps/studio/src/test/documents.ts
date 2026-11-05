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

/**
 * A stateful stand-in for the Documents API and the object store. Starting an upload refuses
 * what the API refuses; the PUT goes to a fake storage host; confirming adds a Queued Document.
 * Each poll of the status endpoint moves every unfinished Document one step on, to Ready.
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
        return status ? { ...document, status, chunk_count: status === "ready" ? 4 : 0 } : document;
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
  );
  return { requests };
}

export type DocumentDetail = Schemas["DocumentDetailOut"];
export type Chunk = Schemas["ChunkOut"];

export function aChunk(overrides: Partial<Chunk> = {}): Chunk {
  return {
    id: `c0c00000-0000-4000-8000-${String(overrides.ordinal ?? 0).padStart(12, "0")}`,
    ordinal: 0,
    text: "Everyone gets 25 days of annual leave a year.",
    heading_path: ["Northwind staff handbook", "Annual leave"],
    page_start: 1,
    page_end: 1,
    embedding_model_id: "multilingual-e5-small",
    ...overrides,
  };
}

/** The Document as the Document list has it: without its markdown. */
function listed(document: DocumentDetail): ProjectDocument {
  return Object.fromEntries(Object.entries(document).filter(([key]) => key !== "markdown")) as ProjectDocument;
}

/**
 * A stand-in for the Document viewer's API: the Document list (just this Document), the
 * Document with its markdown, and its Chunks a page at a time, as the API pages them.
 */
export function fakeDocumentViewerApi({ document, chunks }: { document: DocumentDetail; chunks: Chunk[] }) {
  const requests: { offset: number; limit: number }[] = [];
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/documents", () => HttpResponse.json([listed(document)])),
    http.get("*/api/organisations/:organisationId/projects/:projectId/documents/:documentId", ({ params }) =>
      params.documentId === document.id ? HttpResponse.json(document) : HttpResponse.json({ detail: "Not found" }, { status: 404 }),
    ),
    http.get("*/api/organisations/:organisationId/projects/:projectId/documents/:documentId/chunks", ({ request }) => {
      const query = new URL(request.url).searchParams;
      const offset = Number(query.get("offset") ?? 0);
      const limit = Number(query.get("limit") ?? 50);
      requests.push({ offset, limit });
      return HttpResponse.json({ items: chunks.slice(offset, offset + limit), total: chunks.length, offset, limit });
    }),
  );
  return { requests };
}
