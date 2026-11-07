/**
 * The widget's UI primitives. They read the Theme only through the CSS custom properties that
 * `resolveTheme` produces, so the Studio's preview and the embedded widget render the same
 * components with the same Theme.
 */
import type { CSSProperties, ReactNode } from "react";

import { type ColourScheme, resolveTheme, type Theme } from "./theme";

const FONT = "var(--theme-font-family)";
const RADIUS = "var(--theme-radius)";

/** Applies the Theme's custom properties for one colour scheme to everything inside it. */
export function ThemeScope({
  theme,
  scheme,
  label,
  children,
  style,
}: {
  theme: Theme;
  scheme: ColourScheme;
  label: string;
  children: ReactNode;
  style?: CSSProperties;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      data-scheme={scheme}
      style={{ ...(resolveTheme(theme, scheme) as CSSProperties), colorScheme: scheme, fontFamily: FONT, ...style }}
    >
      {children}
    </div>
  );
}

const HEADER_IMAGE = { width: 28, height: 28, flex: "none" } as const;

/**
 * The chat panel: a header with the Agent's avatar (or initial), name, the Theme's logo and any
 * `actions` (such as a close button), then the Messages and the Composer. With `logLabel` the
 * Messages are a `log`, so new ones are announced; `className` lets the widget lay it out.
 */
export function ChatWindow({
  agentName,
  children,
  composer,
  logoUrl,
  avatarUrl,
  actions,
  logLabel,
  className,
}: {
  agentName: string;
  children: ReactNode;
  composer: ReactNode;
  logoUrl?: string | null | undefined;
  avatarUrl?: string | null | undefined;
  actions?: ReactNode;
  logLabel?: string;
  className?: string;
}) {
  return (
    <section
      aria-label={`Chat with ${agentName}`}
      className={className}
      style={{
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        background: "var(--theme-surface)",
        color: "var(--theme-on-surface)",
        borderRadius: RADIUS,
        border: "1px solid color-mix(in srgb, var(--theme-on-surface) 15%, transparent)",
        boxShadow: "0 8px 24px rgb(0 0 0 / 0.15)",
        fontFamily: FONT,
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "10px 14px",
          background: "var(--theme-primary)",
          color: "var(--theme-on-primary)",
          fontWeight: 600,
        }}
      >
        {avatarUrl ? (
          <img src={avatarUrl} alt={`${agentName}'s avatar`} style={{ ...HEADER_IMAGE, borderRadius: "50%", objectFit: "cover" }} />
        ) : (
          <span
            aria-hidden="true"
            style={{
              display: "inline-flex",
              width: 28,
              height: 28,
              alignItems: "center",
              justifyContent: "center",
              borderRadius: "50%",
              border: "2px solid var(--theme-on-primary)",
              fontSize: 13,
            }}
          >
            {agentName.slice(0, 1)}
          </span>
        )}
        <h3 style={{ margin: 0, fontSize: 15, flex: 1 }}>{agentName}</h3>
        {logoUrl && <img src={logoUrl} alt="Logo" style={{ height: 28, maxWidth: 96, objectFit: "contain" }} />}
        {actions}
      </header>
      <ol
        role={logLabel ? "log" : undefined}
        aria-label={logLabel}
        style={{
          listStyle: "none",
          margin: 0,
          padding: 14,
          display: "flex",
          flexDirection: "column",
          gap: 8,
          flex: "1 1 auto",
          minHeight: 0,
          overflowY: "auto",
        }}
      >
        {children}
      </ol>
      {composer}
    </section>
  );
}

/** One Message: the Agent's on the surface, the Visitor's in the primary colour. */
export function MessageBubble({ from, children, label }: { from: "agent" | "visitor"; children: ReactNode; label?: string }) {
  const visitor = from === "visitor";
  return (
    <li
      data-from={from}
      aria-label={label}
      style={{
        alignSelf: visitor ? "flex-end" : "flex-start",
        maxWidth: "85%",
        padding: "8px 12px",
        borderRadius: RADIUS,
        background: visitor ? "var(--theme-primary)" : "color-mix(in srgb, var(--theme-on-surface) 6%, var(--theme-surface))",
        color: visitor ? "var(--theme-on-primary)" : "var(--theme-on-surface)",
        fontSize: 14,
        lineHeight: 1.4,
      }}
    >
      {children}
    </li>
  );
}

/** Secondary text, such as a citation or a timestamp. */
export function MutedText({ children }: { children: ReactNode }) {
  return <span style={{ display: "block", marginTop: 4, color: "var(--theme-muted)", fontSize: 12 }}>{children}</span>;
}

/** A link in the accent colour, such as a citation. */
export function AccentLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} style={{ color: "var(--theme-accent)", textDecoration: "underline" }}>
      {children}
    </a>
  );
}

/**
 * The message box and Send button; sending passes the typed Message on and clears the box.
 * `sendLabel` replaces the button's "Send" (a UI text override); `disabled` holds the button.
 */
export function Composer({
  onSend,
  sendLabel = "Send",
  disabled = false,
}: {
  onSend: (message: string) => void;
  sendLabel?: string;
  disabled?: boolean;
}) {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        const input = event.currentTarget.elements.namedItem("message") as HTMLInputElement;
        onSend(input.value);
        input.value = "";
      }}
      style={{
        display: "flex",
        gap: 8,
        padding: 10,
        borderTop: "1px solid color-mix(in srgb, var(--theme-on-surface) 15%, transparent)",
      }}
    >
      <input
        name="message"
        aria-label="Message"
        placeholder="Ask a question"
        style={{
          flex: 1,
          minWidth: 0,
          padding: "8px 10px",
          borderRadius: RADIUS,
          border: "1px solid var(--theme-muted)",
          background: "var(--theme-surface)",
          color: "var(--theme-on-surface)",
          font: "inherit",
          fontSize: 14,
          outlineColor: "var(--theme-accent)",
        }}
      />
      <button
        type="submit"
        disabled={disabled}
        style={{
          padding: "8px 14px",
          borderRadius: RADIUS,
          border: "none",
          background: "var(--theme-primary)",
          color: "var(--theme-on-primary)",
          font: "inherit",
          fontSize: 14,
          fontWeight: 600,
          outlineColor: "var(--theme-accent)",
        }}
      >
        {sendLabel}
      </button>
    </form>
  );
}

/** The floating bubble that opens and closes the chat, in a bottom corner. */
export function Launcher({
  open,
  position,
  onToggle,
}: {
  open: boolean;
  position: Theme["launcher_position"];
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={open ? "Close chat" : "Open chat"}
      aria-expanded={open}
      data-position={position}
      onClick={onToggle}
      style={{
        position: "absolute",
        bottom: 16,
        [position === "bottom-left" ? "left" : "right"]: 16,
        width: 52,
        height: 52,
        borderRadius: "50%",
        border: "none",
        background: "var(--theme-primary)",
        color: "var(--theme-on-primary)",
        boxShadow: "0 4px 12px rgb(0 0 0 / 0.25)",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        outlineColor: "var(--theme-accent)",
      }}
    >
      <svg aria-hidden="true" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 5h16v11H9l-5 4z" strokeLinejoin="round" />}
      </svg>
    </button>
  );
}
