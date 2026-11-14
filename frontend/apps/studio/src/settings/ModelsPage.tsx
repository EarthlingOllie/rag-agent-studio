import { Link } from "@tanstack/react-router";
import { type SubmitEvent, useEffect, useId, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { Segmented, button, field, surface, text, useToast } from "../design";
import { type Credential, credentialFailure, type ProviderId, useCredentials } from "./credentials";
import {
  type EvaluationSettings,
  REPEATS,
  useEvaluationSettings,
  useSetEvaluationModel,
  useSetEvaluationRepeats,
} from "./evaluationSettings";
import { ChatModelOptions, withoutTools } from "./ModelOptions";
import { type DefaultModel, useChatModels, useDefaultModel, useSetDefaultModel } from "./models";
import { PriceTable } from "./PriceTable";

const PROVIDER_NAMES: Record<ProviderId, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  bedrock: "Amazon Bedrock",
  voyage: "Voyage AI",
  // The seeded demo provider: canned answers from the Knowledge Base, never a real model.
  demo: "Demo: canned answers, not a real model",
};

const label = (name: string, provider: ProviderId) => `${name} (${PROVIDER_NAMES[provider]})`;

function Current({ organisationId }: { organisationId: string }) {
  const current = useDefaultModel(organisationId);
  if (current.isError) return <p role="alert" className={text.muted}>The Default Model could not be loaded. Try again shortly.</p>;
  if (current.isPending) return <p className={text.muted}>Loading…</p>;
  if (current.data === null) return <p className={text.muted}>No Default Model yet. New Agents need one to answer.</p>;
  const { model_name: modelName, credential_name: credentialName, provider, supports_tools: tools } = current.data;
  return (
    <div className="space-y-1">
      <p className="text-sm text-ink">
        <span className="font-medium text-ink-2">Current: </span>
        <span>{`${modelName}, using ${label(credentialName, provider)}`}</span>
      </p>
      {!tools && (
        <p className={text.muted}>It can't use tools, so Agentic Agents without their own model answer as Automatic.</p>
      )}
    </div>
  );
}

function Picker({
  organisationId,
  chat,
  current,
}: {
  organisationId: string;
  chat: [Credential, ...Credential[]];
  current: DefaultModel | null;
}) {
  const save = useSetDefaultModel(organisationId);
  const start = chat.find((credential) => credential.id === current?.credential_id) ?? chat[0];
  const [credentialId, setCredentialId] = useState(start.id);
  const [wanted, setWanted] = useState(current?.model ?? "");
  const toast = useToast();
  const models = useChatModels(organisationId, credentialId);
  const options = models.data ?? [];
  // The wanted model if this credential offers it, otherwise its first chat model.
  const model = options.some((option) => option.id === wanted) ? wanted : (options[0]?.id ?? "");
  const plain = withoutTools(options, model);
  return (
    <form
      aria-label="Choose the Default Model"
      className="flex flex-col gap-4"
      onSubmit={(event: SubmitEvent<HTMLFormElement>) => {
        event.preventDefault();
        save.mutate(
          { credential_id: credentialId, model },
          {
            onSuccess: (next) => {
              toast.show(`The Default Model is now ${next.model_name}.`);
            },
          },
        );
      }}
    >
      <FormError message={credentialFailure(save.error)} />
      <label className={field.label}>
        Credential
        <select
          className={field.select}
          value={credentialId}
          onChange={(event) => {
            setCredentialId(event.target.value);
          }}
        >
          {chat.map((credential) => (
            <option key={credential.id} value={credential.id}>
              {label(credential.name, credential.provider)}
            </option>
          ))}
        </select>
      </label>
      {models.isError ? (
        <p role="alert" className={text.muted}>The models could not be loaded. Try again shortly.</p>
      ) : (
        <label className={field.label}>
          Model
          <select
            className={field.select}
            value={model}
            onChange={(event) => {
              setWanted(event.target.value);
            }}
          >
            <ChatModelOptions models={options} />
          </select>
        </label>
      )}
      {plain && (
        <p className={text.muted}>
          {`${plain.name} can't use tools: Agentic Agents that use the Default Model will answer as Automatic.`}
        </p>
      )}
      <button type="submit" className={`${button.primary} self-start`} disabled={save.isPending || model === ""}>
        {save.isPending ? "Saving…" : "Save Default Model"}
      </button>
    </form>
  );
}

