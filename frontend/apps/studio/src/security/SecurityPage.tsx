import { type ReactNode, type SubmitEvent, useId, useState } from "react";

import { FormError, formValues } from "../auth/AuthLayout";
import { AuthRequestError, type Session, useMe } from "../auth/session";
import {
  type Enrolment,
  type MfaStatus,
  useConfirmEnrolment,
  useDisableMfa,
  useMfaStatus,
  useReplaceRecoveryCodes,
  useStartEnrolment,
} from "./mfa";

const BUTTON = "rounded bg-accent px-4 py-2 text-sm font-medium text-on-accent hover:bg-accent-hover disabled:bg-muted";
const SECONDARY_BUTTON = "rounded border border-field px-4 py-2 text-sm hover:bg-sunken";

function errorMessage(error: Error | null, incorrect: string): string | undefined {
  if (error === null) return undefined;
  if (error instanceof AuthRequestError && error.status === 400) return incorrect;
  const detail = error instanceof AuthRequestError && error.status === 409 ? (Object(error.body) as { detail?: unknown }).detail : undefined;
  return typeof detail === "string" ? detail : "Something went wrong. Try again.";
}

/** Names each Organisation that requires MFA while the Member doesn't have it yet. */
function RequiredNotice() {
  const session = useMe().data as Session;
  if (session.member.mfa_enabled) return null;
  const requiring = session.organisations.filter((organisation) => organisation.mfa_required);
  return (
    <>
      {requiring.map((organisation) => (
        <p key={organisation.id} className="mt-4 rounded border border-flag bg-flag-soft px-3 py-2 text-sm text-flag">
          {organisation.name} requires two-factor authentication. Set it up to continue.
        </p>
      ))}
    </>
  );
}

function Input({ label, name, type = "text", autoComplete, inputMode }: {
  label: string;
  name: string;
  type?: string;
  autoComplete: string;
  inputMode?: "numeric";
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <input
        id={id}
        name={name}
        type={type}
        autoComplete={autoComplete}
        required
        {...(inputMode === undefined ? {} : { inputMode })}
        className="mt-1 block w-full max-w-xs rounded border border-field px-3 py-2 focus:outline-2 focus:outline-accent"
      />
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="mt-6 rounded-lg border border-line bg-surface p-6">
      <h2 id={id} className="text-lg font-semibold">
        {title}
      </h2>
      <div className="mt-3 space-y-4">{children}</div>
    </section>
  );
}

/** Recovery codes, shown once, straight after they are made. */
function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  return (
    <Panel title="Save your recovery codes">
      <p className="text-sm text-muted">
        If you lose your phone, each of these codes signs you in once. Keep them somewhere safe: they won't be shown
        again.
      </p>
      <ol aria-label="Recovery codes" className="grid max-w-sm grid-cols-2 gap-2 font-mono text-sm">
        {codes.map((code) => (
          <li key={code} className="rounded bg-sunken px-2 py-1">
            {code}
          </li>
        ))}
      </ol>
      <button type="button" onClick={onDone} className={BUTTON}>
        I've saved my recovery codes
      </button>
    </Panel>
  );
}

function Enrol({ enrolment, onCancel, onConfirmed }: {
  enrolment: Enrolment;
  onCancel: () => void;
  onConfirmed: (codes: string[]) => void;
}) {
  const confirm = useConfirmEnrolment();

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    confirm.mutate(formValues(event.currentTarget, ["code"]).code, {
      onSuccess: (result) => {
        onConfirmed(result.recovery_codes);
      },
    });
  }

  return (
    <Panel title="Set up your authenticator app">
      <p className="text-sm text-muted">
        Scan this QR code with an authenticator app such as Google Authenticator, 1Password or Authy.
      </p>
      <img src={enrolment.qr_code} alt="QR code for your authenticator app" width={200} height={200} />
      <p className="text-sm text-muted">
        Can't scan it? Enter this key instead: <code className="break-all font-mono text-ink">{enrolment.secret}</code>
      </p>
      <form onSubmit={onSubmit} className="space-y-4" aria-label="Confirm your authenticator app">
        <FormError message={errorMessage(confirm.error, "That code is incorrect. Check your app and try again.")} />
        <Input label="Code from your app" name="code" autoComplete="one-time-code" inputMode="numeric" />
        <div className="flex gap-3">
          <button type="submit" disabled={confirm.isPending} className={BUTTON}>
            {confirm.isPending ? "Turning on…" : "Turn on"}
          </button>
          <button type="button" onClick={onCancel} className={SECONDARY_BUTTON}>
            Cancel
          </button>
        </div>
      </form>
    </Panel>
  );
}

