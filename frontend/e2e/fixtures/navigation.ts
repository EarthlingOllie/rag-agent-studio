import type { Page } from "@playwright/test";

/**
 * The Studio's navigation menus, by what they hold. Each is a top bar switcher whose button is
 * named "<label>, <menu>" ("Projects, Organisation sections"), or, for the account menu,
 * "<Member>, Account". The same names are used by the Testing Library helper in
 * `apps/studio/src/test/navigation.ts`.
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
 * navigation name. A later slice turns each into a switcher and deletes its entry here; the specs
 * that use the helpers do not change.
 */
const TAB_ROWS: Partial<Record<NavigationMenu, string>> = {
  "Organisation settings": "Organisation settings",
};

function escape(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The button that opens `menu`, whatever its current label. */
export function menuButton(page: Page, menu: NavigationMenu) {
  return page.getByRole("banner").getByRole("button", { name: new RegExp(`^(.+, )?${escape(menu)}$`) });
}

/** Opens a navigation menu and follows (or chooses) `item`, as a Member does. */
export async function openSection(page: Page, menu: NavigationMenu, item: string) {
  const row = TAB_ROWS[menu];
  if (row !== undefined) {
    await page.getByRole("navigation", { name: row }).getByRole("link", { name: item, exact: true }).click();
    return;
  }
  await menuButton(page, menu).click();
  await page.getByRole("menu", { name: menu }).getByRole("menuitem", { name: item, exact: true }).click();
}

/**
 * What a navigation menu offers, in order, then closes it. Role-based hiding is asserted as an
 * item missing from this list.
 */
export async function sectionNames(page: Page, menu: NavigationMenu): Promise<string[]> {
  const row = TAB_ROWS[menu];
  if (row !== undefined) {
    const links = page.getByRole("navigation", { name: row }).getByRole("link");
    await links.first().waitFor();
    return (await links.allTextContents()).map((text) => text.trim());
  }
  await menuButton(page, menu).click();
  const items = page.getByRole("menu", { name: menu }).getByRole("menuitem");
  await items.first().waitFor();
  // An item's name without what is hidden from assistive technology (a number hint, an icon).
  const names = await items.evaluateAll((elements) =>
    elements.map((element) => {
      const copy = element.cloneNode(true) as Element;
      copy.querySelectorAll("[aria-hidden=true]").forEach((hidden) => {
        hidden.remove();
      });
      return copy.textContent.trim();
    }),
  );
  await page.keyboard.press("Escape");
  return names;
}
