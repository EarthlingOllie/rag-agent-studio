import { type SubmitEvent, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { Badge, button, ConfirmDialog, field, Notice, notice, surface, table, text } from "../design";
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


/** `2026-06-01T09:30:00Z` → `2026-06-01 09:30 UTC`, the same for every viewer. */
function when(iso: string): string {
  return `${new Date(iso).toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

function capabilities(list: Capability[]): string {
  return list.map((capability) => CAPABILITY_NAMES[capability]).join(", ");
}

/** The last check's result: a Working or Check failed badge, with the reason for a failure. */
function CheckResult({ credential }: { credential: Credential }) {
  if (credential.check_failure) {
    return (
      <>
        <Badge kind="checkFailed" />{" "}
        <span className="mt-1 block max-w-xs text-xs text-muted">{failureMessages(credential.provider)[credential.check_failure]}</span>
      </>
    );
  }
  return <Badge kind="checkPassed" />;
}

/** Owner actions on one credential: check it again, rotate its key, or delete it (after confirming). */
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
        className="flex flex-wrap items-end justify-end gap-2"
        onSubmit={(event: SubmitEvent<HTMLFormElement>) => {
          event.preventDefault();
          onRotate(apiKey, idle);
        }}
      >
        <label className={`${field.label} text-left`}>
          New API key for {credential.name}
          <input
            type="password"
            autoComplete="off"
            required
            value={apiKey}
            onChange={(event) => {
              setApiKey(event.target.value);
            }}
            className={field.input}
          />
        </label>
        <button type="submit" className={button.primary} disabled={busy}>
          Check and rotate
        </button>
        <button type="button" className={button.secondary} onClick={idle}>
          Cancel
        </button>
      </form>
    );
  }
  return (
    <div className="flex flex-wrap justify-end gap-2">
      <button type="button" className={button.secondary} disabled={busy} aria-label={`Check now: ${credential.name}`} onClick={onCheck}>
        Check now
      </button>
      {credential.auth_kind === "api_key" && (
        <button
          type="button"
          className={button.secondary}
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
        className={button.danger}
        aria-label={`Delete: ${credential.name}`}
        onClick={() => {
          setMode("deleting");
        }}
      >
        Delete
      </button>
      <ConfirmDialog
        open={mode === "deleting"}
        title={`Delete ${credential.name}?`}
        confirmLabel={`Yes, delete ${credential.name}`}
        destructive
        busy={busy}
        onCancel={idle}
        onConfirm={() => {
          setMode("idle");
          onDelete();
        }}
      >
        Its key is erased and it can't be used again. A credential an Agent, Project or the Default Model still uses is not
        deleted: you are told what uses it.
      </ConfirmDialog>
    </div>
  );
}

const KIND_NAMES: Record<string, string> = { agent: "Agent", project: "Project", default_model: "Organisation" };

/** The refusal to delete a credential something still uses, listing what uses it. */
function InUse({ name, error }: { name: string; error: CredentialRequestError }) {
  return (
    <div role="alert" className={notice.error}>
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
  if (credentials.isPending) return <p role="status" className={text.muted}>Loading credentials…</p>;
  if (credentials.isError) return <p role="alert" className={text.muted}>The credentials could not be loaded. Try again shortly.</p>;
  const busy = check.isPending || rotate.isPending || remove.isPending;
  const inUse = remove.error instanceof CredentialRequestError && remove.error.references.length > 0 ? remove.error : null;
  const start = () => {
    setDone(null);
    check.reset();
    rotate.reset();
    remove.reset();
  };
  return (
    <div className="flex flex-col gap-3">
      {inUse ? <InUse name={deleting} error={inUse} /> : <FormError message={credentialFailure(rotate.error ?? remove.error ?? check.error)} />}
      {done && <Notice tone="success">{done}</Notice>}
      {credentials.data.length === 0 ? (
        <p className={text.muted}>No credentials yet.</p>
      ) : (
        <div className={table.wrap}>
          <table className={`${table.table} min-w-[880px]`} aria-label="Provider Credentials">
            <thead>
              <tr>
                <th className={table.th}>Name</th>
                <th className={table.th}>Provider</th>
                <th className={table.th}>Used for</th>
                <th className={table.th}>Key</th>
                <th className={table.th}>Status</th>
                <th className={table.th}>Last checked</th>
                {isOwner && (
                  <th className={table.th}>
                    <span className="sr-only">Actions</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {credentials.data.map((credential) => (
                <tr key={credential.id} className={`${table.row} align-top`}>
                  <td className={`${table.td} font-medium`}>{credential.name}</td>
                  <td className={table.td}>
                    {credential.region ? `${PROVIDER_NAMES[credential.provider]} · ${credential.region}` : PROVIDER_NAMES[credential.provider]}
                  </td>
                  <td className={table.tdMuted}>{capabilities(credential.capabilities)}</td>
                  <KeyCell credential={credential} />
                  <td className={table.td}>
                    <CheckResult credential={credential} />
                  </td>
                  <td className={`${table.tdMuted} font-mono text-[13px] whitespace-nowrap`}>{when(credential.last_checked_at)}</td>
                  {isOwner && (
                    <td className={table.td}>
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
        </div>
      )}
    </div>
  );
}

/** What identifies the credential's secret: its masked suffix, or the IAM role it assumes. */
function KeyCell({ credential }: { credential: Credential }) {
  if (credential.role_arn) {
    return (
      <td className={table.td} aria-label={`IAM role ${credential.role_arn}`}>
        IAM role
        <span className="block font-mono text-xs break-all text-muted">{credential.role_arn}</span>
      </td>
    );
  }
  return (
    <td className={`${table.td} font-mono text-[13px]`} aria-label={`Key ending ${String(credential.masked_suffix)}`}>
      ••••{credential.masked_suffix}
    </td>
  );
}

const PROVIDER_NAMES: Record<Credential["provider"], string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  bedrock: "Amazon Bedrock",
  voyage: "Voyage AI",
  // The seeded demo provider: canned answers from the Knowledge Base, never a real model.
  demo: "Demo: canned answers, not a real model",
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
  const box = `${field.inputMono} text-xs`;
  return (
    <div>
      <div className="flex items-end justify-between gap-2">
        <label htmlFor={id} className={field.label}>
          {label}
        </label>
        <button
          type="button"
          className={button.secondary}
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
        <textarea id={id} readOnly rows={value.split("\n").length} value={value} className={box} />
      ) : (
        <input id={id} readOnly value={value} className={box} />
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
    <section aria-labelledby="bedrock-setup-heading" className="flex flex-col gap-3 rounded-xl bg-sunken p-4">
      <h4 id="bedrock-setup-heading" className={text.subheading}>
        Set up the role in AWS
      </h4>
      <ol className="list-decimal space-y-1 pl-5 text-sm text-ink-2">
        <li>In the IAM console, create a role with a custom trust policy, and paste the trust policy below.</li>
        <li>Attach the permissions policy below to the role (or a policy that allows the same Bedrock actions).</li>
        <li>In the Bedrock console, enable access to the models you'll use, in the region you choose here.</li>
        <li>Paste the role's ARN below. We'll assume the role, then check model access.</li>
      </ol>
      <Copyable id="bedrock-external-id" label="Your external ID" value={externalId} onCopied={setCopied} />
      <Copyable id="bedrock-principal" label="Our AWS principal" value={principal} onCopied={setCopied} />
      <Copyable id="bedrock-trust-policy" label="Trust policy" value={trust} multiline onCopied={setCopied} />
      <Copyable id="bedrock-permissions-policy" label="Permissions policy" value={permissions} multiline onCopied={setCopied} />
      <p role="status" className="text-sm text-ink-2">
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
    <label className={field.label}>
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
        className={type === "password" ? field.inputMono : field.input}
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
    <section aria-labelledby="add-credential-heading" className={`${surface.panel} flex max-w-2xl flex-col gap-4`}>
      <h3 id="add-credential-heading" className={text.heading}>
        Add a credential
      </h3>
      <FormError message={credentialFailure(add.error, providerId)} />
      {saved && <Notice tone="success">{saved}</Notice>}
      <form
        className="flex flex-col gap-4"
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
        <label className={field.label}>
          Provider
          <select
            className={field.select}
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
            <fieldset className="text-sm text-ink">
              <legend id="aws-auth-legend" className={field.label}>
                How should we connect to your AWS account?
              </legend>
              <div role="radiogroup" aria-labelledby="aws-auth-legend" className="mt-1.5 space-y-1.5">
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    className={field.checkbox}
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
                    className={field.checkbox}
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
                <p className={text.muted}>
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
                <p className={text.muted}>
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
        <fieldset className="text-sm text-ink">
          <legend className={field.label}>Use for</legend>
          {offered.map((capability) => (
            <label key={capability} className="mt-1.5 mr-4 inline-flex items-center gap-2">
              <input
                type="checkbox"
                    className={field.checkbox}
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
        <button type="submit" className={`${button.primary} self-start`} disabled={add.isPending || chosen.length === 0}>
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
    <section aria-labelledby="credentials-heading" className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h2 id="credentials-heading" className={text.heading}>
          Provider Credentials
        </h2>
        <p className={text.muted}>
          Each key is checked with its provider when it's saved, stored encrypted, and never shown again: only its last four
          characters are. Amazon Bedrock can instead connect through an IAM role in your AWS account, so no secret is stored.
        </p>
        {!isOwner && <p className={text.muted}>Only Owners can add, check, rotate or delete credentials.</p>}
      </div>
      <CredentialsTable organisationId={organisationId} isOwner={isOwner} />
      {isOwner && providers.data && <AddCredential organisationId={organisationId} providers={providers.data} />}
      {isOwner && providers.isError && <p role="alert">The providers could not be loaded. Try again shortly.</p>}
    </section>
  );
}
