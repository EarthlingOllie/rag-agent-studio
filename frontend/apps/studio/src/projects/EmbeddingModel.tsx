import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { button, Dialog, field, Meter, Notice, surface, text } from "../design";
import {
  choiceLabel,
  choiceValue,
  embeddingFailure,
  type EmbeddingModelState,
  useEmbeddingChoices,
  useEmbeddingState,
  useSetEmbeddingModel,
} from "./embedding";
import type { Project } from "./projects";

export const RE_EMBEDS =
  "Changing it re-embeds every Document in the background; the current model keeps serving until that finishes.";

interface Active {
  modelId: string;
  credentialId: string | null;
}

/** The dialog's buttons, Cancel then the primary, laid out as `Dialog`'s footer is. */
const FOOTER = "flex flex-wrap justify-end gap-2 pt-2";

const MODEL = "font-mono text-[13px] text-ink";

function ChooseModel({
  project,
  organisationId,
  active,
  onDone,
}: {
  project: Project;
  organisationId: string;
  active: Active;
  onDone: () => void;
}) {
  const choices = useEmbeddingChoices(organisationId);
  const save = useSetEmbeddingModel(organisationId, project.id);
  const cancel = (
    <button type="button" className={button.secondary} onClick={onDone}>
      Cancel
    </button>
  );

  if (choices.isPending)
    return (
      <>
        <p role="status" className={text.muted}>
          Loading the Embedding Models…
        </p>
        <div className={FOOTER}>{cancel}</div>
      </>
    );
  if (choices.isError)
    return (
      <>
        <Notice tone="error">The Embedding Models could not be loaded. Try again shortly.</Notice>
        <div className={FOOTER}>{cancel}</div>
      </>
    );

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const select = event.currentTarget.elements.namedItem("embedding-model") as HTMLSelectElement;
    const [modelId, credentialId] = select.value.split("|") as [string, string];
    save.mutate(
      {
        model_id: modelId,
        credential_id: credentialId === "" ? null : credentialId,
      },
      { onSuccess: onDone },
    );
  }

  return (
    <form aria-label="Choose the Embedding Model" onSubmit={onSubmit} className="flex flex-col gap-4">
      <FormError message={embeddingFailure(save.error)} />
      <label htmlFor="embedding-model" className={field.label}>
        Embedding Model
        <select
          id="embedding-model"
          name="embedding-model"
          className={field.select}
          defaultValue={choiceValue(active.modelId, active.credentialId)}
        >
          {choices.data.map((choice) => (
            <option
              key={choiceValue(choice.model_id, choice.credential_id)}
              value={choiceValue(choice.model_id, choice.credential_id)}
            >
              {choiceLabel(choice)}
            </option>
          ))}
        </select>
      </label>
      {project.document_count === 0 ? (
        <Notice tone="info">This Project has no Documents yet, so the new model is used at once.</Notice>
      ) : (
        <Notice tone="warning">
          Every Document in this Project is re-embedded with the new model in the background. The current model
          keeps serving until that finishes.
        </Notice>
      )}
      <div className={FOOTER}>
        {cancel}
        <button type="submit" disabled={save.isPending} className={button.primary}>
          {save.isPending ? "Saving…" : "Use this model"}
        </button>
      </div>
    </form>
  );
}

/** A running re-embed's progress and the model that keeps serving, or why the last one failed. */
function ReEmbed({ state }: { state: EmbeddingModelState }) {
  const job = state.re_embed;
  if (job?.status === "running") {
    return (
      <div role="status" className="flex flex-col gap-2 text-sm text-ink-2">
        <p>
          Re-embedding with <span className={MODEL}>{job.model_id}</span>: {job.embedded_chunks} of{" "}
          {job.total_chunks} Chunks. Retrieval uses <span className={MODEL}>{job.from_model_id}</span> until it
          finishes.
        </p>
        <Meter
          label="Re-embedding progress"
          value={job.embedded_chunks}
          max={Math.max(job.total_chunks, 1)}
          unit="Chunks"
          progress
        />
      </div>
    );
  }
  if (job?.status === "failed") {
    return (
      <Notice tone="error">
        Re-embedding with {job.model_id} failed. {job.error_message}
      </Notice>
    );
  }
  return null;
}

/**
 * The Project's Embedding Model card: the model in mono with Change, which opens a dialog to choose
 * another, and the re-embed a change starts when the Project has Documents.
 */
export function EmbeddingModelSetting({ project, organisationId }: { project: Project; organisationId: string }) {
  const [choosing, setChoosing] = useState(false);
  const state = useEmbeddingState(organisationId, project.id);
  const active: Active = state.data
    ? { modelId: state.data.model_id, credentialId: state.data.credential_id }
    : {
        modelId: project.embedding_model_id,
        credentialId: project.embedding_credential_id,
      };
  const running = state.data?.re_embed?.status === "running";
  return (
    <section aria-labelledby="embedding-model-heading" className={`${surface.panel} flex flex-col gap-3`}>
      <h3 id="embedding-model-heading" className={text.subheading}>
        Embedding Model
      </h3>
      <p className={text.muted}>The model that turns each Chunk into a vector for retrieval.</p>
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-sunken px-3.5 py-2.5">
        <p className="min-w-0 flex-1 text-sm text-ink-2">
          Documents are embedded with <span className={MODEL}>{active.modelId}</span>.{" "}
          {project.document_count === 0 || running ? "" : <span className="text-muted">{RE_EMBEDS}</span>}
        </p>
        <button
          type="button"
          aria-label="Change Embedding Model"
          className={button.secondary}
          onClick={() => {
            setChoosing(true);
          }}
        >
          Change
        </button>
      </div>
      {state.data && <ReEmbed state={state.data} />}
      <Dialog
        open={choosing}
        title="Change the Embedding Model"
        description="Embedding Models come from the Organisation's Provider Credentials that can embed. The built-in model needs none."
        onClose={() => {
          setChoosing(false);
        }}
      >
        <ChooseModel
          project={project}
          organisationId={organisationId}
          active={active}
          onDone={() => {
            setChoosing(false);
          }}
        />
      </Dialog>
    </section>
  );
}
