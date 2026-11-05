import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { server } from "./server";

export type ProjectDocument = Schemas["DocumentOut"];
export type Tag = Schemas["TagOut"];

export const DUPLICATE_TAG = "This Project already has a Tag with that name.";

export function aTag(overrides: Partial<Tag> = {}): Tag {
  return { id: "7a900000-0000-4000-8000-000000000001", name: "HR", document_count: 0, created_at: "2026-11-05T09:00:00Z", ...overrides };
}

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
    tags: [],
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
export function fakeDocumentsApi(options: { documents?: ProjectDocument[]; tags?: Tag[] } = {}) {
  let documents = [...(options.documents ?? [])];
  let tags = [...(options.tags ?? [])];
  const stored = new Map<string, string>();
  // What was PUT for each upload, by upload ID; identical content is refused as a duplicate.
  const contents = new Map<string, string>();
  const contentOf = new Map<string, string>(); // Document ID to its content
  const requests: { route: string; body?: unknown; contentType?: string | null }[] = [];
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/documents", ({ request }) => {
      const query = new URL(request.url).searchParams;
      requests.push({ route: "list", body: query.toString() });
      const q = (query.get("q") ?? "").toLowerCase();
      const statuses = query.getAll("status");
      const tagIds = query.getAll("tag_id");
      return HttpResponse.json(
        documents.filter(
          (document) =>
            document.name.toLowerCase().includes(q) &&
            (statuses.length === 0 || statuses.includes(document.status)) &&
            tagIds.every((id) => document.tags.some((tag) => tag.id === id)),
        ),
      );
    }),
    ...fakeTagRoutes(),
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

  /** Tags, and applying them to Documents, as the API does them. */
  function fakeTagRoutes() {
    const TAGS = "*/api/organisations/:organisationId/projects/:projectId/tags";
    const byName = (a: { name: string }, b: { name: string }) => a.name.toLowerCase().localeCompare(b.name.toLowerCase());
    const counted = () =>
      tags
        .map((tag) => ({ ...tag, document_count: documents.filter((d) => d.tags.some((t) => t.id === tag.id)).length }))
        .sort(byName);
    const refresh = () => {
      const names = new Map(tags.map((tag) => [tag.id, tag.name]));
      documents = documents.map((document) => ({
        ...document,
        tags: document.tags
          .filter((tag) => names.has(tag.id))
          .map((tag) => ({ id: tag.id, name: names.get(tag.id) ?? "" }))
          .sort(byName),
      }));
    };
    const taken = (name: string, id?: string) => tags.some((tag) => tag.id !== id && tag.name.toLowerCase() === name.toLowerCase());
    const refs = (ids: string[]) => tags.filter((tag) => ids.includes(tag.id)).map(({ id, name }) => ({ id, name }));
    return [
      http.get(TAGS, () => HttpResponse.json(counted())),
      http.post(TAGS, async ({ request }) => {
        const { name } = (await request.json()) as Schemas["TagRequest"];
        requests.push({ route: "createTag", body: name });
        if (taken(name.trim())) return HttpResponse.json({ detail: DUPLICATE_TAG }, { status: 409 });
        const tag = aTag({ id: `7a900000-0000-4000-8000-0000000001${String(tags.length).padStart(2, "0")}`, name: name.trim() });
        tags = [...tags, tag];
        return HttpResponse.json(tag, { status: 201 });
      }),
      http.patch(`${TAGS}/:tagId`, async ({ request, params }) => {
        const { name } = (await request.json()) as Schemas["TagRequest"];
        requests.push({ route: "renameTag", body: name });
        if (taken(name.trim(), params.tagId as string)) return HttpResponse.json({ detail: DUPLICATE_TAG }, { status: 409 });
        tags = tags.map((tag) => (tag.id === params.tagId ? { ...tag, name: name.trim() } : tag));
        refresh();
        return HttpResponse.json(counted().find((tag) => tag.id === params.tagId));
      }),
      http.delete(`${TAGS}/:tagId`, ({ params }) => {
        requests.push({ route: "deleteTag", body: params.tagId });
        tags = tags.filter((tag) => tag.id !== params.tagId);
        refresh();
        return new HttpResponse(null, { status: 204 });
      }),
      http.put("*/api/organisations/:organisationId/projects/:projectId/documents/:documentId/tags", async ({ request, params }) => {
        const body = (await request.json()) as Schemas["DocumentTagsRequest"];
        requests.push({ route: "setTags", body });
        documents = documents.map((d) => (d.id === params.documentId ? { ...d, tags: refs(body.tag_ids) } : d));
        refresh();
        return HttpResponse.json(refs(body.tag_ids).sort(byName));
      }),
      http.post("*/api/organisations/:organisationId/projects/:projectId/documents/tags", async ({ request }) => {
        const body = (await request.json()) as Schemas["BulkTagRequest"];
        requests.push({ route: "bulkTag", body });
        const add = body.add ?? [];
        const remove = body.remove ?? [];
        documents = documents.map((d) => {
          if (!body.document_ids.includes(d.id)) return d;
          const kept = d.tags.map((t) => t.id).filter((id) => !remove.includes(id));
          return { ...d, tags: refs([...new Set([...kept, ...add.filter((id) => !remove.includes(id))])]) };
        });
        refresh();
        return new HttpResponse(null, { status: 204 });
      }),
    ];
  }
}
