import { Link, useParams, useSearch } from "@tanstack/react-router";
import { useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { type Session, useMe } from "../auth/session";
import {
  button,
  EmptyState,
  layout,
  Notice,
  PageHeader,
  Segmented,
  Skeleton,
  table,
  ToastProvider,
  useToast,
} from "../design";
import { NewProjectDialog } from "./ProjectDetailsDialog";
import { projectFailure, useArchiveOrRestore, useProjects } from "./projects";

export const INPUT =
  "mt-1 block w-full rounded border border-field bg-surface px-3 py-2 focus:outline-2 focus:outline-accent";
export const BUTTON =
  "rounded border border-field px-3 py-1 text-sm hover:bg-sunken disabled:text-muted";

/** The Organisation in the path and whether the signed-in Member is one of its Owners. */
export function useOrganisationRole() {
  const { organisationId } = useParams({
    from: "/signed-in/organisations/$organisationId",
  });
  const session = useMe().data as Session;
  // OrganisationShell renders these pages only for an Organisation the Member belongs to.
  const organisation = session.organisations.find(
    (candidate) => candidate.id === organisationId,
  ) as Session["organisations"][number];
  return { organisationId, isOwner: organisation.role === "owner" };
}

type Shown = "active" | "archived";

const SHOWN_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "archived", label: "Archived" },
] as const;

function ActiveProjects({ organisationId }: { organisationId: string }) {
  const projects = useProjects(organisationId, false);
  if (projects.isPending) return <Skeleton label="Loading Projects" />;
  if (projects.isError)
    return (
      <EmptyState
        tone="error"
        title="The Projects could not be loaded"
        description="Try again shortly."
      />
    );
  if (projects.data.length === 0) {
    return (
      <EmptyState
        icon="projects"
        title="No Projects yet"
        description="Create one with New Project to start collecting knowledge for a purpose."
      />
    );
  }
  return (
    <div className={table.wrap}>
      <table className={table.table} aria-label="Projects">
        <thead>
          <tr>
            <th scope="col" className={table.th}>
              Name
            </th>
            <th scope="col" className={table.th}>
              Description
            </th>
            <th scope="col" className={table.thNumeric}>
              Documents
            </th>
            <th scope="col" className={table.thNumeric}>
              Agents
            </th>
          </tr>
        </thead>
        <tbody>
          {projects.data.map((project) => (
            <tr key={project.id} className={table.row}>
              <td className={table.td}>
                <Link
                  to="/organisations/$organisationId/projects/$projectId"
                  params={{ organisationId, projectId: project.id }}
                  className={`${table.link} whitespace-nowrap`}
                >
                  {project.name}
                </Link>
              </td>
              <td className={table.tdMuted}>
                <span
                  className="block max-w-md truncate"
                  title={project.description || undefined}
                >
                  {project.description}
                </span>
              </td>
              <td className={table.tdNumeric}>{project.document_count}</td>
              <td className={table.tdNumeric}>{project.agent_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ArchivedProjects({
  organisationId,
  isOwner,
}: {
  organisationId: string;
  isOwner: boolean;
}) {
  const projects = useProjects(organisationId, true);
  const restore = useArchiveOrRestore(organisationId, "restore");
  const toast = useToast();
  if (projects.isPending) return <Skeleton label="Loading archived Projects" />;
  if (projects.isError)
    return (
      <EmptyState
        tone="error"
        title="The archived Projects could not be loaded"
        description="Try again shortly."
      />
    );
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted">
        Archived Projects are hidden from the Projects list and don't serve.{" "}
        {isOwner
          ? "Restore one to bring it back."
          : "Only Owners can restore them."}
      </p>
      <FormError message={projectFailure(restore.error)} />
      {projects.data.length === 0 ? (
        <EmptyState
          icon="projects"
          title="No archived Projects"
          description="A Project you archive is kept here, with its Documents and Agents."
        />
      ) : (
        <div className={table.wrap}>
          <table className={table.table} aria-label="Archived Projects">
            <thead>
              <tr>
                <th scope="col" className={table.th}>
                  Name
                </th>
                <th scope="col" className={table.th}>
                  Archived
                </th>
                <th scope="col" className={table.th}>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {projects.data.map((project) => (
                <tr key={project.id} className={table.row}>
                  <td className={table.td}>
                    <Link
                      to="/organisations/$organisationId/projects/$projectId"
                      params={{ organisationId, projectId: project.id }}
                      className={`${table.link} whitespace-nowrap`}
                    >
                      {project.name}
                    </Link>
                  </td>
                  <td className={`${table.tdMuted} font-mono text-[13px]`}>
                    {(project.archived_at as string).slice(0, 10)}
                  </td>
                  <td className={`${table.td} text-right`}>
                    {isOwner && (
                      <button
                        type="button"
                        className={button.secondary}
                        disabled={restore.isPending}
                        aria-label={`Restore ${project.name}`}
                        onClick={() => {
                          restore.mutate(project.id, {
                            onSuccess: (done) => {
                              toast.show(`${done.name} was restored.`);
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
        </div>
      )}
    </div>
  );
}

/**
 * The Organisation's Projects page: a page header with New Project (the one primary), an
 * Active / Archived filter, and the Projects as a table card with their counts, or the archived
 * ones with their dates and, for Owners, Restore.
 */
export function ProjectsPage() {
  return (
    <ToastProvider>
      <Projects />
    </ToastProvider>
  );
}

/** The page itself, inside the ToastProvider that confirms a restore. */
function Projects() {
  const { organisationId, isOwner } = useOrganisationRole();
  const [shown, setShown] = useState<Shown>("active");
  const [creating, setCreating] = useState(false);
  const { deleted } = useSearch({ from: "/signed-in/organisations/$organisationId/projects" });
  const archived = shown === "archived";
  return (
    <section aria-label="Projects" className={layout.stack}>
      <PageHeader
        title="Projects"
        description="Each Project holds the Documents its Agents answer from."
        actions={
          !archived && (
            <button
              type="button"
              className={button.primary}
              onClick={() => {
                setCreating(true);
              }}
            >
              New Project
            </button>
          )
        }
      />
      {deleted && <Notice tone="success">{deleted} is being deleted permanently.</Notice>}
      <div className={layout.toolbar}>
        <Segmented label="Projects shown" options={SHOWN_OPTIONS} value={shown} onChange={setShown} />
      </div>
      {archived ? (
        <ArchivedProjects organisationId={organisationId} isOwner={isOwner} />
      ) : (
        <ActiveProjects organisationId={organisationId} />
      )}
      {creating && (
        <NewProjectDialog
          organisationId={organisationId}
          onClose={() => {
            setCreating(false);
          }}
        />
      )}
    </section>
  );
}
