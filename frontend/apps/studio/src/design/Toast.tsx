import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { Icon } from "./Icon";
import { button } from "./recipes";

/** How long a toast stays up. Long enough to read it and reach Undo. */
export const TOAST_DURATION_MS = 8000;

interface ToastOptions {
  /** Offer Undo: called once if the Member presses it before the toast goes. */
  onUndo?: () => void;
}

interface Toast extends ToastOptions {
  id: number;
  message: string;
}

const ToastContext = createContext<{ show: (message: string, options?: ToastOptions) => void } | null>(null);

/**
 * Hosts the Studio's toasts: a short confirmation after a change ("Archived HR helper."), with
 * Undo where the action allows it. One at a time; a new toast replaces the last. The message is
 * read out by a polite live region that is in the page before any toast, so screen readers hear
 * every one; Undo and Dismiss sit beside it.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);
  const show = useCallback((message: string, options: ToastOptions = {}) => {
    setToast((last) => ({ id: (last?.id ?? 0) + 1, message, ...options }));
  }, []);
  const value = useMemo(() => ({ show }), [show]);

  useEffect(() => {
    if (toast === null) return;
    const timer = setTimeout(() => {
      setToast(null);
    }, TOAST_DURATION_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className={`fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 ${
          toast === null ? "" : "rounded-full bg-ink py-1.5 pr-1.5 pl-5 text-sm text-surface shadow-[0_12px_32px_var(--ds-scrim)]"
        }`}
      >
        <div role="status" aria-live="polite">
          {toast?.message}
        </div>
        {toast !== null && (
          <span className="flex items-center gap-1">
            {toast.onUndo !== undefined && (
              <button
                type="button"
                className="h-8 rounded-full px-3 font-medium text-surface hover:bg-ink-2"
                onClick={() => {
                  toast.onUndo?.();
                  setToast(null);
                }}
              >
                Undo
              </button>
            )}
            <button
              type="button"
              aria-label="Dismiss"
              className={`${button.iconBare} text-surface hover:bg-ink-2 hover:text-surface`}
              onClick={() => {
                setToast(null);
              }}
            >
              <Icon name="close" size={14} />
            </button>
          </span>
        )}
      </div>
    </ToastContext.Provider>
  );
}

/** Shows a toast: `useToast().show("Published v3.", { onUndo })`. Needs a ToastProvider above. */
export function useToast() {
  const context = useContext(ToastContext);
  if (context === null) throw new Error("useToast needs a ToastProvider");
  return context;
}
