import { MarkdownEditor } from "@studio/ui";
import { useParams } from "@tanstack/react-router";
import { type SubmitEvent, useRef } from "react";

import { FormError } from "../auth/AuthLayout";
import { instructionsFailure, useInstructions, useSaveInstructions } from "./instructions";
import { InstructionsVersions, PublishInstructionsForm } from "./InstructionsVersions";
import { useProject } from "./projects";
import { BUTTON, useOrganisationRole } from "./ProjectsPage";

function InstructionsForm({
  organisationId,
  projectId,
  markdown,
  archived,
}: {
  organisationId: string;
  projectId: string;
  markdown: string;
  archived: boolean;
}) {
  const save = useSaveInstructions(organisationId, projectId);
  // Exactly what was loaded until it is edited, then exactly what the editor wrote.
  const current = useRef(markdown);

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate(current.current);
  }

  return (
    <>
      <form aria-label="Project Instructions" onSubmit={onSubmit} className="space-y-3">
        <FormError message={instructionsFailure(save.error)} />
        <MarkdownEditor
          label="Project Instructions"
          defaultValue={markdown}
          maxLength={20000}
          disabled={archived}
          onChange={(changed) => {
            current.current = changed;
            save.reset();
          }}
        />
        {archived ? (
          <p className="text-sm text-slate-700">This Project is archived. Restore the Project to edit its Instructions.</p>
        ) : (
          <div className="flex items-center gap-3">
            <button type="submit" disabled={save.isPending} className={BUTTON}>
              {save.isPending ? "Saving…" : "Save Instructions"}
            </button>
            {save.isSuccess && (
              <span role="status" className="text-sm text-slate-700">
                Instructions saved
              </span>
            )}
          </div>
        )}
      </form>
      {!archived && (
        <PublishInstructionsForm organisationId={organisationId} projectId={projectId} markdown={() => current.current} />
      )}
    </>
  );
}

/** The Project Instructions: one markdown Draft that every Agent in the Project follows. */
export function InstructionsTab() {
  const { organisationId } = useOrganisationRole();
  const { projectId } = useParams({ from: "/signed-in/organisations/$organisationId/projects/$projectId" });
  const project = useProject(organisationId, projectId);
  const instructions = useInstructions(organisationId, projectId);

  let body;
  if (instructions.isError) {
    body = <p role="alert">The Instructions could not be loaded. Try again shortly.</p>;
  } else if (instructions.isPending || !project.data) {
    body = <p role="status">Loading the Instructions…</p>;
  } else {
    body = (
      <InstructionsForm
        organisationId={organisationId}
        projectId={projectId}
        markdown={instructions.data}
        archived={project.data.archived_at !== null}
      />
    );
  }

  return (
    <section aria-labelledby="tab-heading" className="space-y-3">
      <h2 id="tab-heading" className="text-lg font-semibold">
        Instructions
      </h2>
      <p className="text-slate-700">
        Project Instructions are the shared rules every Agent in this Project follows. They come before each Agent's system prompt.
      </p>
      {body}
      <h3 className="pt-4 text-base font-semibold">Versions</h3>
      {project.data && (
        <InstructionsVersions organisationId={organisationId} projectId={projectId} archived={project.data.archived_at !== null} />
      )}
    </section>
  );
}
