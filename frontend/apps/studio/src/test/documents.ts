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
    replacement: null,
    ...overrides,
  };
}

const NEXT: Partial<Record<ProjectDocument["status"], ProjectDocument["status"]>> = { queued: "processing", processing: "ready" };

/** One poll's progress: the Document moves a step on, and so does a new edition, which replaces it once Ready. */
function advance(document: ProjectDocument): ProjectDocument {
  const status = NEXT[document.status];
  if (status) return { ...document, status, chunk_count: status === "ready" ? 4 : 0 };
  const { replacement } = document;
  const next = replacement && NEXT[replacement.status];
  if (!replacement || !next) return document;
  if (next === "processing") return { ...document, replacement: { ...replacement, status: next } };
  return { ...document, name: replacement.name, edition: replacement.edition, chunk_count: 6, replacement: null };
}

/**
 * A stateful stand-in for the Documents API and the object store. Starting an upload refuses
 * what the API refuses; the PUT goes to a fake storage host; confirming adds a Queued Document.
 * Each poll of the status endpoint moves every unfinished Document one step on, to Ready.
 */
export function fakeDocumentsApi(options: { documents?: ProjectDocument[] } = {}) {
  let documents = [...(options.documents ?? [])];
  const stored = new Map<string, string>();
  // What was PUT for each upload, by upload ID; identical content is refused as a duplicate.
  const contents = new Map<string, string>();
  const contentOf = new Map<string, string>(); // Document ID to its content
  const requests: { route: string; body?: unknown; contentType?: string | null }[] = [];
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/documents", () => HttpResponse.json(documents)),
    http.get("*/api/organisations/:organisationId/projects/:projectId/documents/statuses", () => {
      documents = documents.map(advance);
      requests.push({ route: "statuses" });
      return HttpResponse.json(
        documents.map(({ id, status, error_message, chunk_count, replacement }) => ({
          id,
          status,
          error_message,
          chunk_count,
          replacement,
        })),
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
    http.put(`${STORAGE}/:uploadId`, async ({ request, params }) => {
      const body = await request.text();
      contents.set(params.uploadId as string, body);
      requests.push({ route: "put", body, contentType: request.headers.get("Content-Type") });
      return new HttpResponse(null, { status: 200 });
    }),
    http.post("*/api/organisations/:organisationId/projects/:projectId/documents", async ({ request }) => {
      const body = (await request.json()) as Schemas["ConfirmUploadRequest"];
      requests.push({ route: "confirm", body });
      const refused = duplicateOf(body.upload_id);
      if (refused) return refused;
      const created = aDocument({
        id: `d0c00000-0000-4000-8000-0000000001${String(documents.length).padStart(2, "0")}`,
        name: stored.get(body.upload_id) ?? "",
        status: "queued",
        chunk_count: 0,
        size_bytes: 512,
      });
      documents = [created, ...documents];
      contentOf.set(created.id, contents.get(body.upload_id) ?? "");
      return HttpResponse.json(created, { status: 201 });
    }),
    http.post(`*/api/organisations/:organisationId/projects/:projectId/documents/:documentId/editions`, async ({ request, params }) => {
      const body = (await request.json()) as Schemas["ConfirmUploadRequest"];
      requests.push({ route: "replace", body });
      const refused = duplicateOf(body.upload_id);
      if (refused) return refused;
      documents = documents.map((document) =>
        document.id === params.documentId
          ? {
              ...document,
              replacement: { edition: document.edition + 1, name: stored.get(body.upload_id) ?? "", status: "queued", error_message: null },
            }
          : document,
      );
      contentOf.set(params.documentId as string, contents.get(body.upload_id) ?? "");
      return HttpResponse.json(
        documents.find((document) => document.id === params.documentId),
        { status: 202 },
      );
    }),
    http.delete(`*/api/organisations/:organisationId/projects/:projectId/documents/:documentId`, ({ params }) => {
      requests.push({ route: "delete", body: params.documentId });
      documents = documents.filter((document) => document.id !== params.documentId);
      return new HttpResponse(null, { status: 204 });
    }),
  );

  function duplicateOf(uploadId: string) {
    const content = contents.get(uploadId);
    const existing = documents.find((document) => contentOf.get(document.id) === content);
    if (!existing) return undefined;
    return HttpResponse.json(
      { detail: `This file is already in the Project as ${existing.name}.`, document_id: existing.id, document_name: existing.name },
      { status: 409 },
    );
  }
  return { requests };
}
