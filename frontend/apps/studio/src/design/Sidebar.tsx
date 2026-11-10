import type { ReactNode } from "react";

import { Icon, type IconName } from "./Icon";

/**
 * A sidebar link's classes, for a router <Link>. The current link (marked `aria-current="page"`,
 * which the styling follows) has the soft accent fill the current crumb had.
 */
export const sidebarLink =
  "flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-sm text-ink-2 hover:bg-sunken hover:text-ink aria-[current=page]:bg-accent-soft aria-[current=page]:font-medium aria-[current=page]:text-accent-ink";

/** A sidebar switcher's button (the Organisation or Project switcher): the whole row is the button. */
export const sidebarSwitcher =
  "flex h-10 w-full min-w-0 items-center justify-between gap-2 rounded-lg px-2.5 text-left text-sm font-semibold text-ink hover:bg-sunken";

/**
 * The Studio's navigation beside the page: a navigation landmark named `label`, about 240 px wide,
 * that stays in place while the page scrolls. Hidden below `md`, where the breadcrumb's switchers
 * still reach every page.
 */
export function Sidebar({ label, children }: { label: string; children: ReactNode }) {
  return (
    <aside className="hidden w-60 shrink-0 border-r border-line bg-surface md:sticky md:top-0 md:block md:h-screen md:self-start md:overflow-y-auto">
      <nav aria-label={label} className="flex flex-col gap-1 px-3 py-4">
        {children}
      </nav>
    </aside>
  );
}

/** A named group of sidebar links ("Organisation sections"): a list, one link per item. */
export function SidebarGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <ul aria-label={label} className="flex flex-col gap-0.5">
      {children}
    </ul>
  );
}

/** A sidebar link's content: its icon (hidden from assistive technology) and label. */
export function SidebarLabel({ icon, children }: { icon: IconName; children: ReactNode }) {
  return (
    <>
      <Icon name={icon} className="shrink-0" />
      {children}
    </>
  );
}

/** A rule between the Organisation's links and the Project's. */
export function SidebarDivider() {
  return <hr className="my-3 border-line" />;
}

/** Plain text in the switcher's place, for something with nothing to switch to (a Member's one Organisation). */
export function SidebarTitle({ children }: { children: ReactNode }) {
  return <p className="flex h-10 items-center px-2.5 text-sm font-semibold text-ink">{children}</p>;
}
