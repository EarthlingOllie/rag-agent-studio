import { Link, useNavigate } from "@tanstack/react-router";
import { type SubmitEvent, useState } from "react";

import { AuthLayout, Field, FormError, formValues, SubmitButton } from "./AuthLayout";
import { AuthRequestError, useVerifyMfa } from "./session";

function errorMessage(error: Error | null, recovery: boolean): string | undefined {
  if (error === null) return undefined;
  if (error instanceof AuthRequestError && error.status === 400) {
    return recovery ? "That recovery code is incorrect or already used." : "That code is incorrect. Try again.";
  }
  return "Something went wrong. Try again.";
}

const SIGN_IN_AGAIN = (
  <Link to="/sign-in" className="font-medium text-slate-900 underline">
    Sign in again
  </Link>
);

/** The second step of signing in for a Member with MFA: a code from their app, or a recovery code. */
export function MfaChallengePage() {
  const verify = useVerifyMfa();
  const navigate = useNavigate();
  const [recovery, setRecovery] = useState(false);
  const expired = verify.error instanceof AuthRequestError && verify.error.status === 401;

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    verify.mutate(formValues(event.currentTarget, ["code"]).code, {
      onSuccess: () => {
        void navigate({ to: "/" });
      },
    });
  }

  if (expired) {
    return (
      <AuthLayout title="Sign-in expired" footer={SIGN_IN_AGAIN}>
        <p role="alert">Your sign-in timed out or had too many wrong codes. Sign in again to get a new chance.</p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Two-factor authentication" footer={<>Wrong account? {SIGN_IN_AGAIN}</>}>
      <form onSubmit={onSubmit} className="space-y-4" aria-label="Two-factor authentication">
        <p className="text-sm text-slate-700">
          {recovery
            ? "Enter one of the recovery codes you saved when you turned on two-factor authentication. Each code works once."
            : "Enter the 6-digit code from your authenticator app."}
        </p>
        <FormError message={errorMessage(verify.error, recovery)} />
        {recovery ? (
          <Field key="recovery" label="Recovery code" name="code" autoComplete="off" />
        ) : (
          <Field key="totp" label="Authentication code" name="code" autoComplete="one-time-code" inputMode="numeric" />
        )}
        <SubmitButton pending={verify.isPending} label="Verify" pendingLabel="Verifying…" />
      </form>
      <button
        type="button"
        onClick={() => {
          setRecovery(!recovery);
          verify.reset();
        }}
        className="mt-4 text-sm text-slate-900 underline"
      >
        {recovery ? "Use your authenticator app instead" : "Use a recovery code instead"}
      </button>
    </AuthLayout>
  );
}
