import type { ReactNode } from "react";

import { useAppearance } from "./appearance";
import { Icon, WaveMark } from "./Icon";
import { button } from "./recipes";

/**
 * The Studio's one navigation bar: on a narrow screen the button that opens the sidebar drawer,
 * the mark, the breadcrumb, then page actions and the Member's controls on the right.
 */
export function TopBar({
  menu,
  home,
  breadcrumb,
  actions,
}: {
  /** The sidebar drawer's button (`SidebarButton`), before the mark. */
  menu?: ReactNode;
  /** The mark and product name, usually wrapped in a router <Link> to "/". */
  home: ReactNode;
  breadcrumb?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="border-b border-line bg-surface">
      {/* The mark and breadcrumb share one row, the breadcrumb cut short before it wraps; the
          actions join that row while it has room (12rem for the path) and drop under it otherwise. */}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3 sm:gap-x-6 sm:px-8">
        <div className="flex min-w-0 grow basis-48 items-center gap-x-3 md:gap-x-5">
          <div className="flex shrink-0 items-center gap-2">
            {menu}
            {home}
          </div>
          {breadcrumb}
        </div>
        <div className="flex items-center gap-3">{actions}</div>
      </div>
    </header>
  );
}

/**
 * The mark and product name for `TopBar`'s `home`. `compact` shows only the mark below `md`, leaving
 * the top bar's row to the breadcrumb; give it only where something else names the Studio (the
 * top bar's home link is named "Studio home").
 */
export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2 font-semibold text-ink">
      <WaveMark />
      <span className={compact ? "hidden md:inline" : undefined}>Studio</span>
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
