import type { Page } from "@playwright/test";

/**
 * The Documents section's controls, as a Member uses them: a row's ⋯ menu, the Tags dialog and
 * the bulk bar's Tag menus. The same names are used by the unit tests in
 * `apps/studio/src/projects/Documents*.test.tsx`.
 */

/** Chooses an item (Retry, New edition, Edit Tags, Delete) from a Document's ⋯ menu. */
export async function rowAction(page: Page, name: string, action: "Retry" | "New edition" | "Edit Tags" | "Delete") {
  await page.getByRole("button", { name: `More actions for ${name}`, exact: true }).click();
  await page.getByRole("menu", { name: `Actions for ${name}` }).getByRole("menuitem", { name: action, exact: true }).click();
}

/** Opens Manage tags: the dialog where the Project's Tags are created, renamed and deleted. */
export async function openTags(page: Page) {
  await page.getByRole("button", { name: "Manage tags" }).click();
  return page.getByRole("dialog", { name: "Tags" });
}

/** Adds a Tag to, or removes it from, the selected Documents, from the bulk bar. */
export async function bulkTag(page: Page, menu: "Add Tag" | "Remove Tag", tag: string) {
  await page.getByRole("toolbar", { name: "Bulk actions" }).getByRole("button", { name: menu, exact: true }).click();
  await page.getByRole("menu").getByRole("menuitem", { name: tag, exact: true }).click();
}

/** The Documents stat card's figure, "2 / 500". */
export function quota(page: Page) {
  return page.getByRole("region", { name: "Knowledge Base" }).getByText("Documents", { exact: true }).locator("xpath=following-sibling::span[1]");
}
