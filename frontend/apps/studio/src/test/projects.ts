import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { server } from "./server";

export type Project = Schemas["ProjectOut"];

export const PROJECT_ARCHIVED = "This Project is archived. An Owner can restore it.";
export const ARCHIVE_BEFORE_DELETING = "Only an archived Project can be deleted. Archive it first.";
export const NAME_MISMATCH = "Type the Project's name exactly to delete it.";

export const STALE_INSTRUCTIONS =
  "Someone else saved these Instructions after you opened them. Load their changes, or save yours over them.";
export const NOTHING_TO_PUBLISH = "The Draft is the same as the Current Version, so there's nothing to publish.";
export const NOTHING_TO_REVERT = "There's no earlier Version to revert to.";

type InstructionsHistory = Schemas["InstructionsHistoryOut"];
type InstructionsVersion = Schemas["InstructionsVersionOut"];

const PUBLISHED_AT = "2026-11-06T10:15:00Z";
const AUTHOR = { id: "6a1b0c58-0d6e-4c1b-9d1e-1f1a6c0f0a01", name: "Ada Lovelace" };

/** An Instructions Version, published by Ada unless the overrides say otherwise. */
export function instructionsVersion(number: number, overrides: Partial<InstructionsVersion> = {}): InstructionsVersion {
  return {
    id: `5e0c7a10-0000-4000-8000-${String(number).padStart(12, "0")}`,
    number,
    markdown: `Rules ${String(number)}`,
    note: `Note ${String(number)}`,
    author: AUTHOR,
    created_at: "2026-11-01T09:00:00Z",
    previous_version_id: null,
    ...overrides,
  };
}

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
 * A stateful stand-in for the Projects API: creating, editing, archiving, restoring and deleting change
 * what it lists, and it refuses what the real API refuses. Records the requests it receives.
 */
