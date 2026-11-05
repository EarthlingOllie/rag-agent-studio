import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import {
  CAPABILITY_NAMES,
  type Capability,
  type Credential,
  credentialFailure,
  CredentialRequestError,
  FAILURE_MESSAGES,
  type ProviderInfo,
  useAddCredential,
  useCheckCredential,
  useCredentials,
  useDeleteCredential,
  useProviders,
  useRotateCredential,
} from "./credentials";

const INPUT = "mt-1 block w-full rounded border border-slate-400 bg-white px-3 py-2 focus:outline-2 focus:outline-slate-900";
const BUTTON = "rounded border border-slate-400 px-3 py-1 text-sm hover:bg-slate-100 disabled:text-slate-600";
const PRIMARY = "rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:bg-slate-600";

/** `2026-06-01T09:30:00Z` → `2026-06-01 09:30 UTC`, the same for every viewer. */
function when(iso: string): string {
  return `${new Date(iso).toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

function capabilities(list: Capability[]): string {
  return list.map((capability) => CAPABILITY_NAMES[capability]).join(", ");
}

function Status({ credential }: { credential: Credential }) {
  if (credential.check_failure) {
    return (
      <span className="text-red-800">
        Check failed: {FAILURE_MESSAGES[credential.check_failure]}
      </span>
    );
  }
  return <span className="text-green-900">Working</span>;
}

/** Owner actions on one credential: check it again, rotate its key, or delete it. */
function CredentialActions({
  credential,
  busy,
  onCheck,
  onRotate,
  onDelete,
}: {
  credential: Credential;
  busy: boolean;
  onCheck: () => void;
  onRotate: (apiKey: string, done: () => void) => void;
  onDelete: () => void;
}) {
  const [mode, setMode] = useState<"idle" | "rotating" | "deleting">("idle");
  const [apiKey, setApiKey] = useState("");
  const idle = () => {
    setMode("idle");
    setApiKey("");
  };
  if (mode === "rotating") {
    return (
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event: SubmitEvent<HTMLFormElement>) => {
          event.preventDefault();
          onRotate(apiKey, idle);
        }}
      >
        <label className="text-sm">
          New API key for {credential.name}
          <input
            type="password"
            autoComplete="off"
            required
            value={apiKey}
            onChange={(event) => {
              setApiKey(event.target.value);
            }}
            className={INPUT}
          />
        </label>
        <button type="submit" className={BUTTON} disabled={busy}>
          Check and rotate
        </button>
        <button type="button" className={BUTTON} onClick={idle}>
          Cancel
        </button>
      </form>
    );
  }
  if (mode === "deleting") {
    return (
      <div className="flex gap-2">
        <button
          type="button"
          className={BUTTON}
          disabled={busy}
          onClick={() => {
            setMode("idle");
            onDelete();
          }}
        >
          Yes, delete {credential.name}
        </button>
        <button type="button" className={BUTTON} onClick={idle}>
          Cancel
        </button>
      </div>
    );
  }
  return (
    <div className="flex flex-wrap gap-2">
      <button type="button" className={BUTTON} disabled={busy} aria-label={`Check now: ${credential.name}`} onClick={onCheck}>
        Check now
      </button>
      <button
        type="button"
        className={BUTTON}
        aria-label={`Rotate key: ${credential.name}`}
        onClick={() => {
          setMode("rotating");
        }}
      >
        Rotate key
      </button>
      <button
        type="button"
        className={BUTTON}
        aria-label={`Delete: ${credential.name}`}
        onClick={() => {
          setMode("deleting");
        }}
      >
        Delete
      </button>
    </div>
  );
}

const KIND_NAMES: Record<string, string> = { agent: "Agent", project: "Project", default_model: "Organisation" };

/** The refusal to delete a credential something still uses, listing what uses it. */
function InUse({ name, error }: { name: string; error: CredentialRequestError }) {
  return (
    <div role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
      <p>{name} is still in use, so it wasn't deleted. Move these to another credential first:</p>
      <ul className="mt-1 list-disc pl-5">
        {error.references.map((reference) => (
          <li key={`${reference.kind}:${reference.id}`}>
            {KIND_NAMES[reference.kind] ?? reference.kind} {reference.name}
          </li>
        ))}
      </ul>
    </div>
  );
}

function CredentialsTable({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  const credentials = useCredentials(organisationId);
  const check = useCheckCredential(organisationId);
  const rotate = useRotateCredential(organisationId);
  const remove = useDeleteCredential(organisationId);
  const [done, setDone] = useState<string | null>(null);
  const [deleting, setDeleting] = useState("");
  if (credentials.isPending) return <p role="status">Loading credentials…</p>;
  if (credentials.isError) return <p role="alert">The credentials could not be loaded. Try again shortly.</p>;
  const busy = check.isPending || rotate.isPending || remove.isPending;
  const inUse = remove.error instanceof CredentialRequestError && remove.error.references.length > 0 ? remove.error : null;
  const start = () => {
    setDone(null);
    check.reset();
    rotate.reset();
    remove.reset();
  };
  return (
    <div className="space-y-3">
      {inUse ? <InUse name={deleting} error={inUse} /> : <FormError message={credentialFailure(rotate.error ?? remove.error ?? check.error)} />}
      {done && (
        <p role="status" className="text-sm text-green-900">
          {done}
        </p>
      )}
      {credentials.data.length === 0 ? (
        <p className="text-sm text-slate-700">No credentials yet.</p>
      ) : (
        <table className="w-full text-left text-sm" aria-label="Provider Credentials">
          <thead>
            <tr>
              <th className="py-2 pr-4 font-medium">Name</th>
              <th className="py-2 pr-4 font-medium">Provider</th>
              <th className="py-2 pr-4 font-medium">Used for</th>
              <th className="py-2 pr-4 font-medium">Key</th>
              <th className="py-2 pr-4 font-medium">Status</th>
              <th className="py-2 pr-4 font-medium">Last checked</th>
              {isOwner && (
                <th className="py-2 font-medium">
                  <span className="sr-only">Actions</span>
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {credentials.data.map((credential) => (
              <tr key={credential.id} className="border-t border-slate-200 align-top">
                <td className="py-2 pr-4">{credential.name}</td>
                <td className="py-2 pr-4">{PROVIDER_NAMES[credential.provider]}</td>
                <td className="py-2 pr-4">{capabilities(credential.capabilities)}</td>
                <td className="py-2 pr-4 font-mono" aria-label={`Key ending ${credential.masked_suffix}`}>
                  ••••{credential.masked_suffix}
                </td>
                <td className="py-2 pr-4">
                  <Status credential={credential} />
                </td>
                <td className="py-2 pr-4">{when(credential.last_checked_at)}</td>
                {isOwner && (
                  <td className="py-2">
                    <CredentialActions
                      credential={credential}
                      busy={busy}
                      onCheck={() => {
                        start();
                        check.mutate(credential.id, {
                          onSuccess: (checked) => {
                            setDone(checked.check_failure ? null : `${checked.name} passed its check.`);
                          },
                        });
                      }}
                      onRotate={(apiKey, finished) => {
                        start();
                        rotate.mutate(
                          { credentialId: credential.id, apiKey },
                          {
                            onSuccess: (rotated) => {
                              finished();
                              setDone(`The key of ${rotated.name} was checked and replaced.`);
                            },
                          },
                        );
                      }}
                      onDelete={() => {
                        start();
                        setDeleting(credential.name);
                        remove.mutate(credential.id, {
                          onSuccess: () => {
                            setDone(`${credential.name} was deleted.`);
                          },
                        });
                      }}
                    />
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const PROVIDER_NAMES: Record<Credential["provider"], string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  bedrock: "Amazon Bedrock",
  voyage: "Voyage AI",
};

/** Providers an Owner can add with an API key, from the capability registry. */
function apiKeyProviders(providers: ProviderInfo[]): ProviderInfo[] {
  return providers.filter((provider) => provider.auth_kinds.includes("api_key"));
}

function AddCredential({ organisationId, providers }: { organisationId: string; providers: ProviderInfo[] }) {
  const add = useAddCredential(organisationId);
  const first = providers[0] as ProviderInfo;
  const [providerId, setProviderId] = useState(first.id);
  const provider = providers.find((candidate) => candidate.id === providerId) as ProviderInfo;
  const offered = provider.capabilities.map((entry) => entry.capability);
  const [name, setName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [chosen, setChosen] = useState<Capability[]>(offered);
  const [saved, setSaved] = useState<string | null>(null);
  return (
    <section aria-labelledby="add-credential-heading" className="max-w-md space-y-3">
      <h3 id="add-credential-heading" className="text-base font-semibold">
        Add a credential
      </h3>
      <FormError message={credentialFailure(add.error)} />
      {saved && (
        <p role="status" className="text-sm text-green-900">
          {saved}
        </p>
      )}
      <form
        className="space-y-3"
        onSubmit={(event: SubmitEvent<HTMLFormElement>) => {
          event.preventDefault();
          setSaved(null);
          add.mutate(
            { name, provider: providerId as "anthropic" | "openai" | "voyage", api_key: apiKey, capabilities: chosen },
            {
              onSuccess: (credential) => {
                setSaved(`${credential.name} was checked and saved.`);
                setName("");
                setApiKey("");
              },
            },
          );
        }}
      >
        <label className="block text-sm font-medium">
          Provider
          <select
            className={INPUT}
            value={providerId}
            onChange={(event) => {
              const next = providers.find((candidate) => candidate.id === event.target.value) as ProviderInfo;
              setProviderId(next.id);
              setChosen(next.capabilities.map((entry) => entry.capability));
            }}
          >
            {providers.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm font-medium">
          Name
          <input
            required
            maxLength={100}
            placeholder="Marketing OpenAI"
            value={name}
            onChange={(event) => {
              setName(event.target.value);
            }}
            className={INPUT}
          />
        </label>
        <label className="block text-sm font-medium">
          API key
          <input
            type="password"
            autoComplete="off"
            required
            value={apiKey}
            onChange={(event) => {
              setApiKey(event.target.value);
            }}
            className={INPUT}
          />
        </label>
        <fieldset className="text-sm">
          <legend className="font-medium">Use for</legend>
          {offered.map((capability) => (
            <label key={capability} className="mr-4 inline-flex items-center gap-1">
              <input
                type="checkbox"
                checked={chosen.includes(capability)}
                onChange={(event) => {
                  setChosen(
                    event.target.checked
                      ? offered.filter((c) => c === capability || chosen.includes(c))
                      : chosen.filter((c) => c !== capability),
                  );
                }}
              />
              {CAPABILITY_NAMES[capability]}
            </label>
          ))}
        </fieldset>
        <button type="submit" className={PRIMARY} disabled={add.isPending || chosen.length === 0}>
          {add.isPending ? "Checking with the provider…" : "Check and save"}
        </button>
      </form>
    </section>
  );
}

/** Provider Credentials: every Member sees them; Owners add, check, rotate and delete them. */
export function CredentialsPage({ organisationId, isOwner }: { organisationId: string; isOwner: boolean }) {
  const providers = useProviders();
  return (
    <section aria-labelledby="credentials-heading" className="space-y-6">
      <div className="space-y-1">
        <h2 id="credentials-heading" className="text-lg font-semibold">
          Provider Credentials
        </h2>
        <p className="text-sm text-slate-700">
          Each key is checked with its provider when it's saved, stored encrypted, and never shown again: only its last four
          characters are.
        </p>
        {!isOwner && <p className="text-sm text-slate-700">Only Owners can add, check, rotate or delete credentials.</p>}
      </div>
      <CredentialsTable organisationId={organisationId} isOwner={isOwner} />
      {isOwner && providers.data && <AddCredential organisationId={organisationId} providers={apiKeyProviders(providers.data)} />}
      {isOwner && providers.isError && <p role="alert">The providers could not be loaded. Try again shortly.</p>}
    </section>
  );
}
