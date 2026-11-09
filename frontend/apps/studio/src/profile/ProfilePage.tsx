import type { SubmitEvent } from "react";

import { ErrorNotice, Field, formValues } from "../auth/AuthLayout";
import { AuthRequestError, type Session, useChangePassword, useMe, useUpdateProfile } from "../auth/session";
import { MIN_PASSWORD_LENGTH } from "../auth/SignUpPage";
import { button, layout, Notice, PageHeader, surface, text } from "../design";

function Submit({ pending, label, pendingLabel }: { pending: boolean; label: string; pendingLabel: string }) {
  return (
    <button type="submit" disabled={pending} className={`${button.primary} self-start`}>
      {pending ? pendingLabel : label}
    </button>
  );
}

const FORM = `${surface.panel} flex max-w-xl flex-col gap-4`;

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
    <form onSubmit={onSubmit} aria-label="Your name" className={FORM}>
      <h2 className={text.subheading}>Your name</h2>
      {updateProfile.isSuccess && <Notice tone="success">Name saved.</Notice>}
      <ErrorNotice message={failure(updateProfile.error, { 422: "Enter a name of up to 200 characters." })} />
      <Field label="Name" name="name" autoComplete="name" defaultValue={name} />
      <Submit pending={updateProfile.isPending} label="Save name" pendingLabel="Saving…" />
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
    <form onSubmit={onSubmit} aria-label="Change password" className={FORM}>
      <h2 className={text.subheading}>Change password</h2>
      {changePassword.isSuccess && <Notice tone="success">Password changed. Your other sessions have been signed out.</Notice>}
      <ErrorNotice
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
      <p className="-mt-2 text-xs text-muted">At least {MIN_PASSWORD_LENGTH} characters.</p>
      <Submit pending={changePassword.isPending} label="Change password" pendingLabel="Changing password…" />
    </form>
  );
}

/** The signed-in Member's own details: their name and password. */
export function ProfilePage() {
  const { data } = useMe();
  const { member } = data as Session;
  return (
    <div className={layout.stack}>
      <PageHeader
        title="Profile"
        description={
          <>
            Signed in as <span className="font-medium text-ink">{member.email}</span>
          </>
        }
      />
      <NameForm name={member.name} />
      <PasswordForm />
    </div>
  );
}
