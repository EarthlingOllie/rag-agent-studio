import type { ReactNode } from "react";

/**
 * A tab link's classes, for a router <Link> in a `TabRow`. The current tab (marked
 * `aria-current="page"`, which the styling follows) is underlined in `accent` and set in `ink`.
 */
export const tabLink =
  "-mb-px flex h-10 shrink-0 items-center border-b-2 border-transparent px-3 text-sm whitespace-nowrap text-muted hover:text-ink aria-[current=page]:border-accent aria-[current=page]:font-medium aria-[current=page]:text-ink";

/**
 * A row of tabs under a page header: a navigation landmark named `label` holding a list of links,
 * one per view, each its own page. It scrolls sideways on a narrow screen instead of wrapping.
 */
export function TabRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <nav aria-label={label} className="min-w-0 overflow-x-auto border-b border-line">
      <ul className="flex gap-1">{children}</ul>
    </nav>
  );
}
