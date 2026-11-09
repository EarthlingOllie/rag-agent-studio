import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

/**
 * The Studio's navigation menus, by what they hold. Each is a top bar switcher whose button is
 * named "<label>, <menu>" ("Projects, Organisation sections"), or, for the account menu, "Account".
 * The same names are used by the Playwright helper in `e2e/fixtures/navigation.ts`.
 */
export type NavigationMenu =
  | "Organisations"
  | "Organisation sections"
  | "Projects"
  | "Project sections"
  | "Agents"
  | "Agent views"
  | "Organisation settings"
  | "Account";

type User = { click: (element: Element) => Promise<unknown>; keyboard: (text: string) => Promise<unknown> };

/** An item's visible name, without what is hidden from assistive technology (a number hint, an icon). */
function itemName(item: Element): string {
  const copy = item.cloneNode(true) as Element;
  copy.querySelectorAll("[aria-hidden=true]").forEach((hidden) => {
    hidden.remove();
  });
  return copy.textContent;
}

function escape(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The button that opens `menu`, whatever its current label. */
export function menuButton(menu: NavigationMenu) {
  return screen.findByRole("button", { name: new RegExp(`^(.+, )?${escape(menu)}$`) });
}

async function openMenu(menu: NavigationMenu, user: User) {
  await user.click(await menuButton(menu));
  return screen.findByRole("menu", { name: menu });
}

/** Opens a navigation menu and follows (or chooses) `item`, as a Member does. */
export async function openSection(menu: NavigationMenu, item: string, user: User = userEvent) {
  await user.click(within(await openMenu(menu, user)).getByRole("menuitem", { name: item }));
}

/**
 * What a navigation menu offers, in order, then closes it. Role-based hiding is asserted as an
 * item missing from this list.
 */
export async function sectionNames(menu: NavigationMenu, user: User = userEvent): Promise<string[]> {
  const items = within(await openMenu(menu, user)).getAllByRole("menuitem").map(itemName);
  await user.keyboard("{Escape}");
  return items;
}

/** The item `menu` marks as where the Member is now: its switcher's label. */
export async function currentSection(menu: NavigationMenu): Promise<string> {
  const name = (await menuButton(menu)).getAttribute("aria-label") ?? "";
  return name.slice(0, name.length - `, ${menu}`.length);
}

/** Whether `menu` is on screen at all, e.g. not on a page that was not found. */
export function hasMenu(menu: NavigationMenu): boolean {
  return screen.queryByRole("button", { name: new RegExp(`^(.+, )?${escape(menu)}$`) }) !== null;
}
