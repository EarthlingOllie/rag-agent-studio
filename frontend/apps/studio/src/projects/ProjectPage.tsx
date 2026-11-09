import { Link, Outlet, useNavigate, useParams } from "@tanstack/react-router";
import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { EmbeddingModelSetting } from "./EmbeddingModel";
import {
  type Project,
  ProjectRequestError,
  projectFailure,
  useArchiveOrRestore,
  useDeleteProject,
  useProject,
  useUpdateProject,
} from "./projects";
import { BUTTON, INPUT, ProjectFields, projectDetails, useOrganisationRole } from "./ProjectsPage";

const TAB = "rounded px-3 py-2 text-sm text-ink-2 hover:bg-sunken [&.active]:bg-sunken [&.active]:font-medium [&.active]:text-ink";

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
          <p className="text-sm text-muted">
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

/** Owners only, on an archived Project: deletion is confirmed by typing the Project's name exactly. */
function DeletePermanently({ project, organisationId }: { project: Project; organisationId: string }) {
  const remove = useDeleteProject(organisationId, project.id);
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState("");
  const title = `Delete ${project.name} permanently`;

  if (!confirming) {
    return (
      <button
        type="button"
        className={BUTTON}
        onClick={() => {
          remove.reset();
          setTyped("");
          setConfirming(true);
        }}
      >
        Delete permanently
      </button>
    );
  }

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    remove.mutate(typed, {
      onSuccess: () => {
        void navigate({ to: "/organisations/$organisationId/projects", params: { organisationId }, search: { deleted: project.name } });
      },
    });
  }

  return (
    <form aria-label={title} onSubmit={onSubmit} className="space-y-2 rounded border border-danger bg-surface p-3 text-ink">
      <p>
        Deleting {project.name} removes its Documents, stored files, Agents and Conversations for good. This can&apos;t be undone.
      </p>
      <FormError message={projectFailure(remove.error)} />
      <div>
        <label htmlFor="delete-project-name" className="block text-sm font-medium">
          Type {project.name} to confirm
        </label>
        <input
          id="delete-project-name"
          autoComplete="off"
          className={INPUT}
          value={typed}
          onChange={(event) => {
            setTyped(event.target.value);
          }}
        />
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          className="rounded border border-danger bg-danger px-3 py-1 text-sm text-on-danger hover:bg-danger/90 disabled:border-field disabled:bg-sunken disabled:text-muted"
          disabled={typed !== project.name || remove.isPending}
        >
          {title}
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
    </form>
  );
}

function ArchivedNotice({ project, organisationId, isOwner }: { project: Project; organisationId: string; isOwner: boolean }) {
  const restore = useArchiveOrRestore(organisationId, "restore");
  return (
    <div role="status" className="space-y-2 rounded border border-flag bg-flag-soft p-3 text-sm text-flag">
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
      {isOwner && <DeletePermanently project={project} organisationId={organisationId} />}
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
          {project.description && <p className="mt-1 text-muted">{project.description}</p>}
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
          <p className="text-muted">It doesn't exist in this Organisation.</p>
        </>
      ) : (
        <p role="alert">The Project could not be loaded. Try again shortly.</p>
      );
  } else {
    body = (
      <>
        <ProjectHeader key={project.data.id} project={project.data} organisationId={organisationId} isOwner={isOwner} />
        <nav aria-label="Project" className="flex flex-wrap gap-2 border-b border-line pb-2">
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
      <Link to="/organisations/$organisationId/projects" params={{ organisationId }} className="text-sm text-muted underline">
        All Projects
      </Link>
      {body}
    </section>
  );
}
