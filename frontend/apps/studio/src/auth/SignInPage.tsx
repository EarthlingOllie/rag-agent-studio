import { Link, useNavigate } from "@tanstack/react-router";
import type { SubmitEvent } from "react";

import { AuthLayout, ErrorNotice, Field, formValues, PANEL_LINK, SubmitButton } from "./AuthLayout";
import { AuthRequestError, type Throttled, throttledDetails, useSignIn } from "./session";

function plural(count: number, unit: string): string {
  return `${String(count)} ${unit}${count === 1 ? "" : "s"}`;
}

function throttledMessage({ locked, retry_after_seconds: seconds }: Throttled): string {
  const wait = locked
    ? `Sign-in is locked for ${plural(Math.ceil(seconds / 60), "minute")}. Try again after that.`
    : `Wait ${plural(seconds, "second")}, then try again.`;
  return `Too many failed sign-in attempts. ${wait}`;
}

/** What a failed sign-in tells the person; the accept-invite page shows the same. */
export function signInErrorMessage(error: Error | null): string | undefined {
  if (error === null) return undefined;
  if (error instanceof AuthRequestError && error.status === 401) return "Email or password is incorrect.";
  const throttled = throttledDetails(error);
  if (throttled) return throttledMessage(throttled);
  return "Something went wrong. Try again.";
}

export function SignInPage() {
  const signIn = useSignIn();
  const navigate = useNavigate();

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    signIn.mutate(formValues(event.currentTarget, ["email", "password"]), {
      onSuccess: (outcome) => {
        void navigate({ to: outcome.mfaRequired ? "/sign-in/mfa" : "/" });
      },
    });
  }

  return (
    <AuthLayout
      title="Sign in"
      footer={
        <>
          New to RAG Agent Studio?{" "}
          <Link to="/sign-up" className={PANEL_LINK}>
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" aria-label="Sign in">
        <ErrorNotice message={signInErrorMessage(signIn.error)} />
        <Field label="Email" name="email" type="email" autoComplete="email" />
        <Field label="Password" name="password" type="password" autoComplete="current-password" />
        <p className="-mt-2 text-sm">
          <Link to="/forgot-password" className={PANEL_LINK}>
            Forgot your password?
          </Link>
        </p>
        <SubmitButton pending={signIn.isPending} label="Sign in" pendingLabel="Signing in…" />
      </form>
    </AuthLayout>
  );
}
