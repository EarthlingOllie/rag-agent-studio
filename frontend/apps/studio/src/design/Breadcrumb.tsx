import { Children, Fragment, type KeyboardEvent, type MouseEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";

import { Icon } from "./Icon";
import { Menu, type MenuItem } from "./Menu";
import { surface } from "./recipes";

/**
 * Crumb styling, for a router <Link> or a plain element. Ancestors are muted; the current page
 * is the one place the accent colour appears in the breadcrumb.
 */
export function crumbClass(current = false): string {
  return `inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-[15px] hover:bg-sunken aria-expanded:bg-accent-soft aria-expanded:text-accent-ink ${
    current ? "font-medium text-accent" : "text-muted hover:text-ink"
  }`;
}

const separator = (
  <span aria-hidden="true" className="px-0.5 text-muted">
    /
  </span>
);

/**
 * The top bar's path: Organisation / Project / section / item. It replaces tab rows: a level
 * with siblings to jump between is a `CrumbSwitcher`; a level without is a link or plain text.
 *
 * On a narrow screen (below `md`) a path of three or more crumbs keeps the first (the
 * Organisation) and the last (the current page) and folds the middle into "…" (`PathFold`).
 */
export function Breadcrumb({ children }: { children: ReactNode }) {
  const crumbs = Children.toArray(children);
  const middle = crumbs.slice(1, -1);
  return (
    <nav aria-label="Breadcrumb" className="relative min-w-0">
      <ol className="flex flex-wrap items-center gap-0.5">
        {crumbs.map((crumb, index) => {
          const folded = index > 0 && index < crumbs.length - 1;
          return (
            <Fragment key={index}>
              {index === 1 && middle.length > 0 && (
                <li className="flex items-center gap-0.5 md:hidden">
                  {separator}
                  <PathFold>{middle}</PathFold>
                </li>
              )}
              <li className={`items-center gap-0.5 ${folded ? "hidden md:flex" : "flex"}`}>
                {index > 0 && separator}
                {crumb}
              </li>
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}

/**
 * The narrow screen's "…": a disclosure that lists the folded middle crumbs, each still the same
 * switcher. Escape (outside a switcher's own menu) closes it and returns focus to "…"; a press
 * outside it, or following a link inside it, closes it.
 */
function PathFold({ children }: { children: ReactNode[] }) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const wrapper = useRef<HTMLSpanElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!event.composedPath().includes(wrapper.current as EventTarget)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [open]);

  function onKeyDown(event: KeyboardEvent<HTMLSpanElement>) {
    // A switcher's menu handles its own Escape first (and marks it handled).
    if (event.key !== "Escape" || event.defaultPrevented) return;
    event.preventDefault();
    setOpen(false);
    trigger.current?.focus();
  }

  function onClick(event: MouseEvent<HTMLOListElement>) {
    if ((event.target as Element).closest("a") !== null) setOpen(false);
  }

  return (
    // The list is placed against the breadcrumb (the nav), not the "…", so it fits a narrow window.
    <span ref={wrapper} className="inline-flex" onKeyDown={onKeyDown}>
      <button
        ref={trigger}
        type="button"
        aria-label="Show the whole path"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        className={crumbClass()}
        onClick={() => {
          setOpen(!open);
        }}
      >
        …
      </button>
      {open && (
        <ol
          id={listId}
          aria-label="The whole path"
          onClick={onClick}
          className={`${surface.popover} absolute top-full left-0 z-20 mt-2 flex w-max max-w-[calc(100vw-2rem)] min-w-60 flex-col items-start gap-1`}
        >
          {children.map((crumb, index) => (
            <li key={index} className="flex">
              {crumb}
            </li>
          ))}
        </ol>
      )}
    </span>
  );
}

/** A crumb that opens its siblings: the Organisation, Project, section or item switcher. */
export function CrumbSwitcher({
  label,
  menuLabel,
  items,
  current = false,
  disabled = false,
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
  /** While a switch the menu started is under way. */
  disabled?: boolean;
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
      disabled={disabled}
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
