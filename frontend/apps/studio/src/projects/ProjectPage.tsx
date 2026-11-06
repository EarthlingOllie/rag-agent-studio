import { Link, Outlet, useParams } from "@tanstack/react-router";
import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { EmbeddingModelSetting } from "./EmbeddingModel";
import { type Project, ProjectRequestError, projectFailure, useArchiveOrRestore, useProject, useUpdateProject } from "./projects";
import { BUTTON, ProjectFields, projectDetails, useOrganisationRole } from "./ProjectsPage";

const TAB = "rounded px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 [&.active]:bg-slate-100 [&.active]:font-medium [&.active]:text-slate-900";

const PROJECT = "/organisations/$organisationId/projects/$projectId";

function useProjectParams() {
  return useParams({ from: "/signed-in/organisations/$organisationId/projects/$projectId" });
}

function EditDetails({ project, organisationId, onDone }: { project: Project; organisationId: string; onDone: () => void }) {
  const update = useUpdateProject(organisationId, project.id);

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    update.mutate(projectDetails(event.currentTarget), { onSuccess: onDone });
  }

  return (
    <form aria-label="Project details" onSubmit={onSubmit} className="max-w-md space-y-3">
      <FormError message={projectFailure(update.error)} />
      <ProjectFields idPrefix="project" project={project} />
      <div className="flex gap-2">
        <button type="submit" disabled={update.isPending} className={BUTTON}>
          {update.isPending ? "Saving…" : "Save"}
        </button>
        <button type="button" className={BUTTON} onClick={onDone}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function ArchiveProject({ project, organisationId }: { project: Project; organisationId: string }) {
  const archive = useArchiveOrRestore(organisationId, "archive");
  const [confirming, setConfirming] = useState(false);
  return (
    <div className="space-y-2">
      <FormError message={projectFailure(archive.error)} />
      {confirming ? (
        <div className="space-y-2">
          <p className="text-sm text-slate-700">
            {project.name} will be hidden from the Projects list and stop serving. An Owner can restore it.
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              className={BUTTON}
              disabled={archive.isPending}
              onClick={() => {
                archive.mutate(project.id, {
                  onSettled: () => {
                    setConfirming(false);
                  },
                });
              }}
            >
              Yes, archive {project.name}
            </button>
            <button
              type="button"
              className={BUTTON}
              onClick={() => {
                setConfirming(false);
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className={BUTTON}
          onClick={() => {
            archive.reset();
            setConfirming(true);
          }}
        >
          Archive
        </button>
      )}
    </div>
  );
}

function ArchivedNotice({ project, organisationId, isOwner }: { project: Project; organisationId: string; isOwner: boolean }) {
  const restore = useArchiveOrRestore(organisationId, "restore");
  return (
    <div role="status" className="space-y-2 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
      <p>
        This Project is archived. It is hidden from the Projects list and doesn't serve.{" "}
        {isOwner ? "Restore it to use it again." : "Only Owners can restore it."}
      </p>
      <FormError message={projectFailure(restore.error)} />
      {isOwner && (
        <button
          type="button"
          className={BUTTON}
          disabled={restore.isPending}
          onClick={() => {
            restore.mutate(project.id);
          }}
        >
          Restore {project.name}
        </button>
      )}
    </div>
  );
}

function ProjectHeader({ project, organisationId, isOwner }: { project: Project; organisationId: string; isOwner: boolean }) {
  const [editing, setEditing] = useState(false);
  const archived = project.archived_at !== null;
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 id="page-heading" className="text-2xl font-semibold">
            {project.name}
          </h1>
          {project.description && <p className="mt-1 text-slate-700">{project.description}</p>}
        </div>
        {!archived && !editing && (
          <button
            type="button"
            className={BUTTON}
            onClick={() => {
              setEditing(true);
            }}
          >
            Edit details
          </button>
        )}
      </div>
      {archived ? (
        <ArchivedNotice project={project} organisationId={organisationId} isOwner={isOwner} />
      ) : (
        <>
          {editing && (
            <EditDetails
              project={project}
              organisationId={organisationId}
              onDone={() => {
                setEditing(false);
              }}
            />
          )}
          <ArchiveProject project={project} organisationId={organisationId} />
          <EmbeddingModelSetting project={project} organisationId={organisationId} />
        </>
      )}
    </div>
  );
}

const TABS = [
  { label: "Documents", to: PROJECT },
  { label: "Instructions", to: `${PROJECT}/instructions` },
  { label: "Agents", to: `${PROJECT}/agents` },
  { label: "Conversations", to: `${PROJECT}/conversations` },
  { label: "Analytics", to: `${PROJECT}/analytics` },
  { label: "Settings", to: `${PROJECT}/settings` },
] as const;

/** One Project: its name and description, Archive and restore, and a tab per area of the Project. */
export function ProjectLayout() {
  const { organisationId, isOwner } = useOrganisationRole();
  const { projectId } = useProjectParams();
  const project = useProject(organisationId, projectId);

  let body;
  if (project.isPending) {
    body = <p role="status">Loading the Project…</p>;
  } else if (project.isError) {
    body =
      project.error instanceof ProjectRequestError && project.error.status === 404 ? (
        <>
          <h1 id="page-heading" className="text-2xl font-semibold">
            Project not found
          </h1>
          <p className="text-slate-700">It doesn't exist in this Organisation.</p>
        </>
      ) : (
        <p role="alert">The Project could not be loaded. Try again shortly.</p>
      );
  } else {
    body = (
      <>
        <ProjectHeader key={project.data.id} project={project.data} organisationId={organisationId} isOwner={isOwner} />
        <nav aria-label="Project" className="flex flex-wrap gap-2 border-b border-slate-200 pb-2">
          {TABS.map((tab) => (
            <Link key={tab.label} to={tab.to} params={{ organisationId, projectId }} activeOptions={{ exact: true }} className={TAB}>
              {tab.label}
            </Link>
          ))}
        </nav>
        <Outlet />
      </>
    );
  }

  return (
    <section aria-labelledby="page-heading" className="space-y-6">
      <Link to="/organisations/$organisationId/projects" params={{ organisationId }} className="text-sm text-slate-700 underline">
        All Projects
      </Link>
      {body}
    </section>
  );
}

function TabPlaceholder({ title, children }: { title: string; children: string }) {
  return (
    <section aria-labelledby="tab-heading">
      <h2 id="tab-heading" className="text-lg font-semibold">
        {title}
      </h2>
      <p className="mt-2 text-slate-700">{children}</p>
    </section>
  );
}

export function InstructionsTab() {
  return (
    <TabPlaceholder title="Instructions">
      Project Instructions, the text every Agent in this Project follows, arrive in a later release.
    </TabPlaceholder>
  );
}

export function ConversationsTab() {
  return (
    <TabPlaceholder title="Conversations">
      No Conversations yet. Conversations with this Project's Agents will appear here in a later release.
    </TabPlaceholder>
  );
}

export function AnalyticsTab() {
  return <TabPlaceholder title="Analytics">Analytics for this Project's Agents arrive in a later release.</TabPlaceholder>;
}
