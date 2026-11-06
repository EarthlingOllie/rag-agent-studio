import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { type SubmitEvent, useState } from "react";

import { FormError, formValues } from "../auth/AuthLayout";
import { type Session, useMe } from "../auth/session";
import { type Project, projectFailure, useArchiveOrRestore, useCreateProject, useProjects } from "./projects";

export const INPUT = "mt-1 block w-full rounded border border-slate-400 bg-white px-3 py-2 focus:outline-2 focus:outline-slate-900";
export const BUTTON = "rounded border border-slate-400 px-3 py-1 text-sm hover:bg-slate-100 disabled:text-slate-600";

/** The Organisation in the path and whether the signed-in Member is one of its Owners. */
export function useOrganisationRole() {
  const { organisationId } = useParams({ from: "/signed-in/organisations/$organisationId" });
  const session = useMe().data as Session;
  // OrganisationShell renders these pages only for an Organisation the Member belongs to.
  const organisation = session.organisations.find((candidate) => candidate.id === organisationId) as Session["organisations"][number];
  return { organisationId, isOwner: organisation.role === "owner" };
}

/** Name and description fields, shared by creating and editing a Project. */
export function ProjectFields({ idPrefix, project }: { idPrefix: string; project?: Project }) {
  return (
    <>
      <div>
        <label htmlFor={`${idPrefix}-name`} className="block text-sm font-medium">
          Name
        </label>
        <input
          id={`${idPrefix}-name`}
          name="name"
          required
          maxLength={200}
          defaultValue={project?.name}
          className={INPUT}
        />
      </div>
      <div>
        <label htmlFor={`${idPrefix}-description`} className="block text-sm font-medium">
          Description
        </label>
        <textarea
          id={`${idPrefix}-description`}
          name="description"
          rows={2}
          maxLength={2000}
          defaultValue={project?.description}
          className={INPUT}
        />
      </div>
    </>
  );
}

export function projectDetails(form: HTMLFormElement) {
  return formValues(form, ["name", "description"]);
}

function NewProjectForm({ organisationId }: { organisationId: string }) {
  const create = useCreateProject(organisationId);
  const navigate = useNavigate();

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    create.mutate(projectDetails(event.currentTarget), {
      onSuccess: (project) => {
        void navigate({
          to: "/organisations/$organisationId/projects/$projectId",
          params: { organisationId, projectId: project.id },
        });
      },
    });
  }

  return (
    <form aria-labelledby="new-project-heading" onSubmit={onSubmit} className="max-w-md space-y-3">
      <h2 id="new-project-heading" className="text-lg font-semibold">
        New Project
      </h2>
      <FormError message={projectFailure(create.error)} />
      <ProjectFields idPrefix="new-project" />
      <button type="submit" disabled={create.isPending} className={BUTTON}>
        {create.isPending ? "Creating…" : "Create Project"}
      </button>
    </form>
  );
}

function ActiveProjects({ organisationId }: { organisationId: string }) {
  const projects = useProjects(organisationId, false);
  if (projects.isPending) return <p role="status">Loading Projects…</p>;
  if (projects.isError) return <p role="alert">The Projects could not be loaded. Try again shortly.</p>;
  if (projects.data.length === 0) {
    return <p className="text-slate-700">No Projects yet. Create one to start collecting knowledge for a purpose.</p>;
  }
  return (
    <table className="w-full text-left text-sm" aria-label="Projects">
      <thead>
        <tr>
          <th className="py-2 pr-4 font-medium">Name</th>
          <th className="py-2 pr-4 font-medium">Description</th>
          <th className="py-2 pr-4 text-right font-medium">Documents</th>
          <th className="py-2 text-right font-medium">Agents</th>
        </tr>
      </thead>
      <tbody>
        {projects.data.map((project) => (
          <tr key={project.id} className="border-t border-slate-200 align-top">
            <td className="py-2 pr-4">
              <Link
                to="/organisations/$organisationId/projects/$projectId"
                params={{ organisationId, projectId: project.id }}
                className="font-medium underline"
              >
                {project.name}
              </Link>
            </td>
            <td className="py-2 pr-4 text-slate-700">{project.description}</td>
            <td className="py-2 pr-4 text-right">{project.document_count}</td>
            <td className="py-2 text-right">{project.agent_count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ArchivedProjects({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  const projects = useProjects(organisationId, true);
  const restore = useArchiveOrRestore(organisationId, "restore");
  const [restored, setRestored] = useState<string | null>(null);
  if (projects.isPending) return <p role="status">Loading archived Projects…</p>;
  if (projects.isError) return <p role="alert">The archived Projects could not be loaded. Try again shortly.</p>;
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-700">
        Archived Projects are hidden from the Projects list and don't serve.{" "}
        {isOwner ? "Restore one to bring it back." : "Only Owners can restore them."}
      </p>
      <FormError message={projectFailure(restore.error)} />
      {restored && (
        <p role="status" className="text-sm text-green-900">
          {restored} was restored.
        </p>
      )}
      {projects.data.length === 0 ? (
        <p className="text-slate-700">No archived Projects.</p>
      ) : (
        <table className="w-full text-left text-sm" aria-label="Archived Projects">
          <thead>
            <tr>
              <th className="py-2 pr-4 font-medium">Name</th>
              <th className="py-2 pr-4 font-medium">Archived</th>
              <th className="py-2 font-medium">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {projects.data.map((project) => (
              <tr key={project.id} className="border-t border-slate-200 align-top">
                <td className="py-2 pr-4">
                  <Link
                    to="/organisations/$organisationId/projects/$projectId"
                    params={{ organisationId, projectId: project.id }}
                    className="underline"
                  >
                    {project.name}
                  </Link>
                </td>
                <td className="py-2 pr-4">{(project.archived_at as string).slice(0, 10)}</td>
                <td className="py-2">
                  {isOwner && (
                    <button
                      type="button"
                      className={BUTTON}
                      disabled={restore.isPending}
                      aria-label={`Restore ${project.name}`}
                      onClick={() => {
                        setRestored(null);
                        restore.mutate(project.id, {
                          onSuccess: (done) => {
                            setRestored(done.name);
                          },
                        });
                      }}
                    >
                      Restore
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/** The Organisation's Projects with their counts, the archived ones, and a form for a new Project. */
export function ProjectsPage() {
  const { organisationId, isOwner } = useOrganisationRole();
  const [showArchived, setShowArchived] = useState(false);
  const { deleted } = useSearch({ from: "/signed-in/organisations/$organisationId/projects" });
  return (
    <section aria-labelledby="page-heading" className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <h1 id="page-heading" className="text-2xl font-semibold">
          Projects
        </h1>
        <button
          type="button"
          className={BUTTON}
          onClick={() => {
            setShowArchived(!showArchived);
          }}
        >
          {showArchived ? "Show active Projects" : "Show archived Projects"}
        </button>
      </div>
      {deleted && (
        <p role="status" className="text-sm text-green-900">
          {deleted} is being deleted permanently.
        </p>
      )}
      {showArchived ? (
        <ArchivedProjects organisationId={organisationId} isOwner={isOwner} />
      ) : (
        <>
          <ActiveProjects organisationId={organisationId} />
          <NewProjectForm organisationId={organisationId} />
        </>
      )}
    </section>
  );
}
