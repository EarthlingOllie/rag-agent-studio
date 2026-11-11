import { MarkdownEditor } from "@studio/ui";
import { useParams } from "@tanstack/react-router";
import { type ReactNode, type SubmitEvent, useRef, useState } from "react";

import { button, EmptyState, Notice, notice, Skeleton, surface, text } from "../design";
import { AgentsBehind, BulkRevertOffer, RolloutDialog } from "./BulkRollout";
import {
  type DraftInstructions,
  type InstructionsReverted,
  type InstructionsVersion,
  instructionsFailure,
  StaleInstructionsError,
  useInstructions,
  useSaveInstructions,
  useStoreInstructions,
} from "./instructions";
import { InstructionsVersions, PublishInstructionsForm } from "./InstructionsVersions";
import { useProject } from "./projects";
import { useOrganisationRole } from "./ProjectsPage";

/** A panel on the Instructions page, under its own heading. */
function Panel({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className={`flex flex-col gap-4 ${surface.panel}`}>
      <h3 id={id} className={text.subheading}>
        {title}
      </h3>
      {children}
    </section>
  );
}

function InstructionsForm({
  organisationId,
  projectId,
  draft,
  archived,
  onReplaced,
  onPublished,
}: {
  organisationId: string;
  projectId: string;
  draft: DraftInstructions;
  archived: boolean;
  onReplaced: () => void;
  onPublished: (version: InstructionsVersion) => void;
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

  const failure = save.error instanceof StaleInstructionsError ? undefined : instructionsFailure(save.error);
  return (
    <>
      <Panel id="instructions-draft-heading" title="Draft">
        <form aria-label="Project Instructions" onSubmit={onSubmit} className="flex flex-col gap-3">
          {failure !== undefined && <Notice tone="error">{failure}</Notice>}
          {conflict && (
            <div role="alert" className={`flex flex-col gap-2 ${notice.warning}`}>
              <p>Someone else saved these Instructions while you were editing. Yours aren&apos;t saved. Load theirs, or save yours over them.</p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className={button.secondary}
                  onClick={() => {
                    store(conflict);
                    onReplaced();
                  }}
                >
                  Load their changes
                </button>
                <button
                  type="button"
                  className={button.secondary}
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
            <p className={notice.info}>This Project is archived. Restore the Project to edit its Instructions.</p>
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <button type="submit" disabled={save.isPending} className={button.secondary}>
                {save.isPending ? "Saving…" : "Save Instructions"}
              </button>
              {save.isSuccess && (
                <span role="status" className={text.muted}>
                  Instructions saved
                </span>
              )}
            </div>
          )}
        </form>
      </Panel>
      {!archived && (
        <Panel id="instructions-publish-heading" title="Publish">
          <PublishInstructionsForm
            organisationId={organisationId}
            projectId={projectId}
            markdown={() => current.current}
            baseRevision={() => base.current}
            onSaved={(revision) => {
              base.current = revision;
            }}
            onStale={setConflict}
            onPublished={onPublished}
          />
        </Panel>
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
  // After publishing, the rollout dialog; after reverting, the offer to bulk-revert Agents.
  const [dialog, setDialog] = useState<
    { kind: "rollout"; version: { id: string; number: number } } | { kind: "revert"; reverted: InstructionsReverted } | null
  >(null);
  const close = () => {
    setDialog(null);
  };
  // Moves on when someone else's Draft is loaded, so the editor starts again from it.
  const [generation, setGeneration] = useState(0);

  let body;
  if (instructions.isError) {
    body = <EmptyState tone="error" title="The Instructions could not be loaded" description="Try again shortly." />;
  } else if (instructions.isPending || !project.data) {
    body = <Skeleton label="Loading the Instructions" lines={6} />;
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
        onPublished={(version) => {
          setDialog({ kind: "rollout", version });
        }}
      />
    );
  }

  return (
    <section aria-labelledby="tab-heading" className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h2 id="tab-heading" className={text.heading}>
          Instructions
        </h2>
        <p className={text.muted}>
          Project Instructions are the shared rules every Agent in this Project follows. They come before each Agent&apos;s system prompt.
        </p>
      </div>
      {body}
      {dialog?.kind === "rollout" && (
        <RolloutDialog organisationId={organisationId} projectId={projectId} version={dialog.version} onClose={close} />
      )}
      {dialog?.kind === "revert" && (
        <BulkRevertOffer
          organisationId={organisationId}
          projectId={projectId}
          reverted={dialog.reverted.reverted_from}
          candidates={dialog.reverted.bulk_revert_candidates}
          onClose={close}
        />
      )}
      {project.data && (
        <>
          <Panel id="instructions-agents-heading" title="Agents">
            <AgentsBehind
              organisationId={organisationId}
              projectId={projectId}
              archived={project.data.archived_at !== null}
              onRollOut={(version) => {
                setDialog({ kind: "rollout", version });
              }}
            />
          </Panel>
          <Panel id="instructions-versions-heading" title="Versions">
            <InstructionsVersions
              organisationId={organisationId}
              projectId={projectId}
              archived={project.data.archived_at !== null}
              onReverted={(reverted) => {
                setDialog(reverted.bulk_revert_candidates.length > 0 ? { kind: "revert", reverted } : null);
              }}
            />
          </Panel>
        </>
      )}
    </section>
  );
}
