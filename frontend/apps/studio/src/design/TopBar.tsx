import type { ReactNode } from "react";

import { useAppearance } from "./appearance";
import { Icon, WaveMark } from "./Icon";
import { button } from "./recipes";

/**
 * The Studio's one navigation bar: the mark, the breadcrumb (which carries every level of
 * navigation, sections included), then page actions and the Member's controls on the right.
 */
export function TopBar({
  home,
  breadcrumb,
  actions,
}: {
  /** The mark and product name, usually wrapped in a router <Link> to "/". */
  home: ReactNode;
  breadcrumb?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="border-b border-line bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3 sm:px-8">
        <div className="flex min-w-0 flex-wrap items-center gap-x-5 gap-y-2">
          {home}
          {breadcrumb}
        </div>
        <div className="flex items-center gap-3">{actions}</div>
      </div>
    </header>
  );
}

/** The mark and product name for `TopBar`'s `home`. */
export function Brand() {
  return (
    <span className="flex items-center gap-2 font-semibold text-ink">
      <WaveMark />
      Studio
    </span>
  );
}

/** Switches between the light and dark Appearance. */
export function AppearanceToggle() {
  const { resolved, setAppearance } = useAppearance();
  const next = resolved === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      aria-label={`Switch to ${next} mode`}
      className={button.icon}
      onClick={() => {
        setAppearance(next);
      }}
    >
      <Icon name={resolved === "dark" ? "sun" : "moon"} />
    </button>
  );
}

/** The Member's initials in a circle; the accessible name is their full name. */
export function Avatar({ name }: { name: string }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");
  return (
    <span
      role="img"
      aria-label={name}
      className="grid size-8 shrink-0 place-items-center rounded-full bg-sunken text-xs font-semibold text-ink"
    >
      {initials}
    </span>
  );
}
