import { Link, useNavigate } from "@tanstack/react-router";
import type { SubmitEvent } from "react";

import { AuthLayout, Field, FormError, formValues, SubmitButton } from "./AuthLayout";
import { AuthRequestError, useSignUp } from "./session";

export const MIN_PASSWORD_LENGTH = 12;

function errorMessage(error: Error | null): string | undefined {
  if (error === null) return undefined;
  if (error instanceof AuthRequestError && error.status === 409) {
    return "An account with this email already exists. Sign in instead.";
  }
  if (error instanceof AuthRequestError && error.status === 422) {
    return "Check your details: every field is required and the email must be valid.";
  }
  return "Something went wrong. Try again.";
}

export function SignUpPage() {
  const signUp = useSignUp();
  const navigate = useNavigate();

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = formValues(event.currentTarget, ["name", "email", "password", "organisation_name"]);
    signUp.mutate(values, {
      onSuccess: () => {
        void navigate({ to: "/" });
      },
    });
  }

  return (
    <AuthLayout
      title="Create your account"
      footer={
        <>
          Already have an account?{" "}
          <Link to="/sign-in" className="font-medium text-slate-900 underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" aria-label="Sign up">
        <FormError message={errorMessage(signUp.error)} />
        <Field label="Your name" name="name" autoComplete="name" />
        <Field label="Email" name="email" type="email" autoComplete="email" />
        <Field label="Password" name="password" type="password" autoComplete="new-password" minLength={MIN_PASSWORD_LENGTH} />
        <p className="-mt-2 text-sm text-slate-700">At least {MIN_PASSWORD_LENGTH} characters.</p>
        <Field label="Organisation name" name="organisation_name" autoComplete="organization" />
        <SubmitButton pending={signUp.isPending} label="Create account" pendingLabel="Creating account…" />
      </form>
    </AuthLayout>
  );
}
