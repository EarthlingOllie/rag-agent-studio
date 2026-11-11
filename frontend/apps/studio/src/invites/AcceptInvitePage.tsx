import { Link, Navigate, useSearch } from "@tanstack/react-router";
import type { ReactNode, SubmitEvent } from "react";

import { AuthLayout, ErrorNotice, Field, formValues, PANEL_LINK, SubmitButton } from "../auth/AuthLayout";
import { button, Notice, notice, Skeleton } from "../design";
import { AuthRequestError, type Session, useMe, useSignIn, useSignOut, useVerifyMfa } from "../auth/session";
import { signInErrorMessage } from "../auth/SignInPage";
import { MIN_PASSWORD_LENGTH } from "../auth/SignUpPage";
import {
  type InvitePreview,
  InviteRequestError,
  ROLE_NAMES,
  useAcceptInvite,
  useInvitePreview,
  useSignUpWithInvite,
} from "./invites";

const TITLE = "Accept invite";
const INVALID = "This invite link is invalid or has expired. Ask an Owner of the Organisation for a new one.";
const SOMETHING_WRONG = "Something went wrong. Try again.";

const signInLink = (
  <Link to="/sign-in" className={PANEL_LINK}>
    Sign in
  </Link>
);

/** The invite page while the invite can't be shown: loading, or why it failed. */
function Message({ children }: { children: ReactNode }) {
  return (
    <AuthLayout title={TITLE} footer={signInLink}>
      {children}
    </AuthLayout>
  );
}

function statusOf(error: Error | null): number | undefined {
  if (error instanceof InviteRequestError || error instanceof AuthRequestError) return error.status;
  return undefined;
}

function Invitation({ preview }: { preview: InvitePreview }) {
  return (
    <p className="text-sm text-muted">
      {preview.invited_by_name} invited <strong className="font-medium text-ink">{preview.email}</strong> to join{" "}
      <strong className="font-medium text-ink">{preview.organisation_name}</strong> as{" "}
      {preview.role === "owner" ? "an Owner" : "an Editor"}.
    </p>
  );
}

/** A signed-in Member whose email the invite is for: one click joins. */
function JoinAsMember({ token, preview }: { token: string; preview: InvitePreview }) {
  const accept = useAcceptInvite();
  const status = statusOf(accept.error);
  return (
    <div className="space-y-4">
      <Invitation preview={preview} />
      <ErrorNotice
        message={accept.error === null ? undefined : status === 400 ? INVALID : SOMETHING_WRONG}
      />
      <button
        type="button"
        disabled={accept.isPending}
        onClick={() => {
          accept.mutate(token);
        }}
        className={`${button.primary} w-full`}
      >
        {accept.isPending ? "Joining…" : `Join ${preview.organisation_name}`}
      </button>
    </div>
  );
}

/** Signed in as someone else: the invite is bound to its email. */
function WrongAccount({ session, preview }: { session: Session; preview: InvitePreview }) {
  const signOut = useSignOut();
  return (
    <div className="space-y-4">
      <Invitation preview={preview} />
      <p role="alert" className={notice.warning}>
        You're signed in as {session.member.email}. Sign out, then open the link again to accept as {preview.email}.
      </p>
      <ErrorNotice message={signOut.isError ? "Sign-out failed. Try again." : undefined} />
      <button
        type="button"
        disabled={signOut.isPending}
        onClick={() => {
          signOut.mutate();
        }}
        className={`${button.secondary} w-full`}
      >
        Sign out
      </button>
    </div>
  );
}

/** No account for the invited email yet: create one and join in a single step. */
function CreateAccount({ token, preview }: { token: string; preview: InvitePreview }) {
  const signUp = useSignUpWithInvite();
  const status = statusOf(signUp.error);

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const { name, password } = formValues(event.currentTarget, ["name", "password"]);
    signUp.mutate({ token, name, password });
  }

  const messages: Partial<Record<number, string>> = {
    400: INVALID,
    409: "An account with this email already exists. Sign in to accept the invite.",
    422: `Enter your name and a password of at least ${String(MIN_PASSWORD_LENGTH)} characters.`,
  };
  return (
    <form onSubmit={onSubmit} className="space-y-4" aria-label="Create your account and join">
      <Invitation preview={preview} />
      <ErrorNotice message={signUp.error === null ? undefined : (messages[status ?? 0] ?? SOMETHING_WRONG)} />
      <Field label="Your name" name="name" autoComplete="name" />
      <Field label="Password" name="password" type="password" autoComplete="new-password" minLength={MIN_PASSWORD_LENGTH} />
      <p className="-mt-2 text-sm text-muted">At least {MIN_PASSWORD_LENGTH} characters.</p>
      <SubmitButton pending={signUp.isPending} label="Create account and join" pendingLabel="Creating your account…" />
    </form>
  );
}

