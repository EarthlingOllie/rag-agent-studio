import { Link, useSearch } from "@tanstack/react-router";
import type { SubmitEvent } from "react";

import { AuthLayout, Field, FormError, formValues, SubmitButton } from "./AuthLayout";
import { AuthRequestError, useCompletePasswordReset } from "./session";
import { MIN_PASSWORD_LENGTH } from "./SignUpPage";

const requestNewLink = (
  <Link to="/forgot-password" className="font-medium text-slate-900 underline">
    Request a new link
  </Link>
);

function ErrorWithNewLink({ children }: { children: string }) {
  return (
    <div role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
      {children} {requestNewLink}
    </div>
  );
}

const backToSignIn = (
  <Link to="/sign-in" className="font-medium text-slate-900 underline">
    Back to sign in
  </Link>
);

/** `/reset-password?token=…`: the page the emailed reset link opens. */
export function ResetPasswordPage() {
  const { token } = useSearch({ from: "/reset-password" });
  const completeReset = useCompletePasswordReset();

  if (token === undefined) {
    return (
      <AuthLayout title="Choose a new password" footer={backToSignIn}>
        <ErrorWithNewLink>This reset link is incomplete.</ErrorWithNewLink>
      </AuthLayout>
    );
  }

  const resetToken = token;

  if (completeReset.isSuccess) {
    return (
      <AuthLayout title="Choose a new password" footer={backToSignIn}>
        <p role="status" className="rounded border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-900">
          Your password has been reset and you've been signed out everywhere.{" "}
          <Link to="/sign-in" className="font-medium underline">
            Sign in with your new password
          </Link>
        </p>
      </AuthLayout>
    );
  }

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const { password } = formValues(event.currentTarget, ["password"]);
    completeReset.mutate({ token: resetToken, password });
  }

  const error = completeReset.error;
  const status = error instanceof AuthRequestError ? error.status : undefined;
  return (
    <AuthLayout title="Choose a new password" footer={backToSignIn}>
      <form onSubmit={onSubmit} className="space-y-4" aria-label="Choose a new password">
        {status === 400 ? (
          <ErrorWithNewLink>This reset link is invalid or has expired.</ErrorWithNewLink>
        ) : (
          <FormError
            message={
              error === null
                ? undefined
                : status === 422
                  ? `Choose a password of at least ${String(MIN_PASSWORD_LENGTH)} characters.`
                  : "Something went wrong. Try again."
            }
          />
        )}
        <Field
          label="New password"
          name="password"
          type="password"
          autoComplete="new-password"
          minLength={MIN_PASSWORD_LENGTH}
        />
        <p className="-mt-2 text-sm text-slate-700">At least {MIN_PASSWORD_LENGTH} characters.</p>
        <SubmitButton pending={completeReset.isPending} label="Set new password" pendingLabel="Saving…" />
      </form>
    </AuthLayout>
  );
}
