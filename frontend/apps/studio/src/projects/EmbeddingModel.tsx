import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import {
  choiceLabel,
  choiceValue,
  embeddingFailure,
  useEmbeddingChoices,
  useSetEmbeddingModel,
} from "./embedding";
import type { Project } from "./projects";
import { BUTTON, INPUT } from "./ProjectsPage";

export const HAS_DOCUMENTS =
  "It can't be changed while the Project has Documents.";

function ChooseModel({
  project,
  organisationId,
  onDone,
}: {
  project: Project;
  organisationId: string;
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
          className={INPUT}
          defaultValue={choiceValue(
            project.embedding_model_id,
            project.embedding_credential_id,
          )}
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
      <p className="text-sm text-slate-700">
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

/** The Project's Embedding Model, and choosing another while the Project has no Documents. */
export function EmbeddingModelSetting({
  project,
  organisationId,
}: {
  project: Project;
  organisationId: string;
}) {
  const [choosing, setChoosing] = useState(false);
  const empty = project.document_count === 0;
  return (
    <section
      aria-labelledby="embedding-model-heading"
      className="space-y-2 text-sm"
    >
      <h2 id="embedding-model-heading" className="font-medium">
        Embedding Model
      </h2>
      <p className="text-slate-700">
        Documents are embedded with{" "}
        <span className="font-medium text-slate-900">
          {project.embedding_model_id}
        </span>
        . {empty ? "" : HAS_DOCUMENTS}
      </p>
      {choosing ? (
        <ChooseModel
          project={project}
          organisationId={organisationId}
          onDone={() => {
            setChoosing(false);
          }}
        />
      ) : (
        empty && (
          <button
            type="button"
            className={BUTTON}
            onClick={() => {
              setChoosing(true);
            }}
          >
            Change Embedding Model
          </button>
        )
      )}
    </section>
  );
}