function OwnerControls({ organisationId }: { organisationId: string }) {
  const credentials = useCredentials(organisationId);
  const current = useDefaultModel(organisationId);
  if (credentials.isError) return <p role="alert" className={text.muted}>The credentials could not be loaded. Try again shortly.</p>;
  if (!credentials.data || current.data === undefined) return null;
  const chat = credentials.data
    .filter((credential) => credential.capabilities.includes("chat"))
    .sort((a, b) => a.name.localeCompare(b.name));
  const [first, ...rest] = chat;
  if (first === undefined) {
    return (
      <p className={text.muted}>
        No credential can be used for chat yet.{" "}
        <Link to="/organisations/$organisationId/settings/credentials" params={{ organisationId }} className={text.link}>
          Add one in Credentials
        </Link>
        .
      </p>
    );
  }
  return <Picker organisationId={organisationId} chat={[first, ...rest]} current={current.data} />;
}

/** The chat-capable credentials, by name. */
function chatCredentials(credentials: Credential[]): Credential[] {
  return credentials.filter((credential) => credential.capabilities.includes("chat")).sort((a, b) => a.name.localeCompare(b.name));
}

/** The Evaluation Model picker: "Use the Default Model", or a chat-capable credential and one of its chat models. */
function EvaluationModelPicker({
  organisationId,
  chat,
  current,
}: {
  organisationId: string;
  chat: Credential[];
  current: EvaluationSettings["evaluation_model"];
}) {
  const save = useSetEvaluationModel(organisationId);
  const toast = useToast();
  // "" judges with the Default Model.
  const [credentialId, setCredentialId] = useState(current?.credential_id ?? "");
  const [wanted, setWanted] = useState(current?.model ?? "");
  return (
    <form
      aria-label="Choose the Evaluation Model"
      className="flex flex-col gap-4"
      onSubmit={(event: SubmitEvent<HTMLFormElement>) => {
        event.preventDefault();
        const body = credentialId === "" ? { credential_id: null, model: null } : { credential_id: credentialId, model: wanted };
        save.mutate(body, {
          onSuccess: (next) => {
            toast.show(
              next.evaluation_model === null
                ? "Evaluation Runs are now judged by the Default Model."
                : `Evaluation Runs are now judged by ${next.evaluation_model.model_name}.`,
            );
          },
        });
      }}
    >
      <FormError message={credentialFailure(save.error)} />
      <label className={field.label}>
        Judge with
        <select
          className={field.select}
          value={credentialId}
          onChange={(event) => {
            setCredentialId(event.target.value);
          }}
        >
          <option value="">Use the Default Model</option>
          {chat.map((credential) => (
            <option key={credential.id} value={credential.id}>
              {label(credential.name, credential.provider)}
            </option>
          ))}
        </select>
      </label>
      {credentialId !== "" && (
        <EvaluationModelChoice organisationId={organisationId} credentialId={credentialId} wanted={wanted} onChange={setWanted} />
      )}
      <button
        type="submit"
        className={`${button.primary} self-start`}
        disabled={save.isPending || (credentialId !== "" && wanted === "")}
      >
        {save.isPending ? "Saving…" : "Save Evaluation Model"}
      </button>
    </form>
  );
}

/** The chosen credential's chat models; picks its first while the wanted one isn't offered. */
function EvaluationModelChoice({
  organisationId,
  credentialId,
  wanted,
  onChange,
}: {
  organisationId: string;
  credentialId: string;
  wanted: string;
  onChange: (model: string) => void;
}) {
  const models = useChatModels(organisationId, credentialId);
  const options = models.data ?? [];
  const model = options.some((option) => option.id === wanted) ? wanted : (options[0]?.id ?? "");
  useEffect(() => {
    if (model !== wanted) onChange(model);
  }, [model, wanted, onChange]);
  if (models.isError) return <p role="alert" className={text.muted}>The models could not be loaded. Try again shortly.</p>;
  return (
    <label className={field.label}>
      Model
      <select
        className={field.select}
        value={model}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      >
        <ChatModelOptions models={options} />
      </select>
    </label>
  );
}

