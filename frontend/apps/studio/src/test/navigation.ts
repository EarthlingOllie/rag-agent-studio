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

/**
 * Menus that are still a tab row, keyed by the switcher that replaces them, with the row's
 * navigation name. A later slice turns each into a switcher and deletes its entry here; the tests
 * that use the helpers do not change.
 */
const TAB_ROWS: Partial<Record<NavigationMenu, string>> = {
};

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
  const row = TAB_ROWS[menu];
  if (row !== undefined) {
    await user.click(within(await screen.findByRole("navigation", { name: row })).getByRole("link", { name: item }));
    return;
  }
  await user.click(within(await openMenu(menu, user)).getByRole("menuitem", { name: item }));
}

/**
 * What a navigation menu offers, in order, then closes it. Role-based hiding is asserted as an
 * item missing from this list.
 */
export async function sectionNames(menu: NavigationMenu, user: User = userEvent): Promise<string[]> {
  const row = TAB_ROWS[menu];
  if (row !== undefined) {
    const links = within(await screen.findByRole("navigation", { name: row })).getAllByRole("link");
    return links.map((link) => link.textContent);
  }
  const items = within(await openMenu(menu, user)).getAllByRole("menuitem").map(itemName);
  await user.keyboard("{Escape}");
  return items;
}

/** The item `menu` marks as where the Member is now: a switcher's label, or a tab row's current tab. */
export async function currentSection(menu: NavigationMenu): Promise<string> {
  const row = TAB_ROWS[menu];
  if (row !== undefined) {
    const nav = within(await screen.findByRole("navigation", { name: row }));
    return nav.getAllByRole("link").find((link) => link.getAttribute("aria-current") === "page")?.textContent ?? "";
  }
  const name = (await menuButton(menu)).getAttribute("aria-label") ?? "";
  return name.slice(0, name.length - `, ${menu}`.length);
}

/** Whether `menu` is on screen at all, e.g. not on a page that was not found. */
export function hasMenu(menu: NavigationMenu): boolean {
  const row = TAB_ROWS[menu];
  if (row !== undefined) return screen.queryByRole("navigation", { name: row }) !== null;
  return screen.queryByRole("button", { name: new RegExp(`^(.+, )?${escape(menu)}$`) }) !== null;
}
