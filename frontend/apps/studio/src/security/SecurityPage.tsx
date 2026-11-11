import { type ReactNode, type SubmitEvent, useId, useState } from "react";

import { ErrorNotice, formValues } from "../auth/AuthLayout";
import { AuthRequestError, type Session, useMe } from "../auth/session";
import { button, field, layout, Notice, PageHeader, Skeleton, surface, text } from "../design";
import {
  type Enrolment,
  type MfaStatus,
  useConfirmEnrolment,
  useDisableMfa,
  useMfaStatus,
  useReplaceRecoveryCodes,
  useStartEnrolment,
} from "./mfa";


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
        <Notice key={organisation.id} tone="warning">
          {organisation.name} requires two-factor authentication. Set it up to continue.
        </Notice>
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
      <label htmlFor={id} className={field.label}>
        {label}
      </label>
      <input
        id={id}
        name={name}
        type={type}
        autoComplete={autoComplete}
        required
        {...(inputMode === undefined ? {} : { inputMode })}
        className={`${field.input} max-w-xs`}
      />
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={surface.panel}>
      <h2 id={id} className={text.subheading}>
        {title}
      </h2>
      <div className="mt-3 flex flex-col items-start gap-4">{children}</div>
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
      <ol aria-label="Recovery codes" className="grid w-full max-w-sm grid-cols-2 gap-2 font-mono text-sm">
        {codes.map((code) => (
          <li key={code} className="rounded-lg border border-line-soft bg-sunken px-3 py-1.5 text-ink">
            {code}
          </li>
        ))}
      </ol>
      <button type="button" onClick={onDone} className={button.primary}>
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
  const captionId = useId();

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
      <figure aria-labelledby={captionId} className="flex flex-wrap items-center gap-5 rounded-xl border border-line-soft bg-sunken p-4">
        <img
          src={enrolment.qr_code}
          alt="QR code for your authenticator app"
          width={200}
          height={200}
          className="rounded-lg border border-line bg-surface"
        />
        <figcaption id={captionId} className="max-w-xs text-sm text-muted">
          Can't scan it? Enter this key instead: <code className="break-all font-mono text-ink">{enrolment.secret}</code>
        </figcaption>
      </figure>
      <form onSubmit={onSubmit} className="flex w-full flex-col items-start gap-4" aria-label="Confirm your authenticator app">
        <ErrorNotice message={errorMessage(confirm.error, "That code is incorrect. Check your app and try again.")} />
        <Input label="Code from your app" name="code" autoComplete="one-time-code" inputMode="numeric" />
        <div className="flex gap-3">
          <button type="submit" disabled={confirm.isPending} className={button.primary}>
            {confirm.isPending ? "Turning on…" : "Turn on"}
          </button>
          <button type="button" onClick={onCancel} className={button.secondary}>
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
        <strong className="font-semibold text-ink">Off.</strong> Protect your account with a code from an authenticator app as well as your password.
      </p>
      <ErrorNotice message={start.isError ? "Something went wrong. Try again." : undefined} />
      <button
        type="button"
        disabled={start.isPending}
        onClick={() => {
          start.mutate(undefined, { onSuccess: onEnrolment });
        }}
        className={button.primary}
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
    <div className="flex flex-col gap-6">
      <Panel title="Two-factor authentication">
        <p className="text-sm text-muted">
          <strong className="font-semibold text-ink">On.</strong> Signing in asks for a code from your authenticator app.
        </p>
      </Panel>
      <Panel title="Recovery codes">
        <p className="text-sm text-muted">
          {status.recovery_codes_remaining === 1
            ? "1 recovery code left."
            : `${String(status.recovery_codes_remaining)} recovery codes left.`}{" "}
          Making new codes stops the old ones working.
        </p>
        <form onSubmit={onReplace} className="flex w-full flex-col items-start gap-4" aria-label="Make new recovery codes">
          <ErrorNotice message={errorMessage(replace.error, "That code is incorrect. Try again.")} />
          <Input label="Code from your app" name="code" autoComplete="one-time-code" inputMode="numeric" />
          <button type="submit" disabled={replace.isPending} className={button.primary}>
            Make new recovery codes
          </button>
        </form>
      </Panel>
      <Panel title="Turn off two-factor authentication">
        <form onSubmit={onDisable} className="flex w-full flex-col items-start gap-4" aria-label="Turn off two-factor authentication">
          <ErrorNotice message={errorMessage(disable.error, "Your password or code is incorrect.")} />
          <Input label="Password" name="password" type="password" autoComplete="current-password" />
          <Input label="Code from your app or a recovery code" name="code" autoComplete="one-time-code" />
          <button type="submit" disabled={disable.isPending} className={button.secondary}>
            Turn off
          </button>
        </form>
      </Panel>
    </div>
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
    content = (
      <div className={surface.panel}>
        <Skeleton label="Loading your security settings" />
      </div>
    );
  } else if (status.isError) {
    content = <Notice tone="error">Your security settings could not be loaded. Try again shortly.</Notice>;
  } else if (status.data.enabled) {
    content = <MfaOn status={status.data} onNewCodes={showCodes} />;
  } else {
    content = <MfaOff onEnrolment={(enrolment) => { setView({ kind: "enrol", enrolment }); }} />;
  }

  return (
    <div className={layout.stack}>
      <PageHeader title="Security" description="Settings for your own account, in every Organisation you belong to." />
      <RequiredNotice />
      {content}
    </div>
  );
}