function MfaOff({ onEnrolment }: { onEnrolment: (enrolment: Enrolment) => void }) {
  const start = useStartEnrolment();
  return (
    <Panel title="Two-factor authentication">
      <p className="text-sm text-muted">
        <strong>Off.</strong> Protect your account with a code from an authenticator app as well as your password.
      </p>
      <FormError message={start.isError ? "Something went wrong. Try again." : undefined} />
      <button
        type="button"
        disabled={start.isPending}
        onClick={() => {
          start.mutate(undefined, { onSuccess: onEnrolment });
        }}
        className={BUTTON}
      >
        Set up two-factor authentication
      </button>
    </Panel>
  );
}

function MfaOn({ status, onNewCodes }: { status: MfaStatus; onNewCodes: (codes: string[]) => void }) {
  const replace = useReplaceRecoveryCodes();
  const disable = useDisableMfa();

  function onReplace(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    replace.mutate(formValues(event.currentTarget, ["code"]).code, {
      onSuccess: (result) => {
        onNewCodes(result.recovery_codes);
      },
    });
  }

  function onDisable(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    disable.mutate(formValues(event.currentTarget, ["password", "code"]));
  }

  return (
    <>
      <Panel title="Two-factor authentication">
        <p className="text-sm text-muted">
          <strong>On.</strong> Signing in asks for a code from your authenticator app.
        </p>
      </Panel>
      <Panel title="Recovery codes">
        <p className="text-sm text-muted">
          {status.recovery_codes_remaining === 1
            ? "1 recovery code left."
            : `${String(status.recovery_codes_remaining)} recovery codes left.`}{" "}
          Making new codes stops the old ones working.
        </p>
        <form onSubmit={onReplace} className="space-y-4" aria-label="Make new recovery codes">
          <FormError message={errorMessage(replace.error, "That code is incorrect. Try again.")} />
          <Input label="Code from your app" name="code" autoComplete="one-time-code" inputMode="numeric" />
          <button type="submit" disabled={replace.isPending} className={BUTTON}>
            Make new recovery codes
          </button>
        </form>
      </Panel>
      <Panel title="Turn off two-factor authentication">
        <form onSubmit={onDisable} className="space-y-4" aria-label="Turn off two-factor authentication">
          <FormError message={errorMessage(disable.error, "Your password or code is incorrect.")} />
          <Input label="Password" name="password" type="password" autoComplete="current-password" />
          <Input label="Code from your app or a recovery code" name="code" autoComplete="one-time-code" />
          <button type="submit" disabled={disable.isPending} className={SECONDARY_BUTTON}>
            Turn off
          </button>
        </form>
      </Panel>
    </>
  );
}

type View = { kind: "status" } | { kind: "enrol"; enrolment: Enrolment } | { kind: "codes"; codes: string[] };

/** The signed-in Member's own security settings: two-factor authentication and recovery codes. */
export function SecurityPage() {
  const status = useMfaStatus();
  const [view, setView] = useState<View>({ kind: "status" });
  const showCodes = (codes: string[]) => {
    setView({ kind: "codes", codes });
  };

  let content: ReactNode;
  if (view.kind === "codes") {
    content = <RecoveryCodes codes={view.codes} onDone={() => { setView({ kind: "status" }); }} />;
  } else if (view.kind === "enrol") {
    content = (
      <Enrol enrolment={view.enrolment} onCancel={() => { setView({ kind: "status" }); }} onConfirmed={showCodes} />
    );
  } else if (status.isPending) {
    content = <p role="status">Loading…</p>;
  } else if (status.isError) {
    content = <p role="alert">Your security settings could not be loaded. Try again shortly.</p>;
  } else if (status.data.enabled) {
    content = <MfaOn status={status.data} onNewCodes={showCodes} />;
  } else {
    content = <MfaOff onEnrolment={(enrolment) => { setView({ kind: "enrol", enrolment }); }} />;
  }

  return (
    <section aria-labelledby="page-heading">
      <h1 id="page-heading" className="text-2xl font-semibold">
        Security
      </h1>
      <p className="mt-2 text-muted">Settings for your own account, in every Organisation you belong to.</p>
      <RequiredNotice />
      {content}
    </section>
  );
}