function EvaluationRepeats({ organisationId, repeats }: { organisationId: string; repeats: number }) {
  const save = useSetEvaluationRepeats(organisationId);
  const toast = useToast();
  const hintId = useId();
  return (
    <div className="flex flex-col gap-2">
      <span className={field.label}>Evaluation repeats</span>
      <Segmented
        label="Evaluation repeats"
        describedBy={hintId}
        options={REPEATS.map((value) => ({ value: String(value), label: String(value) }))}
        value={String(repeats)}
        onChange={(value) => {
          save.mutate(Number(value) as (typeof REPEATS)[number], {
            onSuccess: (next) => {
              toast.show(`Each side of a Run now answers every case ${String(next.repeats)} times.`);
            },
          });
        }}
      />
      <p id={hintId} className={field.hint}>
        More repeats give steadier results; each one adds to a Run's cost.
      </p>
      <FormError message={credentialFailure(save.error)} />
    </div>
  );
}

function EvaluationOwnerControls({ organisationId, settings }: { organisationId: string; settings: EvaluationSettings }) {
  const credentials = useCredentials(organisationId);
  return (
    <>
      {credentials.isError && <p role="alert" className={text.muted}>The credentials could not be loaded. Try again shortly.</p>}
      {credentials.data && (
        <EvaluationModelPicker organisationId={organisationId} chat={chatCredentials(credentials.data)} current={settings.evaluation_model} />
      )}
      <EvaluationRepeats organisationId={organisationId} repeats={settings.repeats} />
    </>
  );
}

function EvaluationSection({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  const settings = useEvaluationSettings(organisationId);
  const chosen = settings.data?.evaluation_model;
  return (
    <section aria-labelledby="evaluation-heading" className={`${surface.panel} flex max-w-2xl flex-col gap-4`}>
      <div className="flex flex-col gap-1">
        <h2 id="evaluation-heading" className={text.heading}>
          Evaluation
        </h2>
        <p className={text.muted}>
          The Evaluation Model judges every Evaluation Run in this Organisation, so scores stay comparable across Agents and over time.
        </p>
      </div>
      {settings.isError && <p role="alert" className={text.muted}>The evaluation settings could not be loaded. Try again shortly.</p>}
      {settings.isPending && <p className={text.muted}>Loading…</p>}
      {settings.data && (
        <>
          <div className="space-y-1 text-sm text-ink">
            <p>
              {chosen
                ? `Evaluation Model: ${chosen.model_name}, using ${label(chosen.credential_name, chosen.provider)}`
                : "Evaluation Model: the Default Model"}
            </p>
            <p>{`Each side of a Run answers every case ${String(settings.data.repeats)} times.`}</p>
          </div>
          {isOwner ? (
            <EvaluationOwnerControls organisationId={organisationId} settings={settings.data} />
          ) : (
            <p className={text.muted}>Only Owners can change the Evaluation Model and Evaluation repeats.</p>
          )}
        </>
      )}
    </section>
  );
}

/**
 * Models settings: the Organisation's Default Model, the Evaluation Model and Evaluation repeats,
 * and the price table. Every Member sees them; Owners choose the Default Model and the evaluation
 * settings (confirmed by a toast) and override prices.
 */
export function ModelsPage({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  return (
    <div className="flex flex-col gap-10">
      <DefaultModelSection organisationId={organisationId} isOwner={isOwner} />
      <EvaluationSection organisationId={organisationId} isOwner={isOwner} />
      <PriceTable organisationId={organisationId} isOwner={isOwner} />
    </div>
  );
}

function DefaultModelSection({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  return (
    <section aria-labelledby="default-model-heading" className={`${surface.panel} flex max-w-2xl flex-col gap-4`}>
      <div className="flex flex-col gap-1">
        <h2 id="default-model-heading" className={text.heading}>
          Default Model
        </h2>
        <p className={text.muted}>
          New Agents answer with this model unless they choose their own. Only chat-capable credentials and their chat models can be
          chosen.
        </p>
      </div>
      <Current organisationId={organisationId} />
      {isOwner ? (
        <OwnerControls organisationId={organisationId} />
      ) : (
        <p className={text.muted}>Only Owners can change the Default Model.</p>
      )}
    </section>
  );
}
