import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

/** The frame around the signed-out screens: a centred card with the product name. */
export function AuthLayout({ title, children, footer }: { title: string; children: ReactNode; footer: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-canvas px-4 text-ink">
      <main className="w-full max-w-sm rounded-lg border border-line bg-surface p-8 shadow-sm">
        <p className="text-sm font-semibold text-ink-2">RAG Agent Studio</p>
        <h1 className="mt-2 text-2xl font-semibold">{title}</h1>
        <div className="mt-6">{children}</div>
        <p className="mt-6 text-sm text-muted">{footer}</p>
      </main>
      <footer className="mt-6 text-sm">
        <Link to="/status" className="text-muted underline">
          System status
        </Link>
      </footer>
    </div>
  );
}

export function Field({
  label,
  name,
  type = "text",
  autoComplete,
  minLength,
  inputMode,
  defaultValue,
}: {
  label: string;
  name: string;
  type?: string;
  autoComplete: string;
  minLength?: number;
  inputMode?: "numeric";
  defaultValue?: string;
}) {
  return (
    <div>
      <label htmlFor={name} className="block text-sm font-medium">
        {label}
      </label>
      <input
        id={name}
        name={name}
        type={type}
        autoComplete={autoComplete}
        required
        {...(minLength === undefined ? {} : { minLength })}
        {...(inputMode === undefined ? {} : { inputMode })}
        {...(defaultValue === undefined ? {} : { defaultValue })}
        className="mt-1 block w-full rounded border border-field px-3 py-2 focus:outline-2 focus:outline-accent"
      />
    </div>
  );
}

export function FormError({ message }: { message: string | undefined }) {
  if (message === undefined) return null;
  return (
    <p role="alert" className="rounded border border-danger-soft bg-danger-soft px-3 py-2 text-sm text-danger">
      {message}
    </p>
  );
}

export function SubmitButton({ pending, label, pendingLabel }: { pending: boolean; label: string; pendingLabel: string }) {
  return (
    <button
      type="submit"
      disabled={pending}
      className="w-full rounded bg-accent px-4 py-2 font-medium text-on-accent hover:bg-accent-hover disabled:bg-muted"
    >
      {pending ? pendingLabel : label}
    </button>
  );
}

/** Reads a submitted form's named text fields. */
export function formValues<Name extends string>(form: HTMLFormElement, names: readonly Name[]): Record<Name, string> {
  const data = new FormData(form);
  // Every field these forms read is a text input, so its entry is a string.
  return Object.fromEntries(names.map((name) => [name, data.get(name) as string])) as Record<Name, string>;
}
