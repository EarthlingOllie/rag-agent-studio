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
};

const ARCHIVED_AT = "2026-11-05T09:00:00Z";

/**
 * A stateful stand-in for the Projects API: creating, editing, archiving and restoring change
 * what it lists, and it refuses what the real API refuses. Records the requests it receives.
 */
export function fakeProjectsApi(options: { projects?: Project[] } = {}) {
  let projects = [...(options.projects ?? [hrProject, salesProject, oldProject])];
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
      };
      projects.push(created);
      return HttpResponse.json(created, { status: 201 });
    }),
    http.get("*/api/organisations/:organisationId/projects/:projectId", ({ params }) => {
      const project = find(params.projectId as string);
      return project ? HttpResponse.json(project) : notFound();
    }),
    http.patch("*/api/organisations/:organisationId/projects/:projectId", async ({ params, request }) => {
      const projectId = params.projectId as string;
      const body = (await request.json()) as Schemas["UpdateProjectRequest"];
      requests.push({ route: "update", projectId, body });
      const project = find(projectId) as Project;
      if (project.archived_at !== null) return HttpResponse.json({ detail: PROJECT_ARCHIVED }, { status: 409 });
      return replace({ ...project, name: body.name ?? project.name, description: body.description ?? project.description });
    }),
    http.post("*/api/organisations/:organisationId/projects/:projectId/archive", ({ params }) => {
      const projectId = params.projectId as string;
      requests.push({ route: "archive", projectId });
      const project = find(projectId) as Project;
      if (project.archived_at !== null) return HttpResponse.json({ detail: PROJECT_ARCHIVED }, { status: 409 });
      return replace({ ...project, archived_at: ARCHIVED_AT });
    }),
    http.post("*/api/organisations/:organisationId/projects/:projectId/restore", ({ params }) => {
      const projectId = params.projectId as string;
      requests.push({ route: "restore", projectId });
      return replace({ ...(find(projectId) as Project), archived_at: null });
    }),
  );
  return { requests };
}