export function fakeProjectsApi(
  options: {
    projects?: Project[];
    instructions?: Record<string, string>;
    versions?: Record<string, InstructionsHistory>;
    /** Refuses every Instructions diff with this status. */
    diffStatus?: number;
  } = {},
) {
  let projects = [...(options.projects ?? [hrProject, salesProject, oldProject])];
  const instructions: Record<string, string> = { ...options.instructions };
  const versions: Record<string, InstructionsHistory> = { ...options.versions };
  const historyOf = (id: string): InstructionsHistory => versions[id] ?? { current_version_id: null, versions: [] };
  const currentOf = (history: InstructionsHistory) => history.versions.find((version) => version.id === history.current_version_id);
  const requests: { route: string; projectId?: string; body?: unknown }[] = [];
  // Each Project's Instructions Draft revision: it moves on whenever the text changes.
  const revisions: Record<string, number> = {};
  const draftOf = (projectId: string) => ({ markdown: instructions[projectId] ?? "", revision: revisions[projectId] ?? 1 });
  const saveInstructions = (projectId: string, markdown: string) => {
    if (markdown !== draftOf(projectId).markdown) revisions[projectId] = draftOf(projectId).revision + 1;
    instructions[projectId] = markdown;
    return draftOf(projectId);
  };
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
      return find(projectId) ? HttpResponse.json(draftOf(projectId)) : notFound();
    }),
    http.put("*/api/organisations/:organisationId/projects/:projectId/instructions", async ({ params, request }) => {
      const projectId = params.projectId as string;
      const body = (await request.json()) as Schemas["ProjectInstructions"];
      requests.push({ route: "instructions", projectId, body });
      if ((find(projectId) as Project).archived_at !== null) return HttpResponse.json({ detail: PROJECT_ARCHIVED }, { status: 409 });
      if (body.markdown.length > 20_000) return HttpResponse.json({ detail: [{ msg: "too long" }] }, { status: 422 });
      const base = new URL(request.url).searchParams.get("base_revision");
      if (base !== null && Number(base) !== draftOf(projectId).revision)
        return HttpResponse.json({ detail: STALE_INSTRUCTIONS, latest: draftOf(projectId) }, { status: 409 });
      return HttpResponse.json(saveInstructions(projectId, body.markdown));
    }),
    http.get("*/api/organisations/:organisationId/projects/:projectId/instructions/versions", ({ params }) => {
      const projectId = params.projectId as string;
      return find(projectId) ? HttpResponse.json(historyOf(projectId)) : notFound();
    }),
    http.post("*/api/organisations/:organisationId/projects/:projectId/instructions/versions", async ({ params, request }) => {
      const projectId = params.projectId as string;
      const body = (await request.json()) as Schemas["PublishInstructionsRequest"];
      requests.push({ route: "publish", projectId, body });
      if ((find(projectId) as Project).archived_at !== null) return HttpResponse.json({ detail: PROJECT_ARCHIVED }, { status: 409 });
      const note = body.note.trim();
      if (!note || note.length > 500) return HttpResponse.json({ detail: [{ msg: "bad note" }] }, { status: 422 });
      const history = historyOf(projectId);
      const current = currentOf(history);
      const markdown = instructions[projectId] ?? "";
      if (markdown === (current?.markdown ?? "")) return HttpResponse.json({ detail: NOTHING_TO_PUBLISH }, { status: 409 });
      const version = instructionsVersion(history.versions.length + 1, {
        markdown,
        note,
        created_at: PUBLISHED_AT,
        previous_version_id: current?.id ?? null,
      });
      versions[projectId] = { current_version_id: version.id, versions: [version, ...history.versions] };
      return HttpResponse.json(version, { status: 201 });
    }),
    http.get("*/api/organisations/:organisationId/projects/:projectId/instructions/diff", ({ params, request }) => {
      const projectId = params.projectId as string;
      const query = new URL(request.url).searchParams;
      if (options.diffStatus) return HttpResponse.json({ detail: "Boom" }, { status: options.diffStatus });
      const side = (id: string) => {
        const version = historyOf(projectId).versions.find((candidate) => candidate.id === id);
        return {
          side: version ? { kind: "version" as const, version: { id: version.id, number: version.number } } : { kind: "draft" as const, version: null },
          lines: (version ? version.markdown : (instructions[projectId] ?? "")).split("\n").filter(Boolean),
        };
      };
      const before = side(query.get("from") as string);
      const after = side(query.get("to") as string);
      // A simple line diff: lines on both sides are equal, the rest deleted or inserted.
      const lines = [
        ...before.lines.map((text) => ({ op: after.lines.includes(text) ? ("equal" as const) : ("delete" as const), text })),
        ...after.lines.filter((text) => !before.lines.includes(text)).map((text) => ({ op: "insert" as const, text })),
      ];
      return HttpResponse.json({ from: before.side, to: after.side, lines });
    }),
    http.post("*/api/organisations/:organisationId/projects/:projectId/instructions/revert", ({ params }) => {
      const projectId = params.projectId as string;
      requests.push({ route: "revert", projectId });
      if ((find(projectId) as Project).archived_at !== null) return HttpResponse.json({ detail: PROJECT_ARCHIVED }, { status: 409 });
      const history = historyOf(projectId);
      const target = history.versions.find((version) => version.id === currentOf(history)?.previous_version_id);
      if (!target) return HttpResponse.json({ detail: NOTHING_TO_REVERT }, { status: 409 });
      versions[projectId] = { ...history, current_version_id: target.id };
      return HttpResponse.json(target);
    }),
    http.post("*/api/organisations/:organisationId/projects/:projectId/restore", ({ params }) => {
      const projectId = params.projectId as string;
      requests.push({ route: "restore", projectId });
      return replace({ ...(find(projectId) as Project), archived_at: null });
    }),
    http.delete("*/api/organisations/:organisationId/projects/:projectId", async ({ params, request }) => {
      const projectId = params.projectId as string;
      const body = (await request.json()) as Schemas["DeleteProjectRequest"];
      requests.push({ route: "delete", projectId, body });
      const project = find(projectId);
      if (!project) return notFound();
      if (project.archived_at === null) return HttpResponse.json({ detail: ARCHIVE_BEFORE_DELETING }, { status: 409 });
      if (body.confirm_name !== project.name) return HttpResponse.json({ detail: NAME_MISMATCH }, { status: 400 });
      projects = projects.filter((candidate) => candidate.id !== projectId);
      return new HttpResponse(null, { status: 202 });
    }),
  );
  return {
    requests,
    /** A colleague saves `markdown` as the Project's Instructions Draft. */
    colleagueSavesInstructions: (projectId: string, markdown: string) => saveInstructions(projectId, markdown),
  };
}
