import { type KeyboardEvent, type ReactNode, useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

import { Icon } from "./Icon";
import { button, text } from "./recipes";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface DialogProps {
  open: boolean;
  title: string;
  /** One or two sentences under the title; it becomes the dialog's accessible description. */
  description?: ReactNode;
  onClose: () => void;
  children?: ReactNode;
  /** The buttons along the bottom, primary last. */
  footer?: ReactNode;
  /** `alertdialog` for a destructive confirmation: it is not dismissed by a click outside. */
  role?: "dialog" | "alertdialog";
  /** The ✕ in the corner. ConfirmDialog leaves it out: its Cancel does the same. */
  closeButton?: boolean;
}

/**
 * A modal dialog. It takes focus when it opens (its first control, or itself), keeps Tab and
 * Shift+Tab inside, closes on Escape, on its ✕ or on a click outside (not an `alertdialog`), and
 * returns focus to whatever opened it.
 */
export function Dialog(props: DialogProps) {
  if (!props.open) return null;
  return createPortal(<DialogPanel {...props} />, document.body);
}

function DialogPanel({ title, description, onClose, children, footer, role = "dialog", closeButton = true }: DialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const first = panel.current?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? panel.current)?.focus();
    return () => {
      opener?.focus();
    };
  }, []);

  // Escape also closes the top dialog when focus has fallen out of it to the page, as it does when
  // the focused button is disabled while its request runs. Escape inside a dialog is handled below.
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  });
  useEffect(() => {
    function onDocumentKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      const modals = document.querySelectorAll('[aria-modal="true"]');
      if (modals[modals.length - 1] !== panel.current) return;
      event.preventDefault();
      close.current();
    }
    document.addEventListener("keydown", onDocumentKeyDown);
    return () => {
      document.removeEventListener("keydown", onDocumentKeyDown);
    };
  }, []);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(FOCUSABLE));
    event.preventDefault();
    const index = focusable.indexOf(document.activeElement as HTMLElement);
    const next = event.shiftKey ? (index <= 0 ? focusable.length - 1 : index - 1) : (index + 1) % focusable.length;
    focusable[next]?.focus();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        data-testid="dialog-scrim"
        aria-hidden="true"
        className="absolute inset-0 bg-scrim"
        // Focus stays in the dialog, so Escape and Tab keep working after a click outside it.
        onMouseDown={(event) => {
          event.preventDefault();
        }}
        onClick={role === "dialog" ? onClose : undefined}
      />
      <div
        ref={panel}
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description === undefined ? undefined : descriptionId}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        className="relative flex max-h-[calc(100vh-2rem)] w-full max-w-lg flex-col gap-4 overflow-y-auto rounded-2xl border border-line bg-surface p-6 shadow-[0_12px_32px_var(--ds-scrim)] focus:outline-none"
      >
        <div className="flex items-start justify-between gap-4">
          <h2 id={titleId} className={text.heading}>
            {title}
          </h2>
          {closeButton && (
            <button type="button" aria-label="Close" className={button.iconBare} onClick={onClose}>
              <Icon name="close" />
            </button>
          )}
        </div>
        {description !== undefined && (
          <p id={descriptionId} className="text-[15px] text-ink-2">
            {description}
          </p>
        )}
        {children}
        {footer !== undefined && <div className="flex flex-wrap justify-end gap-2 pt-2">{footer}</div>}
      </div>
    </div>
  );
}

/**
 * Asks before an action happens. A destructive one (Delete, Archive) is an `alertdialog` with a
 * filled danger button; focus starts on Cancel so Enter never destroys anything by accident.
 * The children say what will happen: name the thing and the consequence.
 */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel = "Cancel",
  destructive = false,
  busy = false,
  body,
  confirmDisabled = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  destructive?: boolean;
  /** The confirmed action is running: both buttons wait. */
  busy?: boolean;
  /**
   * What the confirmation asks for beyond a click, under the description: typing a name to delete
   * something for good, or why the action was refused. It comes before the buttons, so its first
   * field takes focus.
   */
  body?: ReactNode;
  /** The confirmation isn't ready yet, e.g. the name isn't typed exactly. Cancel still works. */
  confirmDisabled?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Dialog
      open={open}
      title={title}
      description={children}
      onClose={onCancel}
      role={destructive ? "alertdialog" : "dialog"}
      closeButton={false}
      footer={
        <>
          <button type="button" className={button.secondary} disabled={busy} onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className={destructive ? button.dangerFilled : button.primary}
            disabled={busy || confirmDisabled}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </>
      }
    >
      {body}
    </Dialog>
  );
}
