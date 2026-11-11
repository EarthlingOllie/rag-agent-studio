import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { Brand, button, field, Notice, surface } from "../design";

/**
 * The frame of every page shown without the top bar (signing in, invites, the status page, and
 * the moment before the session is known): a centred panel on the canvas with the wave mark.
 * `home` makes the mark a link to the Studio; `wide` is for content wider than a form.
 */
export function SignedOutFrame({
  children,
  footer,
  home = false,
  wide = false,
}: {
  children: ReactNode;
  footer?: ReactNode;
  home?: boolean;
  wide?: boolean;
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-canvas px-4 py-10 text-ink">
      <main className={`w-full ${wide ? "max-w-xl" : "max-w-sm"} ${surface.panel} p-8`}>
        {home ? (
          <Link to="/" aria-label="Studio home" className="inline-flex rounded-md">
            <Brand />
          </Link>
        ) : (
          <Brand />
        )}
        <div className="mt-6">{children}</div>
      </main>
      {footer !== undefined && <footer className="mt-6 text-sm">{footer}</footer>}
    </div>
  );
}

/** A link inside the signed-out panels: accent and always underlined, so it never relies on colour. */
export const PANEL_LINK = "font-medium text-accent underline underline-offset-4 hover:text-accent-hover";

/** An error under a form's heading, as an error `Notice`; nothing while there is none. */
export function ErrorNotice({ message }: { message: string | undefined }) {
  if (message === undefined) return null;
  return <Notice tone="error">{message}</Notice>;
}

/** The frame around the signed-out screens: a centred panel with the mark, the title and the form. */
export function AuthLayout({ title, children, footer }: { title: string; children: ReactNode; footer: ReactNode }) {
  return (
    <SignedOutFrame
      footer={
        <Link to="/status" className="text-muted underline underline-offset-4 hover:text-ink">
          System status
        </Link>
      }
    >
      <h1 className="text-2xl font-medium tracking-[-0.01em] text-ink">{title}</h1>
      <div className="mt-6">{children}</div>
      <p className="mt-6 text-sm text-muted">{footer}</p>
    </SignedOutFrame>
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
      <label htmlFor={name} className={field.label}>
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
        className={field.input}
      />
    </div>
  );
}

/**
 * The old name of `ErrorNotice`, kept for the pages that later design tickets restyle (they
 * switch to `ErrorNotice` or `Notice` as they go). It renders the same error `Notice`.
 */
export const FormError = ErrorNotice;

export function SubmitButton({ pending, label, pendingLabel }: { pending: boolean; label: string; pendingLabel: string }) {
  return (
    <button type="submit" disabled={pending} className={`${button.primary} w-full`}>
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
