import { Link } from "@tanstack/react-router";
import type { SubmitEvent } from "react";

import { AuthLayout, Field, FormError, formValues, SubmitButton } from "./AuthLayout";
import { AuthRequestError, useRequestPasswordReset } from "./session";

function errorMessage(error: Error | null): string | undefined {
  if (error === null) return undefined;
  if (error instanceof AuthRequestError && error.status === 422) return "Enter a valid email address.";
  return "Something went wrong. Try again.";
}

const backToSignIn = (
  <Link to="/sign-in" className="font-medium text-ink underline">
    Back to sign in
  </Link>
);

/** `/forgot-password`: asks for a reset link. The answer never says whether the email is registered. */
export function ForgotPasswordPage() {
  const requestReset = useRequestPasswordReset();

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    requestReset.mutate(formValues(event.currentTarget, ["email"]));
  }

  return (
    <AuthLayout title="Reset your password" footer={backToSignIn}>
      {requestReset.isSuccess ? (
        <p role="status" className="rounded border border-accent-soft bg-accent-soft px-3 py-2 text-sm text-accent-ink">
          If that email is registered, a reset link is on its way. Check your inbox.
        </p>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4" aria-label="Reset your password">
          <FormError message={errorMessage(requestReset.error)} />
          <p className="text-sm text-muted">Enter your email and we'll send you a link to choose a new password.</p>
          <Field label="Email" name="email" type="email" autoComplete="email" />
          <SubmitButton pending={requestReset.isPending} label="Send reset link" pendingLabel="Sending…" />
        </form>
      )}
    </AuthLayout>
  );
}
