import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

/** The frame around the signed-out screens: a centred card with the product name. */
export function AuthLayout({ title, children, footer }: { title: string; children: ReactNode; footer: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-4 text-slate-900">
      <main className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold text-slate-700">RAG Agent Studio</p>
        <h1 className="mt-2 text-2xl font-semibold">{title}</h1>
        <div className="mt-6">{children}</div>
        <p className="mt-6 text-sm text-slate-700">{footer}</p>
      </main>
      <footer className="mt-6 text-sm">
        <Link to="/status" className="text-slate-700 underline">
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
  defaultValue,
}: {
  label: string;
  name: string;
  type?: string;
  autoComplete: string;
  minLength?: number;
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
        {...(defaultValue === undefined ? {} : { defaultValue })}
        className="mt-1 block w-full rounded border border-slate-400 px-3 py-2 focus:outline-2 focus:outline-slate-900"
      />
    </div>
  );
}

export function FormError({ message }: { message: string | undefined }) {
  if (message === undefined) return null;
  return (
    <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
      {message}
    </p>
  );
}

export function SubmitButton({ pending, label, pendingLabel }: { pending: boolean; label: string; pendingLabel: string }) {
  return (
    <button
      type="submit"
      disabled={pending}
      className="w-full rounded bg-slate-900 px-4 py-2 font-medium text-white hover:bg-slate-700 disabled:bg-slate-600"
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
