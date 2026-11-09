import { type KeyboardEvent, type ReactNode, useRef } from "react";

import { Icon } from "./Icon";
import { button } from "./recipes";

/** The index an arrow, Home or End key moves to in a row of `count` items, wrapping; null for other keys. */
function moveIndex(key: string, index: number, count: number): number | null {
  if (key === "ArrowRight" || key === "ArrowDown") return (index + 1) % count;
  if (key === "ArrowLeft" || key === "ArrowUp") return (index - 1 + count) % count;
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  return null;
}

/**
 * A choice of a few options shown side by side (Visitors / Playground / All). It is a radio
 * group: one Tab stop on the chosen option, and the arrow keys move and choose, wrapping;
 * Home and End jump to the ends.
 */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  const group = useRef<HTMLDivElement>(null);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = options.findIndex((option) => option.value === value);
    const next = moveIndex(event.key, index, options.length);
    if (next === null) return;
    event.preventDefault();
    onChange((options[next] as { value: T }).value);
    group.current?.querySelectorAll<HTMLButtonElement>("[role=radio]")[next]?.focus();
  }

  return (
    <div
      ref={group}
      role="radiogroup"
      aria-label={label}
      onKeyDown={onKeyDown}
      className="inline-flex h-9 items-center gap-0.5 rounded-full bg-sunken p-0.5"
    >
      {options.map((option) => {
        const checked = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            onClick={() => {
              onChange(option.value);
            }}
            className={`h-8 rounded-full px-3.5 text-sm font-medium transition-colors ${
              checked ? "bg-surface text-ink shadow-[0_1px_2px_var(--ds-scrim)]" : "text-muted hover:text-ink"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/** The page numbers to show: all of up to seven, else the first, the last and the current with its neighbours. */
function pageList(page: number, pageCount: number): (number | "gap")[] {
  if (pageCount <= 7) return Array.from({ length: pageCount }, (_, index) => index + 1);
  const shown = [...new Set([1, page - 1, page, page + 1, pageCount])].filter((n) => n >= 1 && n <= pageCount).sort((a, b) => a - b);
  const list: (number | "gap")[] = [];
  shown.forEach((n, index) => {
    const previous = shown[index - 1];
    // A gap of one page shows that page; a longer gap is "…".
    if (previous !== undefined && n - previous === 2) list.push(n - 1);
    else if (previous !== undefined && n - previous > 2) list.push("gap");
    list.push(n);
  });
  return list;
}

/** Previous, the page numbers and Next, for a long list. Hidden when everything fits on one page. */
export function Pagination({
  label,
  page,
  pageCount,
  onPageChange,
}: {
  /** Names the navigation landmark: "Conversations pages". */
  label: string;
  /** The current page, from 1. */
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
}) {
  if (pageCount <= 1) return null;
  const number = "inline-flex size-9 items-center justify-center rounded-full font-mono text-[13px]";
  return (
    <nav aria-label={label} className="flex items-center justify-center gap-1">
      <button
        type="button"
        aria-label="Previous page"
        className={button.iconBare}
        disabled={page <= 1}
        onClick={() => {
          onPageChange(page - 1);
        }}
      >
        <Icon name="chevronLeft" />
      </button>
      <ul className="flex items-center gap-1">
        {pageList(page, pageCount).map((item, index) => (
          <li key={item === "gap" ? `gap-${String(index)}` : item}>
            {item === "gap" ? (
              <span className={`${number} text-muted`}>…</span>
            ) : (
              <button
                type="button"
                aria-label={`Page ${String(item)}`}
                aria-current={item === page ? "page" : undefined}
                className={`${number} ${item === page ? "bg-accent-soft font-medium text-accent-ink" : "text-ink hover:bg-sunken"}`}
                onClick={() => {
                  onPageChange(item);
                }}
              >
                {item}
              </button>
            )}
          </li>
        ))}
      </ul>
      <button
        type="button"
        aria-label="Next page"
        className={button.iconBare}
        disabled={page >= pageCount}
        onClick={() => {
          onPageChange(page + 1);
        }}
      >
        <Icon name="chevronRight" />
      </button>
    </nav>
  );
}

/**
 * The bar that appears while rows are selected: how many, the actions for them, and Clear
 * selection. It is a toolbar: the arrow keys move between its buttons (Home and End jump) and
 * Escape clears the selection.
 */
export function BulkBar({
  count,
  noun,
  onClear,
  children,
}: {
  count: number;
  /** Singular and plural: ["Agent", "Agents"]. */
  noun: readonly [string, string];
  onClear: () => void;
  /** The action buttons. */
  children: ReactNode;
}) {
  if (count === 0) return null;

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClear();
      return;
    }
    const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not([disabled])"));
    const next = moveIndex(event.key, buttons.indexOf(document.activeElement as HTMLButtonElement), buttons.length);
    if (next === null) return;
    event.preventDefault();
    buttons[next]?.focus();
  }

  return (
    <div
      role="toolbar"
      aria-label="Bulk actions"
      onKeyDown={onKeyDown}
      className="flex flex-wrap items-center gap-2 rounded-2xl border border-line bg-surface py-2 pr-2 pl-4"
    >
      <span role="status" className="mr-auto text-sm font-medium text-ink">
        {count} {count === 1 ? noun[0] : noun[1]} selected
      </span>
      {children}
      <button type="button" className={button.ghost} onClick={onClear}>
        Clear selection
      </button>
    </div>
  );
}
