import { type KeyboardEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";

import { Icon, type IconName } from "./Icon";
import { surface } from "./recipes";

/** What a menu item's link must spread onto the router <Link> it renders. */
export interface MenuLinkProps {
  role: "menuitem";
  className: string;
  "aria-current": "page" | undefined;
  children: ReactNode;
}

export interface MenuItem {
  /** Stable key; defaults to the label. */
  id?: string;
  label: string;
  /** An action. Give either this or `renderLink`. */
  onSelect?: () => void;
  /**
   * A destination: render a router <Link> with these props spread on it, so the item is a real
   * link (open in a new tab works); the menu closes when it is followed.
   */
  renderLink?: (props: MenuLinkProps) => ReactNode;
  icon?: IconName;
  /** A hint shown on the right, e.g. a keyboard shortcut or a count. */
  hint?: string;
  /** Marks where the Member is now (a breadcrumb switcher's current option). */
  current?: boolean;
  /** Destructive actions (Delete) read in the danger colour. */
  danger?: boolean;
  disabled?: boolean;
}

/**
 * A button that opens a list of actions or destinations. Used for breadcrumb switchers and row
 * "more" menus. Keyboard: Enter/Space/ArrowDown open it on the first item, ArrowUp/ArrowDown move,
 * Home/End jump, Escape closes and returns focus to the button; clicking outside closes it.
 */
export function Menu({
  label,
  items,
  triggerClassName,
  triggerLabel,
  menuLabel,
  align = "start",
  triggerProps,
}: {
  /** The trigger's content. */
  label: ReactNode;
  items: MenuItem[];
  triggerClassName: string;
  /** Accessible name when `label` is an icon, or to add what the menu holds. */
  triggerLabel?: string;
  /** Names the open menu ("Project sections"). */
  menuLabel?: string;
  align?: "start" | "end";
  triggerProps?: { "aria-current"?: "page" };
}) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const wrapper = useRef<HTMLSpanElement>(null);
  const enabled = items.filter((item) => item.disabled !== true);

  function focusItem(index: number) {
    const buttons = menu.current?.querySelectorAll<HTMLButtonElement>("[role=menuitem]:not([disabled])");
    if (!buttons || buttons.length === 0) return;
    const wrapped = (index + buttons.length) % buttons.length;
    buttons[wrapped]?.focus();
  }

  function close(returnFocus: boolean) {
    setOpen(false);
    if (returnFocus) trigger.current?.focus();
  }

  useEffect(() => {
    if (!open) return;
    focusItem(Math.max(0, enabled.findIndex((item) => item.current === true)));
    function onPointerDown(event: PointerEvent) {
      // The wrapper holds the button and the menu; a press anywhere else closes the menu.
      if (!event.composedPath().includes(wrapper.current as EventTarget)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
    };
    // Focus moves only when the menu opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function onTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
    }
  }

  function onMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("[role=menuitem]:not([disabled])"));
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === "ArrowDown") focusItem(index + 1);
    else if (event.key === "ArrowUp") focusItem(index - 1);
    else if (event.key === "Home") focusItem(0);
    else if (event.key === "End") focusItem(buttons.length - 1);
    else if (event.key === "Escape") close(true);
    else if (event.key === "Tab") close(false);
    else return;
    event.preventDefault();
  }

  return (
    <span ref={wrapper} className="relative inline-flex">
      <button
        ref={trigger}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={triggerLabel}
        className={triggerClassName}
        onClick={() => {
          setOpen(!open);
        }}
        onKeyDown={onTriggerKeyDown}
        {...triggerProps}
      >
        {label}
      </button>
      {open && (
        <div
          ref={menu}
          id={menuId}
          role="menu"
          aria-label={menuLabel}
          tabIndex={-1}
          onKeyDown={onMenuKeyDown}
          className={`${surface.popover} absolute top-full z-20 mt-2 flex min-w-60 flex-col ${align === "end" ? "right-0" : "left-0"}`}
        >
          {items.map((item) => {
            const className = `flex items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-left text-sm hover:bg-sunken focus:bg-sunken focus:outline-none disabled:opacity-50 ${
              item.current === true ? "bg-sunken font-medium" : ""
            } ${item.danger === true ? "text-danger" : "text-ink"}`;
            const content = (
              <>
                {item.icon && <Icon name={item.icon} className={item.current === true ? "text-accent" : "text-muted"} />}
                <span className="flex-1">{item.label}</span>
                {item.hint !== undefined && <span className="font-mono text-xs text-muted">{item.hint}</span>}
              </>
            );
            const current = item.current === true ? "page" : undefined;
            const onClick = () => {
              close(true);
              item.onSelect?.();
            };
            if (item.renderLink) {
              // Following the link (click or Enter) bubbles here and closes the menu.
              return (
                <span key={item.id ?? item.label} className="contents" onClick={onClick}>
                  {item.renderLink({ role: "menuitem", className, "aria-current": current, children: content })}
                </span>
              );
            }
            return (
              <button
                key={item.id ?? item.label}
                type="button"
                role="menuitem"
                disabled={item.disabled}
                aria-current={current}
                onClick={onClick}
                className={className}
              >
                {content}
              </button>
            );
          })}
        </div>
      )}
    </span>
  );
}
