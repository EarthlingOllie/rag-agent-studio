import type { ReactNode } from "react";

import { Icon } from "./Icon";
import { notice, text } from "./recipes";

/**
 * A page's title block: title, one-line description, and its actions on the right. A section
 * inside a page that already has its h1 (a Project section under the Project's header) passes
 * `level={2}`.
 */
export function PageHeader({
  title,
  description,
  actions,
  level = 1,
  headingId,
  beside,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  level?: 1 | 2;
  /** The heading's id, for a region it names. */
  headingId?: string;
  /** What sits on the title's line after it: a switcher's ▾, badges. */
  beside?: ReactNode;
}) {
  const Heading = level === 1 ? "h1" : "h2";
  const heading = (
    <Heading id={headingId} className={level === 1 ? text.title : "text-2xl font-medium tracking-[-0.01em] text-ink"}>
      {title}
    </Heading>
  );
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex min-w-0 flex-col gap-1">
        {beside === undefined ? (
          heading
        ) : (
          <div className="flex min-w-0 flex-wrap items-center gap-2.5">
            {heading}
            {beside}
          </div>
        )}
        {description !== undefined && <p className="text-[15px] text-muted">{description}</p>}
      </div>
      {actions !== undefined && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** One figure in the row of cards under a page header. */
export function StatCard({
  label,
  value,
  unit,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  /** A quieter suffix, e.g. "/ 500". */
  unit?: string;
  /** "flag" draws the value in the warning colour (flagged chunks, failures). */
  tone?: "default" | "flag";
}) {
  return (
    <div className="flex flex-col gap-1 rounded-2xl border border-line bg-surface px-5 py-4">
      <span className="text-[13px] text-muted">{label}</span>
      <span className={`font-mono text-[22px] ${tone === "flag" ? "text-flag" : "text-ink"}`}>
        {value}
        {unit !== undefined && <span className="text-sm text-muted"> {unit}</span>}
      </span>
    </div>
  );
}

/** A Tag (the knowledge-base label): sand pill. */
export function Tag({ children }: { children: ReactNode }) {
  return <span className="inline-flex rounded-full bg-sand px-2.5 py-0.5 text-xs text-sand-ink">{children}</span>;
}

const DOT = {
  ready: "bg-accent",
  working: "bg-field",
  failed: "bg-danger",
  flagged: "bg-flag",
} as const;

/** A status word with a coloured dot (Ready, Processing, Failed…). */
export function Status({ tone, children }: { tone: keyof typeof DOT; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-ink-2">
      <span aria-hidden="true" className={`size-[7px] rounded-full ${DOT[tone]}`} />
      {children}
    </span>
  );
}

/** A count that needs attention (flagged chunks), or a quiet dash when there is none. */
export function FlagCount({ count, label }: { count: number; label: string }) {
  if (count === 0) {
    return (
      <span className="text-muted" aria-label={`No ${label}`}>
        —
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 font-medium text-flag" aria-label={`${String(count)} ${label}`}>
      <Icon name="warning" size={12} />
      {count}
    </span>
  );
}

/** An inline message. Errors are announced (`role="alert"`); the rest are polite. */
export function Notice({ tone, children }: { tone: keyof typeof notice; children: ReactNode }) {
  return (
    <p role={tone === "error" ? "alert" : "status"} className={notice[tone]}>
      {children}
    </p>
  );
}

/** A collapsible settings section (the Agent configuration panel). */
export function Section({
  title,
  summary,
  defaultOpen = false,
  children,
}: {
  title: string;
  /** What is set, shown on the right while collapsed: "top-5 · hybrid 0.5". */
  summary?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  return (
    <details open={defaultOpen} className="group border-b border-line-soft">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-4 font-medium text-ink">
        <span className="flex items-center gap-2">
          <Icon name="chevronRight" size={14} className="text-muted transition-transform group-open:rotate-90" />
          {title}
        </span>
        {summary !== undefined && <span className="font-mono text-xs font-normal text-muted">{summary}</span>}
      </summary>
      <div className="flex flex-col gap-4 px-6 pb-6">{children}</div>
    </details>
  );
}
