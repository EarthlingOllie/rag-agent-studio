import { useCallback, useSyncExternalStore } from "react";

/**
 * The Studio's Appearance: light, dark, or following the system. This is the Member's own setting
 * for the Studio and has nothing to do with an Organisation's widget Theme or Theme Mode.
 */
export type Appearance = "light" | "dark" | "system";

export const APPEARANCE_KEY = "studio.appearance";
const DARK_QUERY = "(prefers-color-scheme: dark)";

const listeners = new Set<() => void>();

function stored(): Appearance {
  try {
    const value = window.localStorage.getItem(APPEARANCE_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(DARK_QUERY).matches;
}

/** Puts an Appearance on <html>: tokens.css reads `data-appearance`; "system" removes it. */
export function applyAppearance(appearance: Appearance): void {
  const root = document.documentElement;
  if (appearance === "system") delete root.dataset.appearance;
  else root.dataset.appearance = appearance;
}

/** Call once before the first render so the page doesn't flash the other Appearance. */
export function initAppearance(): void {
  applyAppearance(stored());
}

/** Remembers and applies a choice, and tells every `useAppearance` about it. */
export function setAppearance(appearance: Appearance): void {
  try {
    if (appearance === "system") window.localStorage.removeItem(APPEARANCE_KEY);
    else window.localStorage.setItem(APPEARANCE_KEY, appearance);
  } catch {
    // Storage can be unavailable (private windows); the choice still applies to this page.
  }
  applyAppearance(appearance);
  current = appearance;
  listeners.forEach((listener) => {
    listener();
  });
}

let current: Appearance | undefined;

function snapshot(): Appearance {
  current ??= stored();
  return current;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const media = typeof window.matchMedia === "function" ? window.matchMedia(DARK_QUERY) : undefined;
  media?.addEventListener("change", listener);
  return () => {
    listeners.delete(listener);
    media?.removeEventListener("change", listener);
  };
}

/** Forgets the cached choice (tests). */
export function resetAppearanceForTests(): void {
  current = undefined;
}

/**
 * The Member's Appearance, what it resolves to now, and a setter. `resolved` is what is on
 * screen: "system" resolves through the browser's colour-scheme preference.
 */
export function useAppearance(): {
  appearance: Appearance;
  resolved: "light" | "dark";
  setAppearance: (appearance: Appearance) => void;
} {
  const appearance = useSyncExternalStore(subscribe, snapshot);
  const prefersDark = useSyncExternalStore(subscribe, systemPrefersDark);
  const resolved = appearance === "system" ? (prefersDark ? "dark" : "light") : appearance;
  const set = useCallback((next: Appearance) => {
    setAppearance(next);
  }, []);
  return { appearance, resolved, setAppearance: set };
}
