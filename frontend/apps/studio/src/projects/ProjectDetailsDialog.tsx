import { useNavigate } from "@tanstack/react-router";
import { type SubmitEvent, useId } from "react";

import { FormError, formValues } from "../auth/AuthLayout";
import { button, Dialog, field, useToast } from "../design";
import { type Project, projectFailure, useCreateProject, useUpdateProject } from "./projects";

const MODES = {
  create: { title: "New Project", action: "Create Project", pending: "Creating…" },
  edit: { title: "Project details", action: "Save", pending: "Saving…" },
} as const;

/** Name (required) and Description, filled in with the Project's current values when editing. */
function ProjectFields({ project }: { project: Project | undefined }) {
  const id = useId();
  return (
    <>
      <div>
        <label htmlFor={`${id}-name`} className={field.label}>
          Name
        </label>
        <input
          id={`${id}-name`}
          name="name"
          required
          maxLength={200}
          defaultValue={project?.name}
          className={field.input}
        />
      </div>
      <div>
        <label htmlFor={`${id}-description`} className={field.label}>
          Description
        </label>
        <textarea
          id={`${id}-description`}
          name="description"
          rows={3}
          maxLength={2000}
          defaultValue={project?.description}
          className={field.textarea}
        />
      </div>
    </>
  );
}

/**
 * The Project details dialog: a Project's name and description, for a new Project or an existing
 * one. A refusal shows inside it and keeps what was typed; Cancel and Escape close it unsaved.
 */
function ProjectDetailsDialog({
  mode,
  project,
  pending,
  error,
  onSubmit,
  onClose,
}: {
  mode: keyof typeof MODES;
  project?: Project | undefined;
  pending: boolean;
  error: Error | null;
  onSubmit: (details: Record<"name" | "description", string>) => void;
  onClose: () => void;
}) {
  const words = MODES[mode];

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit(formValues(event.currentTarget, ["name", "description"]));
  }

  return (
    <Dialog open title={words.title} onClose={onClose} closeButton={false}>
      <form aria-label={words.title} onSubmit={submit} className="space-y-4">
        <FormError message={projectFailure(error)} />
        <ProjectFields project={project} />
        <div className="flex flex-wrap justify-end gap-2 pt-2">
          <button type="button" className={button.secondary} onClick={onClose}>
            Cancel
          </button>
          <button type="submit" disabled={pending} className={button.primary}>
            {pending ? words.pending : words.action}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

/** New Project: creates the Project and opens it. */
export function NewProjectDialog({ organisationId, onClose }: { organisationId: string; onClose: () => void }) {
  const create = useCreateProject(organisationId);
  const navigate = useNavigate();
  return (
    <ProjectDetailsDialog
      mode="create"
      pending={create.isPending}
      error={create.error}
      onClose={onClose}
      onSubmit={(details) => {
        create.mutate(details, {
          onSuccess: (created) => {
            void navigate({
              to: "/organisations/$organisationId/projects/$projectId",
              params: { organisationId, projectId: created.id },
            });
          },
        });
      }}
    />
  );
}

/** Edit details: saves the Project's name and description, closes, and confirms with a toast. */
export function EditProjectDialog({
  project,
  organisationId,
  onClose,
}: {
  project: Project;
  organisationId: string;
  onClose: () => void;
}) {
  const update = useUpdateProject(organisationId, project.id);
  const toast = useToast();
  return (
    <ProjectDetailsDialog
      mode="edit"
      project={project}
      pending={update.isPending}
      error={update.error}
      onClose={onClose}
      onSubmit={(details) => {
        update.mutate(details, {
          onSuccess: () => {
            onClose();
            toast.show("Project details saved");
          },
        });
      }}
    />
  );
}
