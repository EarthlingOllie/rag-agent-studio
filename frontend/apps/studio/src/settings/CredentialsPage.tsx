import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import {
  CAPABILITY_NAMES,
  type Capability,
  type Credential,
  credentialFailure,
  CredentialRequestError,
  failureMessages,
  type NewBedrockCredential,
  type ProviderInfo,
  useAddBedrockCredential,
  useAddCredential,
  useBedrockSetup,
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
        Check failed: {failureMessages(credential.provider)[credential.check_failure]}
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
      {credential.auth_kind === "api_key" && (
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
      )}
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
                <td className="py-2 pr-4">
                  {credential.region ? `${PROVIDER_NAMES[credential.provider]} · ${credential.region}` : PROVIDER_NAMES[credential.provider]}
                </td>
                <td className="py-2 pr-4">{capabilities(credential.capabilities)}</td>
                <KeyCell credential={credential} />
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

/** What identifies the credential's secret: its masked suffix, or the IAM role it assumes. */
function KeyCell({ credential }: { credential: Credential }) {
  if (credential.role_arn) {
    return (
      <td className="py-2 pr-4" aria-label={`IAM role ${credential.role_arn}`}>
        IAM role
        <span className="block font-mono text-xs break-all">{credential.role_arn}</span>
      </td>
    );
  }
  return (
    <td className="py-2 pr-4 font-mono" aria-label={`Key ending ${String(credential.masked_suffix)}`}>
      ••••{credential.masked_suffix}
    </td>
  );
}

const PROVIDER_NAMES: Record<Credential["provider"], string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  bedrock: "Amazon Bedrock",
  voyage: "Voyage AI",
};

type Copied = { what: string; ok: boolean } | null;

/** A read-only value with a button that copies it, for pasting into AWS. */
function Copyable({
  id,
  label,
  value,
  multiline = false,
  onCopied,
}: {
  id: string;
  label: string;
  value: string;
  multiline?: boolean;
  onCopied: (copied: Copied) => void;
}) {
  const field = `${INPUT} font-mono text-xs`;
  return (
    <div>
      <div className="flex items-end justify-between gap-2">
        <label htmlFor={id} className="text-sm font-medium">
          {label}
        </label>
        <button
          type="button"
          className={BUTTON}
          onClick={() => {
            navigator.clipboard.writeText(value).then(
              () => {
                onCopied({ what: label, ok: true });
              },
              () => {
                onCopied({ what: label, ok: false });
              },
            );
          }}
        >
          Copy {label.replace("Your ", "").replace(/^\w/, (c) => c.toLowerCase())}
        </button>
      </div>
      {multiline ? (
        <textarea id={id} readOnly rows={value.split("\n").length} value={value} className={field} />
      ) : (
        <input id={id} readOnly value={value} className={field} />
      )}
    </div>
  );
}

/** The Organisation's external ID and the policies an Owner pastes into their IAM role. */
function BedrockRoleSetup({ organisationId }: { organisationId: string }) {
  const setup = useBedrockSetup(organisationId);
  const [copied, setCopied] = useState<Copied>(null);
  if (setup.isError) return <p role="alert">The AWS setup details could not be loaded. Try again shortly.</p>;
  if (!setup.data) return <p role="status">Loading the AWS setup details…</p>;
  const { external_id: externalId, platform_principal: principal, trust_policy: trust, permissions_policy: permissions } = setup.data;
  return (
    <section aria-labelledby="bedrock-setup-heading" className="space-y-3 rounded border border-slate-300 bg-slate-50 p-3">
      <h4 id="bedrock-setup-heading" className="text-sm font-semibold">
        Set up the role in AWS
      </h4>
      <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-700">
        <li>In the IAM console, create a role with a custom trust policy, and paste the trust policy below.</li>
        <li>Attach the permissions policy below to the role (or a policy that allows the same Bedrock actions).</li>
        <li>In the Bedrock console, enable access to the models you'll use, in the region you choose here.</li>
        <li>Paste the role's ARN below. We'll assume the role, then check model access.</li>
      </ol>
      <Copyable id="bedrock-external-id" label="Your external ID" value={externalId} onCopied={setCopied} />
      <Copyable id="bedrock-principal" label="Our AWS principal" value={principal} onCopied={setCopied} />
      <Copyable id="bedrock-trust-policy" label="Trust policy" value={trust} multiline onCopied={setCopied} />
      <Copyable id="bedrock-permissions-policy" label="Permissions policy" value={permissions} multiline onCopied={setCopied} />
      <p role="status" className="text-sm">
        {copied?.ok === true && `${copied.what.replace("Your external", "External")} copied.`}
        {copied?.ok === false && "Couldn't copy. Select the text and copy it yourself."}
      </p>
    </section>
  );
}

type AwsAuthKind = "aws_role" | "aws_access_keys";

function TextField({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: "text" | "password";
  placeholder?: string;
}) {
  return (
    <label className="block text-sm font-medium">
      {label}
      <input
        type={type}
        autoComplete="off"
        required
        placeholder={placeholder}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        className={INPUT}
      />
    </label>
  );
}

