import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { server } from "./server";

export type Project = Schemas["ProjectOut"];

export const PROJECT_ARCHIVED = "This Project is archived. An Owner can restore it.";

export const hrProject: Project = {
  id: "7c2d1e69-1e7f-4d2c-8e2f-2a2b7d1a0b01",
  name: "HR handbook",
  description: "Policies for the HR Agent",
  created_at: "2026-10-01T09:30:00Z",
  archived_at: null,
  document_count: 12,
  agent_count: 2,
  embedding_model_id: "multilingual-e5-small",
  ocr_enabled: false,
  embedding_credential_id: null,
};

export const salesProject: Project = {
  id: "7c2d1e69-1e7f-4d2c-8e2f-2a2b7d1a0b02",
  name: "Sales enablement",
  description: "",
  created_at: "2026-10-02T09:30:00Z",
  archived_at: null,
  document_count: 0,
  agent_count: 0,
  embedding_model_id: "multilingual-e5-small",
  ocr_enabled: false,
  embedding_credential_id: null,
};

export const oldProject: Project = {
  id: "7c2d1e69-1e7f-4d2c-8e2f-2a2b7d1a0b03",
  name: "Old launch",
  description: "Retired",
  created_at: "2026-09-01T09:30:00Z",
  archived_at: "2026-10-20T08:00:00Z",
  document_count: 3,
  agent_count: 1,
  embedding_model_id: "multilingual-e5-small",
  ocr_enabled: false,
  embedding_credential_id: null,
};

const ARCHIVED_AT = "2026-11-05T09:00:00Z";

/**
 * A stateful stand-in for the Projects API: creating, editing, archiving and restoring change
 * what it lists, and it refuses what the real API refuses. Records the requests it receives.
 */
export function fakeProjectsApi(options: { projects?: Project[]; instructions?: Record<string, string> } = {}) {
  let projects = [...(options.projects ?? [hrProject, salesProject, oldProject])];
  const instructions: Record<string, string> = { ...options.instructions };
  const requests: { route: string; projectId?: string; body?: unknown }[] = [];
  const find = (id: string) => projects.find((project) => project.id === id);
  const notFound = () => HttpResponse.json({ detail: "Not found" }, { status: 404 });
  const replace = (changed: Project) => {
    projects = projects.map((project) => (project.id === changed.id ? changed : project));
    return HttpResponse.json(changed);
  };
  server.use(
    http.get("*/api/organisations/:organisationId/projects", ({ request }) => {
      const archived = new URL(request.url).searchParams.get("archived") === "true";
      return HttpResponse.json(
        projects
          .filter((project) => (project.archived_at !== null) === archived)
          .sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase())),
      );
    }),
    http.post("*/api/organisations/:organisationId/projects", async ({ request }) => {
      const body = (await request.json()) as Schemas["CreateProjectRequest"];
      requests.push({ route: "create", body });
      const created: Project = {
        id: `7c2d1e69-1e7f-4d2c-8e2f-2a2b7d1a0c${String(projects.length).padStart(2, "0")}`,
        name: body.name.trim(),
        description: body.description.trim(),
        created_at: ARCHIVED_AT,
        archived_at: null,
        document_count: 0,
        agent_count: 0,
        embedding_model_id: "multilingual-e5-small",
        ocr_enabled: false,
        embedding_credential_id: null,
      };
      projects.push(created);
      return HttpResponse.json(created, { status: 201 });
    }),
    http.get("*/api/organisations/:organisationId/projects/:projectId", ({ params }) => {
      const project = find(params.projectId as string);
      return project ? HttpResponse.json(project) : notFound();
    }),
    http.get("*/api/organisations/:organisationId/projects/:projectId/embedding-model", ({ params }) => {
      const project = find(params.projectId as string);
      if (!project) return notFound();
      const state: Schemas["EmbeddingModelStateOut"] = {
        model_id: project.embedding_model_id,
        credential_id: project.embedding_credential_id ?? null,
        pending_model_id: null,
        pending_credential_id: null,
        re_embed: null,
      };
      return HttpResponse.json(state);
    }),
    http.patch("*/api/organisations/:organisationId/projects/:projectId", async ({ params, request }) => {
      const projectId = params.projectId as string;
      const body = (await request.json()) as Schemas["UpdateProjectRequest"];
      requests.push({ route: "update", projectId, body });
      const project = find(projectId) as Project;
      if (project.archived_at !== null) return HttpResponse.json({ detail: PROJECT_ARCHIVED }, { status: 409 });
      return replace({
        ...project,
        name: body.name ?? project.name,
        description: body.description ?? project.description,
        ocr_enabled: body.ocr_enabled ?? project.ocr_enabled,
      });
    }),
    http.post("*/api/organisations/:organisationId/projects/:projectId/archive", ({ params }) => {
      const projectId = params.projectId as string;
      requests.push({ route: "archive", projectId });
      const project = find(projectId) as Project;
      if (project.archived_at !== null) return HttpResponse.json({ detail: PROJECT_ARCHIVED }, { status: 409 });
      return replace({ ...project, archived_at: ARCHIVED_AT });
    }),
    http.get("*/api/organisations/:organisationId/projects/:projectId/instructions", ({ params }) => {
      const projectId = params.projectId as string;
      return find(projectId) ? HttpResponse.json({ markdown: instructions[projectId] ?? "" }) : notFound();
    }),
    http.put("*/api/organisations/:organisationId/projects/:projectId/instructions", async ({ params, request }) => {
      const projectId = params.projectId as string;
      const body = (await request.json()) as Schemas["ProjectInstructions"];
      requests.push({ route: "instructions", projectId, body });
      if ((find(projectId) as Project).archived_at !== null) return HttpResponse.json({ detail: PROJECT_ARCHIVED }, { status: 409 });
      if (body.markdown.length > 20_000) return HttpResponse.json({ detail: [{ msg: "too long" }] }, { status: 422 });
      instructions[projectId] = body.markdown;
      return HttpResponse.json({ markdown: body.markdown });
    }),
    http.post("*/api/organisations/:organisationId/projects/:projectId/restore", ({ params }) => {
      const projectId = params.projectId as string;
      requests.push({ route: "restore", projectId });
      return replace({ ...(find(projectId) as Project), archived_at: null });
    }),
  );
  return { requests };
}
