import { createContext, type ReactNode, useContext } from "react";
import { createPortal } from "react-dom";

/** Where a page's top bar actions go: the slot the Organisation shell renders in its top bar. */
export const TopBarSlot = createContext<HTMLElement | null>(null);

/**
 * A page's own actions in the top bar's right side (the Agent's Saved state, History and Publish),
 * rendered there through a portal. Outside the shell, or before the slot is in the page, nothing
 * is shown.
 */
export function TopBarActions({ children }: { children: ReactNode }) {
  const slot = useContext(TopBarSlot);
  return slot === null ? null : createPortal(children, slot);
}
