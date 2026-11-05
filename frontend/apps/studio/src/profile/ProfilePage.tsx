import type { SubmitEvent } from "react";

import { Field, FormError, formValues, SubmitButton } from "../auth/AuthLayout";
import { AuthRequestError, type Session, useChangePassword, useMe, useUpdateProfile } from "../auth/session";
import { MIN_PASSWORD_LENGTH } from "../auth/SignUpPage";

function Saved({ children }: { children: string }) {
  return (
    <p role="status" className="rounded border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-900">
      {children}
    </p>
  );
}

function failure(error: Error | null, messages: Partial<Record<number, string>>): string | undefined {
  if (error === null) return undefined;
  const status = error instanceof AuthRequestError ? error.status : 0;
  return messages[status] ?? "Something went wrong. Try again.";
}

function NameForm({ name }: { name: string }) {
  const updateProfile = useUpdateProfile();

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    updateProfile.mutate(formValues(event.currentTarget, ["name"]));
  }

  return (
    <form onSubmit={onSubmit} aria-label="Your name" className="max-w-sm space-y-4">
      <h2 className="text-lg font-semibold">Your name</h2>
      {updateProfile.isSuccess && <Saved>Name saved.</Saved>}
      <FormError message={failure(updateProfile.error, { 422: "Enter a name of up to 200 characters." })} />
      <Field label="Name" name="name" autoComplete="name" defaultValue={name} />
      <SubmitButton pending={updateProfile.isPending} label="Save name" pendingLabel="Saving…" />
    </form>
  );
}

function PasswordForm() {
  const changePassword = useChangePassword();

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    changePassword.mutate(formValues(form, ["current_password", "new_password"]), {
      onSuccess: () => {
        form.reset();
      },
    });
  }

  return (
    <form onSubmit={onSubmit} aria-label="Change password" className="max-w-sm space-y-4">
      <h2 className="text-lg font-semibold">Change password</h2>
      {changePassword.isSuccess && <Saved>Password changed. Your other sessions have been signed out.</Saved>}
      <FormError
        message={failure(changePassword.error, {
          400: "Current password is incorrect.",
          422: `Choose a new password of at least ${String(MIN_PASSWORD_LENGTH)} characters.`,
        })}
      />
      <Field label="Current password" name="current_password" type="password" autoComplete="current-password" />
      <Field
        label="New password"
        name="new_password"
        type="password"
        autoComplete="new-password"
        minLength={MIN_PASSWORD_LENGTH}
      />
      <p className="-mt-2 text-sm text-slate-700">At least {MIN_PASSWORD_LENGTH} characters.</p>
      <SubmitButton pending={changePassword.isPending} label="Change password" pendingLabel="Changing password…" />
    </form>
  );
}

/** The signed-in Member's own details: their name and password. */
export function ProfilePage() {
  const { data } = useMe();
  const { member } = data as Session;
  return (
    <section aria-labelledby="page-heading" className="space-y-8">
      <div>
        <h1 id="page-heading" className="text-2xl font-semibold">
          Profile
        </h1>
        <p className="mt-2 text-slate-700">
          Signed in as <span className="font-medium">{member.email}</span>
        </p>
      </div>
      <NameForm name={member.name} />
      <PasswordForm />
    </section>
  );
}
