import { Link, useNavigate } from "@tanstack/react-router";
import type { SubmitEvent } from "react";

import { AuthLayout, Field, FormError, formValues, SubmitButton } from "./AuthLayout";
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

function errorMessage(error: Error | null): string | undefined {
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
      onSuccess: () => {
        void navigate({ to: "/" });
      },
    });
  }

  return (
    <AuthLayout
      title="Sign in"
      footer={
        <>
          New to RAG Agent Studio?{" "}
          <Link to="/sign-up" className="font-medium text-slate-900 underline">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" aria-label="Sign in">
        <FormError message={errorMessage(signIn.error)} />
        <Field label="Email" name="email" type="email" autoComplete="email" />
        <Field label="Password" name="password" type="password" autoComplete="current-password" />
        <SubmitButton pending={signIn.isPending} label="Sign in" pendingLabel="Signing in…" />
      </form>
    </AuthLayout>
  );
}
