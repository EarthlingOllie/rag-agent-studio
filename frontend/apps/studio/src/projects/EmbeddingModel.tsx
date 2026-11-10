import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { field } from "../design";
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
import { BUTTON } from "./ProjectsPage";

export const RE_EMBEDS =
  "Changing it re-embeds every Document in the background; the current model keeps serving until that finishes.";

interface Active {
  modelId: string;
  credentialId: string | null;
}

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

  if (choices.isPending)
    return <p role="status">Loading the Embedding Models…</p>;
  if (choices.isError)
    return (
      <p role="alert">
        The Embedding Models could not be loaded. Try again shortly.
      </p>
    );

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const select = event.currentTarget.elements.namedItem(
      "embedding-model",
    ) as HTMLSelectElement;
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
    <form
      aria-label="Choose the Embedding Model"
      onSubmit={onSubmit}
      className="max-w-md space-y-3"
    >
      <FormError message={embeddingFailure(save.error)} />
      <label htmlFor="embedding-model" className="block text-sm font-medium">
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
      <p className="text-sm text-muted">
        Provider models come from the Organisation's Provider Credentials that
        can embed. The built-in model needs none.
      </p>
      <div className="flex gap-2">
        <button type="submit" disabled={save.isPending} className={BUTTON}>
          {save.isPending ? "Saving…" : "Use this model"}
        </button>
        <button type="button" className={BUTTON} onClick={onDone}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** A running re-embed's progress, or why the last one failed. */
function ReEmbed({ state }: { state: EmbeddingModelState }) {
  const job = state.re_embed;
  if (job?.status === "running") {
    return (
      <div role="status" className="space-y-1">
        <p>
          Re-embedding with{" "}
          <span className="font-medium text-ink">{job.model_id}</span>:{" "}
          {job.embedded_chunks} of {job.total_chunks} Chunks. Retrieval uses{" "}
          {job.from_model_id} until it finishes.
        </p>
        <progress
          aria-label="Re-embedding progress"
          className="w-full max-w-md"
          max={Math.max(job.total_chunks, 1)}
          value={job.embedded_chunks}
        />
      </div>
    );
  }
  if (job?.status === "failed") {
    return (
      <p role="alert" className="text-danger">
        Re-embedding with {job.model_id} failed. {job.error_message}
      </p>
    );
  }
  return null;
}

/** The Project's Embedding Model, choosing another, and the re-embed a change starts when the Project has Documents. */
export function EmbeddingModelSetting({
  project,
  organisationId,
}: {
  project: Project;
  organisationId: string;
}) {
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
    <section
      aria-labelledby="embedding-model-heading"
      className="space-y-2 text-sm"
    >
      <h2 id="embedding-model-heading" className="font-medium">
        Embedding Model
      </h2>
      <p className="text-muted">
        Documents are embedded with{" "}
        <span className="font-medium text-ink">{active.modelId}</span>.{" "}
        {project.document_count === 0 || running ? "" : RE_EMBEDS}
      </p>
      {state.data && <ReEmbed state={state.data} />}
      {choosing ? (
        <ChooseModel
          project={project}
          organisationId={organisationId}
          active={active}
          onDone={() => {
            setChoosing(false);
          }}
        />
      ) : (
        <button
          type="button"
          className={BUTTON}
          onClick={() => {
            setChoosing(true);
          }}
        >
          Change Embedding Model
        </button>
      )}
    </section>
  );
}
