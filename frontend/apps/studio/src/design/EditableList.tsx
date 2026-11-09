import { useEffect, useId, useRef, useState } from "react";

import { Notice } from "./content";
import { Icon } from "./Icon";
import { button, field, text } from "./recipes";

/**
 * A short list of values the Member edits in place (Allowed Origins). Type and press Enter (or
 * Add) to add; blanks and duplicates are refused, and `validate` can refuse more, with the
 * reason under the input. Escape clears the input. Each item has a Remove button; after a
 * removal focus moves to the next item's, the previous one's, or back to the input.
 */
export function EditableList({
  label,
  inputLabel,
  placeholder,
  items,
  onChange,
  validate,
  emptyWarning,
}: {
  label: string;
  inputLabel: string;
  placeholder?: string;
  items: readonly string[];
  onChange: (items: string[]) => void;
  /** Why a value can't be added, or undefined if it can. */
  validate?: (value: string) => string | undefined;
  /** Shown while the list is empty, when an empty list has a consequence. */
  emptyWarning?: string;
}) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | undefined>(undefined);
  /** The index of the item just removed, until the new list renders and focus can move. */
  const removedAt = useRef<number | null>(null);
  const errorId = useId();
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (removedAt.current === null) return;
    const removes = (list.current as HTMLUListElement).querySelectorAll<HTMLButtonElement>("button");
    const target = removes[Math.min(removedAt.current, removes.length - 1)];
    (target ?? input.current)?.focus();
    removedAt.current = null;
  }, [items]);

  function add() {
    const value = draft.trim();
    if (value === "") return;
    const problem = items.includes(value) ? "Already in the list." : validate?.(value);
    if (problem !== undefined) {
      setError(problem);
      return;
    }
    onChange([...items, value]);
    setDraft("");
    input.current?.focus();
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className={field.label}>{label}</h3>
      <ul ref={list} aria-label={label} className="flex flex-col divide-y divide-line-soft rounded-xl border border-line empty:hidden">
        {items.map((item, index) => (
          <li key={item} className="flex items-center justify-between gap-3 py-1.5 pr-1.5 pl-3.5">
            <span className={`${text.mono} break-all text-ink`}>{item}</span>
            <button
              type="button"
              aria-label={`Remove ${item}`}
              className={button.iconBare}
              onClick={() => {
                onChange(items.filter((other) => other !== item));
                removedAt.current = index;
              }}
            >
              <Icon name="close" size={14} />
            </button>
          </li>
        ))}
      </ul>
      {items.length === 0 && emptyWarning !== undefined && <Notice tone="warning">{emptyWarning}</Notice>}
      {/* Not a <form>: the list usually sits inside a page's settings form. */}
      <div className="flex items-start gap-2">
        <div className="flex-1">
          <input
            ref={input}
            aria-label={inputLabel}
            placeholder={placeholder}
            value={draft}
            aria-invalid={error !== undefined}
            aria-describedby={error === undefined ? undefined : errorId}
            className={`${field.inputMono} mt-0`}
            onChange={(event) => {
              setDraft(event.target.value);
              setError(undefined);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                add();
              } else if (event.key === "Escape") {
                setDraft("");
                setError(undefined);
              }
            }}
          />
          {error !== undefined && (
            <p id={errorId} className={field.error}>
              {error}
            </p>
          )}
        </div>
        <button type="button" className={`${button.secondary} h-10`} onClick={add}>
          <Icon name="plus" size={14} />
          Add
        </button>
      </div>
    </div>
  );
}
