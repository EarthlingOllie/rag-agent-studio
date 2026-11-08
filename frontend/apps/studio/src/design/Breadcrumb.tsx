import { Children, type ReactNode } from "react";

import { Icon } from "./Icon";
import { Menu, type MenuItem } from "./Menu";

/**
 * Crumb styling, for a router <Link> or a plain element. Ancestors are muted; the current page
 * is the one place the accent colour appears in the breadcrumb.
 */
export function crumbClass(current = false): string {
  return `inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-[15px] hover:bg-sunken aria-expanded:bg-accent-soft aria-expanded:text-accent-ink ${
    current ? "font-medium text-accent" : "text-muted hover:text-ink"
  }`;
}

/**
 * The top bar's path: Organisation / Project / section / item. It replaces tab rows: a level
 * with siblings to jump between is a `CrumbSwitcher`; a level without is a link or plain text.
 */
export function Breadcrumb({ children }: { children: ReactNode }) {
  const crumbs = Children.toArray(children);
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex flex-wrap items-center gap-0.5">
        {crumbs.map((crumb, index) => (
          <li key={index} className="flex items-center gap-0.5">
            {index > 0 && (
              <span aria-hidden="true" className="px-0.5 text-muted">
                /
              </span>
            )}
            {crumb}
          </li>
        ))}
      </ol>
    </nav>
  );
}

/** A crumb that opens its siblings: the Organisation, Project, section or item switcher. */
export function CrumbSwitcher({
  label,
  menuLabel,
  items,
  current = false,
}: {
  label: string;
  /**
   * What the switcher holds: "Organisations", "Projects", "Project sections", "Agents". It names
   * the menu and is added to the button's name after the visible label ("Documents, Project
   * sections"), so tests and screen readers can find a switcher whatever is selected.
   */
  menuLabel: string;
  items: MenuItem[];
  /** True for the last crumb (the page the Member is on). */
  current?: boolean;
}) {
  return (
    <Menu
      label={
        <>
          {label}
          <Icon name="chevronDown" size={12} />
        </>
      }
      items={items}
      triggerLabel={`${label}, ${menuLabel}`}
      menuLabel={menuLabel}
      triggerClassName={crumbClass(current)}
      {...(current ? { triggerProps: { "aria-current": "page" } } : {})}
    />
  );
}

/** A crumb with nothing to switch to, e.g. the current page when it has no siblings. */
export function CrumbText({ children, current = false }: { children: ReactNode; current?: boolean }) {
  return (
    <span className={crumbClass(current)} aria-current={current ? "page" : undefined}>
      {children}
    </span>
  );
}