/** An account exists for the invited email: sign in here (with MFA if needed), then join. */
function SignInToAccept({ preview }: { preview: InvitePreview }) {
  const signIn = useSignIn();
  const verify = useVerifyMfa();
  const needsCode = signIn.data?.mfaRequired === true;

  if (needsCode) {
    const codeError =
      verify.error === null
        ? undefined
        : statusOf(verify.error) === 400
          ? "That code is incorrect. Try again."
          : statusOf(verify.error) === 401
            ? "Your sign-in timed out. Reload the page to sign in again."
            : SOMETHING_WRONG;
    return (
      <form
        className="space-y-4"
        aria-label="Two-factor authentication"
        onSubmit={(event) => {
          event.preventDefault();
          verify.mutate(formValues(event.currentTarget, ["code"]).code);
        }}
      >
        <Invitation preview={preview} />
        <p className="text-sm text-muted">Enter the 6-digit code from your authenticator app, or a recovery code.</p>
        <ErrorNotice message={codeError} />
        <Field label="Authentication code" name="code" autoComplete="one-time-code" />
        <SubmitButton pending={verify.isPending} label="Verify" pendingLabel="Verifying…" />
      </form>
    );
  }

  return (
    <form
      className="space-y-4"
      aria-label="Sign in to accept"
      onSubmit={(event) => {
        event.preventDefault();
        signIn.mutate({ email: preview.email, password: formValues(event.currentTarget, ["password"]).password });
      }}
    >
      <Invitation preview={preview} />
      <p className="text-sm text-muted">You already have an account. Sign in to accept.</p>
      <ErrorNotice message={signInErrorMessage(signIn.error)} />
      <Field label="Password" name="password" type="password" autoComplete="current-password" />
      <p className="-mt-2 text-sm">
        <Link to="/forgot-password" className={PANEL_LINK}>
          Forgot your password?
        </Link>
      </p>
      <SubmitButton pending={signIn.isPending} label="Sign in" pendingLabel="Signing in…" />
    </form>
  );
}

function AcceptInvite({ token }: { token: string }) {
  const preview = useInvitePreview(token);
  const me = useMe();
  if (preview.isPending || me.isPending) {
    return (
      <Message>
        <Skeleton label="Loading the invite" />
      </Message>
    );
  }
  if (preview.isError) {
    return (
      <Message>
        <Notice tone="error">{statusOf(preview.error) === 404 ? INVALID : SOMETHING_WRONG}</Notice>
      </Message>
    );
  }
  if (me.isError) {
    return (
      <Message>
        <Notice tone="error">The Studio could not reach the API. Try again shortly.</Notice>
      </Message>
    );
  }

  const invite = preview.data;
  const session = me.data;
  // Joined (just now, through this page): the session lists the Organisation, so open it.
  if (session?.organisations.some((organisation) => organisation.id === invite.organisation_id)) {
    return <Navigate to="/organisations/$organisationId/projects" params={{ organisationId: invite.organisation_id }} />;
  }
  const title = `Join ${invite.organisation_name}`;
  let body: ReactNode;
  if (session === null) {
    body = invite.account_exists ? <SignInToAccept preview={invite} /> : <CreateAccount token={token} preview={invite} />;
  } else if (session.member.email === invite.email) {
    body = <JoinAsMember token={token} preview={invite} />;
  } else {
    body = <WrongAccount session={session} preview={invite} />;
  }
  return (
    <AuthLayout title={title} footer={<>Role: {ROLE_NAMES[invite.role]}</>}>
      {body}
    </AuthLayout>
  );
}

/** `/accept-invite?token=…`: the page an invite link opens. */
export function AcceptInvitePage() {
  const { token } = useSearch({ from: "/accept-invite" });
  if (token === undefined) {
    return (
      <Message>
        <Notice tone="error">This invite link is incomplete.</Notice>
      </Message>
    );
  }
  return <AcceptInvite token={token} />;
}
