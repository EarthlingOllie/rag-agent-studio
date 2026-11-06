import { Link } from "@tanstack/react-router";
import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { type Credential, credentialFailure, type ProviderId, useCredentials } from "./credentials";
import { type DefaultModel, useChatModels, useDefaultModel, useSetDefaultModel } from "./models";
import { PriceTable } from "./PriceTable";

const INPUT = "mt-1 block w-full rounded border border-slate-400 bg-white px-3 py-2 focus:outline-2 focus:outline-slate-900";
const PRIMARY = "rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:bg-slate-600";

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
  if (current.isError) return <p role="alert">The Default Model could not be loaded. Try again shortly.</p>;
  if (current.isPending) return <p className="text-sm text-slate-700">Loading…</p>;
  if (current.data === null) return <p className="text-sm text-slate-700">No Default Model yet. New Agents need one to answer.</p>;
  const { model_name: modelName, credential_name: credentialName, provider } = current.data;
  return (
    <p className="text-sm">
      <span className="font-medium">Current: </span>
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
  const [saved, setSaved] = useState<string | null>(null);
  const models = useChatModels(organisationId, credentialId);
  const options = models.data ?? [];
  // The wanted model if this credential offers it, otherwise its first chat model.
  const model = options.some((option) => option.id === wanted) ? wanted : (options[0]?.id ?? "");
  return (
    <form
      aria-label="Choose the Default Model"
      className="max-w-md space-y-3"
      onSubmit={(event: SubmitEvent<HTMLFormElement>) => {
        event.preventDefault();
        setSaved(null);
        save.mutate(
          { credential_id: credentialId, model },
          {
            onSuccess: (next) => {
              setSaved(`The Default Model is now ${next.model_name}.`);
            },
          },
        );
      }}
    >
      <FormError message={credentialFailure(save.error)} />
      {saved && (
        <p role="status" className="text-sm text-green-900">
          {saved}
        </p>
      )}
      <label className="block text-sm font-medium">
        Credential
        <select
          className={INPUT}
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
        <p role="alert">The models could not be loaded. Try again shortly.</p>
      ) : (
        <label className="block text-sm font-medium">
          Model
          <select
            className={INPUT}
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
      <button type="submit" className={PRIMARY} disabled={save.isPending || model === ""}>
        {save.isPending ? "Saving…" : "Save Default Model"}
      </button>
    </form>
  );
}

function OwnerControls({ organisationId }: { organisationId: string }) {
  const credentials = useCredentials(organisationId);
  const current = useDefaultModel(organisationId);
  if (credentials.isError) return <p role="alert">The credentials could not be loaded. Try again shortly.</p>;
  if (!credentials.data || current.data === undefined) return null;
  const chat = credentials.data
    .filter((credential) => credential.capabilities.includes("chat"))
    .sort((a, b) => a.name.localeCompare(b.name));
  const [first, ...rest] = chat;
  if (first === undefined) {
    return (
      <p className="text-sm text-slate-700">
        No credential can be used for chat yet.{" "}
        <Link to="/organisations/$organisationId/settings/credentials" params={{ organisationId }} className="underline">
          Add one on the Credentials tab
        </Link>
        .
      </p>
    );
  }
  return <Picker organisationId={organisationId} chat={[first, ...rest]} current={current.data} />;
}

/**
 * The Models tab: the Organisation's Default Model and the price table. Every Member sees them;
 * Owners choose the Default Model and override prices.
 */
export function ModelsPage({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  return (
    <div className="space-y-10">
      <DefaultModelSection organisationId={organisationId} isOwner={isOwner} />
      <PriceTable organisationId={organisationId} isOwner={isOwner} />
    </div>
  );
}

function DefaultModelSection({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  return (
    <section aria-labelledby="default-model-heading" className="space-y-4">
      <div className="space-y-1">
        <h2 id="default-model-heading" className="text-lg font-semibold">
          Default Model
        </h2>
        <p className="text-sm text-slate-700">
          New Agents answer with this model unless they choose their own. Only chat-capable credentials and their chat models can be
          chosen.
        </p>
      </div>
      <Current organisationId={organisationId} />
      {isOwner ? (
        <OwnerControls organisationId={organisationId} />
      ) : (
        <p className="text-sm text-slate-700">Only Owners can change the Default Model.</p>
      )}
    </section>
  );
}
