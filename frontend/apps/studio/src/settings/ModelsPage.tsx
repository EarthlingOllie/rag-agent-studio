import { Link } from "@tanstack/react-router";
import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { button, field, surface, text, useToast } from "../design";
import { type Credential, credentialFailure, type ProviderId, useCredentials } from "./credentials";
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
  const { model_name: modelName, credential_name: credentialName, provider } = current.data;
  return (
    <p className="text-sm text-ink">
      <span className="font-medium text-ink-2">Current: </span>
      <span>{`${modelName}, using ${label(credentialName, provider)}`}</span>
    </p>
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
            {options.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </select>
        </label>
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

/**
 * Models settings: the Organisation's Default Model and the price table. Every Member sees them;
 * Owners choose the Default Model (confirmed by a toast) and override prices.
 */
export function ModelsPage({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  return (
    <div className="flex flex-col gap-10">
      <DefaultModelSection organisationId={organisationId} isOwner={isOwner} />
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