function AddCredential({ organisationId, providers }: { organisationId: string; providers: ProviderInfo[] }) {
  const addKey = useAddCredential(organisationId);
  const addBedrock = useAddBedrockCredential(organisationId);
  const first = providers[0] as ProviderInfo;
  const [providerId, setProviderId] = useState(first.id);
  const provider = providers.find((candidate) => candidate.id === providerId) as ProviderInfo;
  const offered = provider.capabilities.map((entry) => entry.capability);
  const bedrock = providerId === "bedrock";
  const add = bedrock ? addBedrock : addKey;
  const [name, setName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [authKind, setAuthKind] = useState<AwsAuthKind>("aws_role");
  const [roleArn, setRoleArn] = useState("");
  const [region, setRegion] = useState("us-east-1");
  const [accessKeyId, setAccessKeyId] = useState("");
  const [secretAccessKey, setSecretAccessKey] = useState("");
  const [chosen, setChosen] = useState<Capability[]>(offered);
  const [saved, setSaved] = useState<string | null>(null);
  const onSaved = (credential: Credential) => {
    setSaved(`${credential.name} was checked and saved.`);
    setName("");
    setApiKey("");
    setRoleArn("");
    setAccessKeyId("");
    setSecretAccessKey("");
  };
  return (
    <section aria-labelledby="add-credential-heading" className="max-w-xl space-y-3">
      <h3 id="add-credential-heading" className="text-base font-semibold">
        Add a credential
      </h3>
      <FormError message={credentialFailure(add.error, providerId)} />
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
          if (bedrock) {
            const body: NewBedrockCredential =
              authKind === "aws_role"
                ? { name, auth_kind: "aws_role", role_arn: roleArn, region, capabilities: chosen }
                : {
                    name,
                    auth_kind: "aws_access_keys",
                    access_key_id: accessKeyId,
                    secret_access_key: secretAccessKey,
                    region,
                    capabilities: chosen,
                  };
            addBedrock.mutate(body, { onSuccess: onSaved });
            return;
          }
          addKey.mutate(
            { name, provider: providerId, api_key: apiKey, capabilities: chosen },
            { onSuccess: onSaved },
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
              addKey.reset();
              addBedrock.reset();
            }}
          >
            {providers.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </select>
        </label>
        <TextField label="Name" value={name} onChange={setName} placeholder={bedrock ? "Bedrock production" : "Marketing OpenAI"} />
        {bedrock ? (
          <>
            <fieldset className="text-sm">
              <legend id="aws-auth-legend" className="font-medium">
                How should we connect to your AWS account?
              </legend>
              <div role="radiogroup" aria-labelledby="aws-auth-legend" className="mt-1 space-y-1">
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="aws-auth-kind"
                    checked={authKind === "aws_role"}
                    onChange={() => {
                      setAuthKind("aws_role");
                    }}
                  />
                  IAM role (recommended)
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="aws-auth-kind"
                    checked={authKind === "aws_access_keys"}
                    onChange={() => {
                      setAuthKind("aws_access_keys");
                    }}
                  />
                  Access keys
                </label>
              </div>
            </fieldset>
            {authKind === "aws_role" ? (
              <>
                <p className="text-sm text-slate-700">
                  We assume a role in your AWS account using your Organisation's external ID, so no secret is stored and you can
                  revoke access at any time.
                </p>
                <BedrockRoleSetup organisationId={organisationId} />
                <TextField
                  label="Role ARN"
                  value={roleArn}
                  onChange={setRoleArn}
                  placeholder="arn:aws:iam::123456789012:role/StudioBedrockAccess"
                />
              </>
            ) : (
              <>
                <p className="text-sm text-slate-700">
                  Prefer the IAM role: access keys are long-lived secrets. If you use them, give the IAM user only the Bedrock
                  permissions it needs. We store the secret encrypted and never show it again.
                </p>
                <TextField label="Access key ID" value={accessKeyId} onChange={setAccessKeyId} />
                <TextField label="Secret access key" type="password" value={secretAccessKey} onChange={setSecretAccessKey} />
              </>
            )}
            <TextField label="AWS region" value={region} onChange={setRegion} placeholder="us-east-1" />
          </>
        ) : (
          <TextField label="API key" type="password" value={apiKey} onChange={setApiKey} />
        )}
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
          characters are. Amazon Bedrock can instead connect through an IAM role in your AWS account, so no secret is stored.
        </p>
        {!isOwner && <p className="text-sm text-slate-700">Only Owners can add, check, rotate or delete credentials.</p>}
      </div>
      <CredentialsTable organisationId={organisationId} isOwner={isOwner} />
      {isOwner && providers.data && <AddCredential organisationId={organisationId} providers={providers.data} />}
      {isOwner && providers.isError && <p role="alert">The providers could not be loaded. Try again shortly.</p>}
    </section>
  );
}
