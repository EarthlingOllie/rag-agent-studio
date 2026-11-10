import type { Locator, Page } from "@playwright/test";

/**
 * The Studio's navigation, by what it holds. The same names are used by the Testing Library helper
 * in `apps/studio/src/test/navigation.ts`.
 *
 * - "Organisation sections" and "Project sections" are link groups in the sidebar (the navigation
 *   landmark named "Studio"): lists of links, the current one marked `aria-current="page"`.
 * - "Organisations" and "Projects" are the sidebar's switchers: a button named
 *   "<label>, <menu>" ("HR handbook, Projects") that opens a menu.
 * - The rest are top bar menus: breadcrumb switchers named the same way, and the account menu,
 *   "<Member>, Account".
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

/** The sidebar's link groups. */
type SidebarGroup = "Organisation sections" | "Project sections";

/** The navigation menus that open from a button. */
export type SwitcherMenu = Exclude<NavigationMenu, SidebarGroup>;

const SIDEBAR_GROUPS: readonly NavigationMenu[] = ["Organisation sections", "Project sections"];
const SIDEBAR_SWITCHERS: readonly NavigationMenu[] = ["Organisations", "Projects"];

function isGroup(menu: NavigationMenu): menu is SidebarGroup {
  return SIDEBAR_GROUPS.includes(menu);
}

function escape(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The sidebar: the navigation landmark named "Studio". */
export function sidebar(page: Page) {
  return page.getByRole("navigation", { name: "Studio" });
}

function group(page: Page, menu: SidebarGroup) {
  return sidebar(page).getByRole("list", { name: menu, exact: true });
}

/** The button that opens `menu`, whatever its current label: in the sidebar, or in the top bar. */
export function menuButton(page: Page, menu: SwitcherMenu) {
  const scope = SIDEBAR_SWITCHERS.includes(menu) ? sidebar(page) : page.getByRole("banner");
  return scope.getByRole("button", { name: new RegExp(`^(.+, )?${escape(menu)}$`) });
}

/** Names of `items`, without what is hidden from assistive technology (a number hint, an icon). */
function visibleNames(items: Locator): Promise<string[]> {
  return items.evaluateAll((elements) =>
    elements.map((element) => {
      const copy = element.cloneNode(true) as Element;
      copy.querySelectorAll("[aria-hidden=true]").forEach((hidden) => {
        hidden.remove();
      });
      return copy.textContent.trim();
    }),
  );
}

/** Follows the sidebar link `item` in a group, or opens a menu and follows (or chooses) `item`, as a Member does. */
export async function openSection(page: Page, menu: NavigationMenu, item: string) {
  if (isGroup(menu)) {
    await group(page, menu).getByRole("link", { name: item, exact: true }).click();
    return;
  }
  await menuButton(page, menu).click();
  await page.getByRole("menu", { name: menu }).getByRole("menuitem", { name: item, exact: true }).click();
}

/**
 * What a sidebar group or a navigation menu offers, in order (a menu is opened, read and closed
 * again). Role-based hiding is asserted as an item missing from this list.
 */
export async function sectionNames(page: Page, menu: NavigationMenu): Promise<string[]> {
  if (isGroup(menu)) {
    const links = group(page, menu).getByRole("link");
    await links.first().waitFor();
    return visibleNames(links);
  }
  await menuButton(page, menu).click();
  const items = page.getByRole("menu", { name: menu }).getByRole("menuitem");
  await items.first().waitFor();
  const names = await visibleNames(items);
  await page.keyboard.press("Escape");
  return names;
}

/**
 * Where the Member is now in `menu`: a group's link marked `aria-current="page"` ("" when none
 * is), or a switcher's label.
 */
export async function currentSection(page: Page, menu: NavigationMenu): Promise<string> {
  if (isGroup(menu)) {
    await group(page, menu).getByRole("link").first().waitFor();
    const current = group(page, menu).locator("a[aria-current=page]");
    return (await current.count()) === 0 ? "" : ((await visibleNames(current))[0] as string);
  }
  const name = (await menuButton(page, menu).getAttribute("aria-label")) ?? "";
  return name.slice(0, name.length - `, ${menu}`.length);
}
