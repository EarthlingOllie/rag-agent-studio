import type { ReactNode } from "react";

import { Icon, type IconName } from "./Icon";
import { text } from "./recipes";

/**
 * What a page or card shows when it has nothing to list, or could not load: what is (not) here,
 * and what to do next. `tone="error"` announces it as an alert.
 */
export function EmptyState({
  title,
  description,
  action,
  icon,
  tone = "empty",
}: {
  title: string;
  description?: ReactNode;
  /** The next step, usually the page's primary button. */
  action?: ReactNode;
  icon?: IconName;
  tone?: "empty" | "error";
}) {
  return (
    <div
      role={tone === "error" ? "alert" : undefined}
      className="flex flex-col items-center gap-2 rounded-2xl border border-line bg-surface px-6 py-12 text-center"
    >
      {icon !== undefined && (
        <span className="mb-1 flex size-10 items-center justify-center rounded-full bg-sunken text-muted">
          <Icon name={icon} size={20} />
        </span>
      )}
      <h2 className={tone === "error" ? "text-base font-semibold text-danger" : text.subheading}>{title}</h2>
      {description !== undefined && <p className="max-w-md text-sm text-muted">{description}</p>}
      {action !== undefined && <div className="mt-3">{action}</div>}
    </div>
  );
}

const WIDTHS = ["w-3/4", "w-full", "w-5/6", "w-2/3"];

/** Grey bars where content is loading. Announced once as "Loading…", with the bars hidden. */
export function Skeleton({ label = "Loading", lines = 3 }: { label?: string; lines?: number }) {
  return (
    <div role="status" aria-label={label} aria-busy="true" className="flex flex-col gap-3">
      {Array.from({ length: lines }, (_, index) => (
        <span
          key={index}
          data-skeleton-line
          aria-hidden="true"
          className={`h-3.5 animate-pulse rounded-full bg-sunken ${WIDTHS[index % WIDTHS.length] as string}`}
        />
      ))}
    </div>
  );
}
