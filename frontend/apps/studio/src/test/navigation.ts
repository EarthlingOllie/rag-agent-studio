import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

/**
 * The Studio's navigation, by what it holds. The same names are used by the Playwright helper in
 * `e2e/fixtures/navigation.ts`.
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

type User = { click: (element: Element) => Promise<unknown>; keyboard: (text: string) => Promise<unknown> };

/** An item's visible name, without what is hidden from assistive technology (an icon). */
function itemName(item: Element): string {
  const copy = item.cloneNode(true) as Element;
  copy.querySelectorAll("[aria-hidden=true]").forEach((hidden) => {
    hidden.remove();
  });
  return copy.textContent.trim();
}

function escape(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function buttonName(menu: NavigationMenu) {
  return new RegExp(`^(.+, )?${escape(menu)}$`);
}

/** The sidebar: the navigation landmark named "Studio". */
export function sidebar() {
  return screen.findByRole("navigation", { name: "Studio" });
}

/** The button that opens `menu`, whatever its current label: in the sidebar, or in the top bar. */
export async function menuButton(menu: SwitcherMenu) {
  if (SIDEBAR_SWITCHERS.includes(menu)) return within(await sidebar()).findByRole("button", { name: buttonName(menu) });
  // The main landmark is replaced once the Studio has loaded, so it is looked up on every try.
  if (MAIN_SWITCHERS.includes(menu)) return waitFor(() => within(screen.getByRole("main")).getByRole("button", { name: buttonName(menu) }));
  return screen.findByRole("button", { name: buttonName(menu) });
}

async function group(menu: SidebarGroup) {
  return within(await sidebar()).findByRole("list", { name: menu });
}

/** A tab row under a page header: the navigation landmark named `menu`. */
function tabRow(menu: TabRowMenu) {
  return screen.findByRole("navigation", { name: menu });
}

/** An Agent's tab row: the navigation landmark named "Agent views". */
export function agentTabs() {
  return tabRow("Agent views");
}

async function linkList(menu: LinkList) {
  return isTabRow(menu) ? tabRow(menu) : group(menu);
}

async function openMenu(menu: SwitcherMenu, user: User) {
  await user.click(await menuButton(menu));
  return screen.findByRole("menu", { name: menu });
}

/** Follows the sidebar link `item` in a group, or opens a menu and follows (or chooses) `item`, as a Member does. */
export async function openSection(menu: NavigationMenu, item: string, user: User = userEvent) {
  if (isLinkList(menu)) {
    await user.click(within(await linkList(menu)).getByRole("link", { name: item }));
    return;
  }
  await user.click(within(await openMenu(menu, user)).getByRole("menuitem", { name: item }));
}

/**
 * What a sidebar group or a navigation menu offers, in order (a menu is opened, read and closed
 * again). Role-based hiding is asserted as an item missing from this list.
 */
export async function sectionNames(menu: NavigationMenu, user: User = userEvent): Promise<string[]> {
  if (isLinkList(menu)) return within(await linkList(menu)).getAllByRole("link").map(itemName);
  const items = within(await openMenu(menu, user)).getAllByRole("menuitem").map(itemName);
  await user.keyboard("{Escape}");
  return items;
}

/**
 * Where the Member is now in `menu`: a group's link marked `aria-current="page"` ("" when none
 * is), or a switcher's label.
 */
export async function currentSection(menu: NavigationMenu): Promise<string> {
  if (isLinkList(menu)) {
    const current = within(await linkList(menu))
      .getAllByRole("link")
      .find((link) => link.getAttribute("aria-current") === "page");
    return current === undefined ? "" : itemName(current);
  }
  const name = (await menuButton(menu)).getAttribute("aria-label") ?? "";
  return name.slice(0, name.length - `, ${menu}`.length);
}

/** Whether `menu` is on screen at all, e.g. not on a page that was not found. */
export function hasMenu(menu: NavigationMenu): boolean {
  const nav = screen.queryByRole("navigation", { name: "Studio" });
  if (isTabRow(menu)) return screen.queryByRole("navigation", { name: menu }) !== null;
  if (isGroup(menu)) return nav !== null && within(nav).queryByRole("list", { name: menu }) !== null;
  const scope = SIDEBAR_SWITCHERS.includes(menu) ? nav : MAIN_SWITCHERS.includes(menu) ? screen.queryByRole("main") : document.body;
  return scope !== null && within(scope).queryByRole("button", { name: buttonName(menu) }) !== null;
}

/**
 * The top bar's breadcrumb, once it has crumbs: their names in order, and the one marked
 * `aria-current="page"` ("" when none is).
 */
export async function breadcrumb(): Promise<{ crumbs: string[]; current: string }> {
  const nav = within(await screen.findByRole("banner")).getByRole("navigation", { name: "Breadcrumb" });
  const links = await within(nav).findAllByRole("link");
  const current = links.find((link) => link.getAttribute("aria-current") === "page");
  return { crumbs: links.map(itemName), current: current === undefined ? "" : itemName(current) };
}

/** The top bar's "Open navigation" button, which opens the sidebar as a drawer on a narrow screen. */
export function navigationButton() {
  return within(screen.getByRole("banner")).findByRole("button", { name: "Open navigation" });
}

/** Opens the sidebar drawer from the top bar, as a Member on a phone does, and returns it. */
export async function openDrawer(user: User = userEvent) {
  await user.click(await navigationButton());
  return screen.findByRole("dialog", { name: "Navigation" });
}
