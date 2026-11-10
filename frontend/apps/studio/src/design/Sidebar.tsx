import { type KeyboardEvent, type MouseEvent, type ReactNode, type Ref, useEffect, useRef } from "react";

import { Icon, type IconName } from "./Icon";
import { button } from "./recipes";

/**
 * A sidebar link's classes, for a router <Link>. The current link (marked `aria-current="page"`,
 * which the styling follows) has the soft accent fill the current crumb had.
 */
export const sidebarLink =
  "flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-sm text-ink-2 hover:bg-sunken hover:text-ink aria-[current=page]:bg-accent-soft aria-[current=page]:font-medium aria-[current=page]:text-accent-ink";

/** A sidebar switcher's button (the Organisation or Project switcher): the whole row is the button. */
export const sidebarSwitcher =
  "flex h-10 w-full min-w-0 items-center justify-between gap-2 rounded-lg px-2.5 text-left text-sm font-semibold text-ink hover:bg-sunken";

/** The open drawer, below `md`: over the page at the left, full height, scrolling on its own. */
const DRAWER = "fixed inset-y-0 left-0 z-50 block overflow-y-auto shadow-[0_12px_32px_var(--ds-scrim)] md:bottom-auto md:shadow-none";

const FOCUSABLE = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** The sidebar's drawer state on a narrow screen: the top bar's button opens it (`SidebarButton`). */
export interface SidebarDrawer {
  open: boolean;
  /** Closes the drawer: Escape, a press outside it, or following a link in it. */
  onClose: () => void;
}

/**
 * The Studio's navigation beside the page: a navigation landmark named `label`, about 240 px wide,
 * that stays in place while the page scrolls. Below `md` it is hidden until the top bar's button
 * (`SidebarButton`, controlling `id`) opens it as a drawer: a modal dialog named "Navigation" over
 * the page, which focuses the current link on opening, keeps Tab and Shift+Tab inside, and closes
 * on Escape, a press outside it or a followed link. `drawer.onClose` returns focus to the button.
 */
export function Sidebar({ label, children, id, drawer }: { label: string; children: ReactNode; id: string; drawer: SidebarDrawer }) {
  const panel = useRef<HTMLElement>(null);
  const { open, onClose } = drawer;

  useEffect(() => {
    if (!open) return;
    const current = panel.current?.querySelector<HTMLElement>('a[aria-current="page"]');
    (current ?? panel.current?.querySelector<HTMLElement>(FOCUSABLE))?.focus();
  }, [open]);

  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    // A switcher's open menu handles its own Escape and Tab first.
    if (!open || event.defaultPrevented) return;
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(FOCUSABLE));
    event.preventDefault();
    const index = focusable.indexOf(document.activeElement as HTMLElement);
    const next = event.shiftKey ? (index <= 0 ? focusable.length - 1 : index - 1) : (index + 1) % focusable.length;
    focusable[next]?.focus();
  }

  function onClick(event: MouseEvent<HTMLElement>) {
    // Following a link, the sidebar's own or a switcher's, closes the drawer.
    if (open && (event.target as Element).closest("a[href]") !== null) onClose();
  }

  return (
    <>
      {open && (
        <div
          data-testid="drawer-scrim"
          aria-hidden="true"
          className="fixed inset-0 z-40 bg-scrim md:hidden"
          // Focus stays in the drawer, so Escape and Tab keep working after a press outside it.
          onMouseDown={(event) => {
            event.preventDefault();
          }}
          onClick={onClose}
        />
      )}
      <aside
        ref={panel}
        id={id}
        role={open ? "dialog" : undefined}
        aria-modal={open ? true : undefined}
        aria-label={open ? "Navigation" : undefined}
        onKeyDown={onKeyDown}
        onClick={onClick}
        className={`${open ? DRAWER : "hidden"} w-60 shrink-0 border-r border-line bg-surface md:sticky md:top-0 md:block md:h-screen md:self-start md:overflow-y-auto`}
      >
        <nav aria-label={label} className="flex flex-col gap-1 px-3 py-4">
          {children}
        </nav>
      </aside>
    </>
  );
}

/** The top bar's menu button that opens the sidebar drawer; shown below `md` only. */
export function SidebarButton({
  controls,
  open,
  onOpen,
  ref,
}: {
  /** The sidebar's `id`. */
  controls: string;
  open: boolean;
  onOpen: () => void;
  ref: Ref<HTMLButtonElement>;
}) {
  return (
    <button
      ref={ref}
      type="button"
      aria-label="Open navigation"
      aria-controls={controls}
      aria-expanded={open}
      className={`${button.iconBare} md:hidden`}
      onClick={onOpen}
    >
      <Icon name="menu" />
    </button>
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
