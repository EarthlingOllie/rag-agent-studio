import { MarkdownEditor } from "@studio/ui";
import { useParams } from "@tanstack/react-router";
import { type SubmitEvent, useRef, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import {
  type DraftInstructions,
  instructionsFailure,
  StaleInstructionsError,
  useInstructions,
  useSaveInstructions,
  useStoreInstructions,
} from "./instructions";
import { InstructionsVersions, PublishInstructionsForm } from "./InstructionsVersions";
import { useProject } from "./projects";
import { BUTTON, useOrganisationRole } from "./ProjectsPage";

const CONFLICT_BUTTON = "rounded border border-slate-400 bg-white px-3 py-1 text-sm text-slate-900 hover:bg-slate-100";

function InstructionsForm({
  organisationId,
  projectId,
  draft,
  archived,
  onReplaced,
}: {
  organisationId: string;
  projectId: string;
  draft: DraftInstructions;
  archived: boolean;
  onReplaced: () => void;
}) {
  const save = useSaveInstructions(organisationId, projectId);
  const store = useStoreInstructions(organisationId, projectId);
  // Exactly what was loaded until it is edited, then exactly what the editor wrote.
  const current = useRef(draft.markdown);
  // The Draft revision these edits are made on: the last one saved or loaded here.
  const base = useRef(draft.revision);
  // Someone else's Draft, when a save was refused because they had saved since.
  const [conflict, setConflict] = useState<DraftInstructions | null>(null);

  function saveOver(baseRevision: number) {
    setConflict(null);
    save.mutate(
      { markdown: current.current, baseRevision },
      {
        onSuccess: (saved) => {
          base.current = saved.revision;
        },
        onError: (error) => {
          if (error instanceof StaleInstructionsError) setConflict(error.latest);
        },
      },
    );
  }

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    saveOver(base.current);
  }

  return (
    <>
      <form aria-label="Project Instructions" onSubmit={onSubmit} className="space-y-3">
        <FormError message={save.error instanceof StaleInstructionsError ? undefined : instructionsFailure(save.error)} />
        {conflict && (
          <div role="alert" className="space-y-2 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
            <p>Someone else saved these Instructions while you were editing. Yours aren&apos;t saved. Load theirs, or save yours over them.</p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className={CONFLICT_BUTTON}
                onClick={() => {
                  store(conflict);
                  onReplaced();
                }}
              >
                Load their changes
              </button>
              <button
                type="button"
                className={CONFLICT_BUTTON}
                onClick={() => {
                  saveOver(conflict.revision);
                }}
              >
                Save mine over theirs
              </button>
            </div>
          </div>
        )}
        <MarkdownEditor
          label="Project Instructions"
          defaultValue={draft.markdown}
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
        <PublishInstructionsForm
          organisationId={organisationId}
          projectId={projectId}
          markdown={() => current.current}
          baseRevision={() => base.current}
          onStale={setConflict}
        />
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
  // Moves on when someone else's Draft is loaded, so the editor starts again from it.
  const [generation, setGeneration] = useState(0);

  let body;
  if (instructions.isError) {
    body = <p role="alert">The Instructions could not be loaded. Try again shortly.</p>;
  } else if (instructions.isPending || !project.data) {
    body = <p role="status">Loading the Instructions…</p>;
  } else {
    body = (
      <InstructionsForm
        key={generation}
        organisationId={organisationId}
        projectId={projectId}
        draft={instructions.data}
        archived={project.data.archived_at !== null}
        onReplaced={() => {
          setGeneration((count) => count + 1);
        }}
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
