import type { Locator, Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { openSection } from "../fixtures/navigation";

/** What the browser draws for a select: its arrow, its paddings and where its chevron sits. */
function drawn(select: Locator) {
  return select.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      appearance: style.appearance,
      paddingLeft: style.paddingLeft,
      paddingRight: Number.parseFloat(style.paddingRight),
      chevron: style.backgroundImage,
      chevronX: style.backgroundPositionX,
    };
  });
}

async function openMembers(page: Page) {
  await page.goto("/");
  await openSection(page, "Organisation sections", "Settings");
  await openSection(page, "Organisation settings", "Members");
  await expect(page.getByRole("table", { name: "Members" })).toBeVisible();
}

test("selects draw the design system's chevron, inset like their text, in both Appearances", async ({ signedInPage: page, member }) => {
  await openMembers(page);
  // A form field (the invite's Role) and a table-cell select (the Member's own role).
  const selects = [
    page.getByRole("form", { name: "Invite someone" }).getByLabel("Role"),
    page.getByLabel(`Role for ${member.name}`),
  ];
  const chevrons: string[] = [];
  for (const select of selects) {
    const style = await drawn(select);
    expect(style.appearance).toBe("none");
    expect(style.paddingRight).toBeGreaterThanOrEqual(36);
    expect(style.chevron).toContain("data:image/svg+xml");
    expect(style.chevronX).toBe(`right ${style.paddingLeft}`);
    chevrons.push(style.chevron);
  }

  // The chevron is drawn in the muted colour of whichever Appearance is showing.
  await page.evaluate(() => {
    document.documentElement.dataset.appearance = "dark";
  });
  const dark = await drawn(selects[0] as Locator);
  expect(dark.chevron).toContain("data:image/svg+xml");
  expect(dark.chevron).not.toBe(chevrons[0]);
});
