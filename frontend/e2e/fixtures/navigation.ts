import type { Locator, Page } from "@playwright/test";

/**
 * The Studio's navigation, by what it holds. The same names are used by the Testing Library helper
 * in `apps/studio/src/test/navigation.ts`.
 *
 * - "Organisation sections" and "Project sections" are link groups in the sidebar (the navigation
 *   landmark named "Studio"): lists of links, the current one marked `aria-current="page"`.
 * - "Organisations" and "Projects" are the sidebar's switchers: a button named
 *   "<label>, <menu>" ("HR handbook, Projects") that opens a menu.
 * - "Agent views" and "Organisation settings" are tab rows under a page header (navigation
 *   landmarks of those names): lists of links, the current one marked `aria-current="page"`, like
 *   a sidebar group.
 * - "Agents" is the ▾ switcher on the Agent's name, in the page's main content, named the same way.
 * - "Account" is the top bar's account menu, "<Member>, Account". The breadcrumb has no menus: it
 *   is plain links (`breadcrumb`).
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
export type SwitcherMenu = Exclude<NavigationMenu, SidebarGroup | "Agent views" | "Organisation settings">;

const SIDEBAR_GROUPS: readonly NavigationMenu[] = ["Organisation sections", "Project sections"];
const SIDEBAR_SWITCHERS: readonly NavigationMenu[] = ["Organisations", "Projects"];

function isGroup(menu: NavigationMenu): menu is SidebarGroup {
  return SIDEBAR_GROUPS.includes(menu);
}

/** Tab rows under a page header. */
type TabRowMenu = "Agent views" | "Organisation settings";

const TAB_ROWS: readonly NavigationMenu[] = ["Agent views", "Organisation settings"];

function isTabRow(menu: NavigationMenu): menu is TabRowMenu {
  return TAB_ROWS.includes(menu);
}

/** Lists of links: the sidebar's groups and the tab rows. */
type LinkList = SidebarGroup | TabRowMenu;

/** The switchers in the page's main content rather than the sidebar or the top bar. */
const MAIN_SWITCHERS: readonly NavigationMenu[] = ["Agents"];

function isLinkList(menu: NavigationMenu): menu is LinkList {
  return isGroup(menu) || isTabRow(menu);
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

/** A tab row under a page header: the navigation landmark named `menu`. */
function tabRow(page: Page, menu: TabRowMenu) {
  return page.getByRole("navigation", { name: menu, exact: true });
}

/** An Agent's tab row: the navigation landmark named "Agent views". */
export function agentTabs(page: Page) {
  return tabRow(page, "Agent views");
}

function linkList(page: Page, menu: LinkList) {
  return isTabRow(menu) ? tabRow(page, menu) : group(page, menu);
}

/** The button that opens `menu`, whatever its current label: in the sidebar, or in the top bar. */
export function menuButton(page: Page, menu: SwitcherMenu) {
  const scope = SIDEBAR_SWITCHERS.includes(menu)
    ? sidebar(page)
    : MAIN_SWITCHERS.includes(menu)
      ? page.getByRole("main")
      : page.getByRole("banner");
  return scope.getByRole("button", { name: new RegExp(`^(.+, )?${escape(menu)}$`) });
}

/** Names of `items`, without what is hidden from assistive technology (an icon). */
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
  if (isLinkList(menu)) {
    await linkList(page, menu).getByRole("link", { name: item, exact: true }).click();
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
  if (isLinkList(menu)) {
    const links = linkList(page, menu).getByRole("link");
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
  if (isLinkList(menu)) {
    await linkList(page, menu).getByRole("link").first().waitFor();
    const current = linkList(page, menu).locator("a[aria-current=page]");
    return (await current.count()) === 0 ? "" : ((await visibleNames(current))[0] as string);
  }
  const name = (await menuButton(page, menu).getAttribute("aria-label")) ?? "";
  return name.slice(0, name.length - `, ${menu}`.length);
}

/**
 * The top bar's breadcrumb, once it has crumbs: their names in order, and the one marked
 * `aria-current="page"` ("" when none is). Crumbs hidden on a narrow screen are left out.
 */
export async function breadcrumb(page: Page): Promise<{ crumbs: string[]; current: string }> {
  const links = page.getByRole("banner").getByRole("navigation", { name: "Breadcrumb" }).getByRole("link");
  await links.first().waitFor();
  const current = links.and(page.locator("[aria-current=page]"));
  return { crumbs: await visibleNames(links), current: (await current.count()) === 0 ? "" : ((await visibleNames(current))[0] as string) };
}

/** The top bar's "Open navigation" button, shown below `md`, where the sidebar is a drawer. */
export function navigationButton(page: Page) {
  return page.getByRole("banner").getByRole("button", { name: "Open navigation" });
}

/** Opens the sidebar drawer from the top bar, as a Member on a phone does, and returns it. */
export async function openDrawer(page: Page): Promise<Locator> {
  await navigationButton(page).click();
  const drawer = page.getByRole("dialog", { name: "Navigation" });
  await drawer.getByRole("navigation", { name: "Studio" }).waitFor();
  return drawer;
}
