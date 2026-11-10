import { Children, type ReactNode } from "react";

/**
 * A crumb's classes, for a router <Link> in a `Breadcrumb`. Ancestors are muted; the current page
 * (marked `aria-current="page"`, which the styling follows) is the one place the accent colour
 * appears in the breadcrumb. A long name is cut short with an ellipsis rather than wrapping.
 */
export const crumbLink =
  "block h-8 max-w-60 min-w-0 truncate rounded-md px-2 text-[15px] leading-8 text-muted hover:bg-sunken hover:text-ink aria-[current=page]:font-medium aria-[current=page]:text-accent";

/**
 * The top bar's path: plain links, one per child, from the outermost page to the current one. It
 * says where the Member is and leads back up; the sidebar is how they move around, so no crumb
 * opens a menu.
 *
 * On a narrow screen (below `md`) only the last two crumbs are shown, so the top bar stays one row.
 */
export function Breadcrumb({ children }: { children: ReactNode }) {
  const crumbs = Children.toArray(children);
  const firstNarrow = crumbs.length - 2;
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex min-w-0 items-center gap-0.5">
        {crumbs.map((crumb, index) => (
          <li key={index} className={`min-w-0 items-center gap-0.5 ${index < firstNarrow ? "hidden md:flex" : "flex"}`}>
            {index > 0 && (
              <span aria-hidden="true" className={`px-0.5 text-muted ${index === firstNarrow ? "hidden md:inline" : ""}`}>
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
