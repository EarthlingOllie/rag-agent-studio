import { Outlet, useNavigate, useParams } from "@tanstack/react-router";
import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { button, ConfirmDialog, EmptyState, field, Icon, Menu, type MenuItem, PageHeader, Skeleton } from "../design";
import {
  type Project,
  ProjectRequestError,
  projectFailure,
  useArchiveOrRestore,
  useDeleteProject,
  useProject,
  useUpdateProject,
} from "./projects";
import { ProjectFields, projectDetails, useOrganisationRole } from "./ProjectsPage";

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
        <button type="button" className={button.secondary} onClick={onDone}>
          Cancel
        </button>
        <button type="submit" disabled={update.isPending} className={button.primary}>
          {update.isPending ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}

/** Archive, from the ⋯ menu: asked first, in a destructive confirmation. */
function ArchiveDialog({
  project,
  archive,
  onDone,
}: {
  project: Project;
  archive: ReturnType<typeof useArchiveOrRestore>;
  onDone: () => void;
}) {
  return (
    <ConfirmDialog
      open
      title={`Archive ${project.name}?`}
      confirmLabel={`Yes, archive ${project.name}`}
      destructive
      busy={archive.isPending}
      onConfirm={() => {
        archive.mutate(project.id, { onSettled: onDone });
      }}
      onCancel={onDone}
    >
      {project.name} will be hidden from the Projects list and stop serving. An Owner can restore it.
    </ConfirmDialog>
  );
}

/** Owners only, on an archived Project: deletion is confirmed by typing the Project's name exactly. */
function DeleteDialog({ project, organisationId, onDone }: { project: Project; organisationId: string; onDone: () => void }) {
  const remove = useDeleteProject(organisationId, project.id);
  const navigate = useNavigate();
  const [typed, setTyped] = useState("");
  const title = `Delete ${project.name} permanently`;
  const ready = typed === project.name && !remove.isPending;

  function confirm() {
    remove.mutate(typed, {
      onSuccess: () => {
        void navigate({ to: "/organisations/$organisationId/projects", params: { organisationId }, search: { deleted: project.name } });
      },
    });
  }

  return (
    <ConfirmDialog
      open
      title={title}
      confirmLabel={title}
      destructive
      busy={remove.isPending}
      confirmDisabled={!ready}
      onConfirm={confirm}
      onCancel={onDone}
      body={
        <form
          aria-label={title}
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (ready) confirm();
          }}
        >
          <FormError message={projectFailure(remove.error)} />
          <div>
            <label htmlFor="delete-project-name" className={field.label}>
              Type {project.name} to confirm
            </label>
            <input
              id="delete-project-name"
              autoComplete="off"
              className={field.input}
              value={typed}
              onChange={(event) => {
                setTyped(event.target.value);
              }}
            />
          </div>
        </form>
      }
    >
      Deleting {project.name} removes its Documents, stored files, Agents and Conversations for good. This can&apos;t be undone.
    </ConfirmDialog>
  );
}

function ArchivedNotice({ project, organisationId, isOwner }: { project: Project; organisationId: string; isOwner: boolean }) {
  const restore = useArchiveOrRestore(organisationId, "restore");
  return (
    <div role="status" className="space-y-2 rounded-2xl border border-flag bg-flag-soft p-4 text-sm text-flag">
      <p>
        This Project is archived. It is hidden from the Projects list and doesn't serve.{" "}
        {isOwner ? "Restore it to use it again." : "Only Owners can restore it."}
      </p>
      <FormError message={projectFailure(restore.error)} />
      {isOwner && (
        <button
          type="button"
          className={button.secondary}
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

/**
 * The page header: the Project's name and description, Edit details, and a ⋯ menu for the rare
 * actions: Archive, or, on an archived Project, permanent deletion (Owners only).
 */
function ProjectHeader({ project, organisationId, isOwner }: { project: Project; organisationId: string; isOwner: boolean }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState<"archive" | "delete" | null>(null);
  const archive = useArchiveOrRestore(organisationId, "archive");
  const archived = project.archived_at !== null;
  const done = () => {
    setConfirming(null);
  };

  const actions: MenuItem[] = archived
    ? isOwner
      ? [{ label: "Delete permanently", danger: true, onSelect: () => { setConfirming("delete"); } }]
      : []
    : [
        {
          label: "Archive",
          onSelect: () => {
            archive.reset();
            setConfirming("archive");
          },
        },
      ];

  return (
    <div className="space-y-4">
      <PageHeader
        title={project.name}
        description={project.description === "" ? undefined : project.description}
        actions={
          <>
            {!archived && !editing && (
              <button
                type="button"
                className={button.secondary}
                onClick={() => {
                  setEditing(true);
                }}
              >
                Edit details
              </button>
            )}
            {actions.length > 0 && (
              <Menu
                label={<Icon name="more" />}
                triggerLabel="More Project actions"
                menuLabel="Project actions"
                align="end"
                triggerClassName={button.icon}
                items={actions}
              />
            )}
          </>
        }
      />
      {archived ? (
        <ArchivedNotice project={project} organisationId={organisationId} isOwner={isOwner} />
      ) : (
        <>
          <FormError message={confirming === null ? projectFailure(archive.error) : undefined} />
          {editing && (
            <EditDetails
              project={project}
              organisationId={organisationId}
              onDone={() => {
                setEditing(false);
              }}
            />
          )}
        </>
      )}
      {confirming === "archive" && <ArchiveDialog project={project} archive={archive} onDone={done} />}
      {confirming === "delete" && <DeleteDialog project={project} organisationId={organisationId} onDone={done} />}
    </div>
  );
}

/**
 * One Project: its page header, then the section the breadcrumb's section switcher has open.
 * The Project and section switchers in the top bar replace a tab row and an All Projects link.
 */
export function ProjectLayout() {
  const { organisationId, isOwner } = useOrganisationRole();
  const { projectId } = useProjectParams();
  const project = useProject(organisationId, projectId);

  if (project.isPending) return <Skeleton label="Loading the Project" />;
  if (project.isError) {
    return project.error instanceof ProjectRequestError && project.error.status === 404 ? (
      <EmptyState level={1} icon="projects" title="Project not found" description="It doesn't exist in this Organisation." />
    ) : (
      <EmptyState tone="error" title="The Project could not be loaded" description="Try again shortly." />
    );
  }
  return (
    <div className="space-y-6">
      <ProjectHeader key={project.data.id} project={project.data} organisationId={organisationId} isOwner={isOwner} />
      <Outlet />
    </div>
  );
}
