import AxeBuilder from "@axe-core/playwright";
import type { Browser, Locator, Page } from "@playwright/test";

import { AXE_TAGS, expect, test } from "../fixtures";
import { newMember } from "../fixtures/auth";

async function openTheme(page: Page) {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Organisation settings" }).click();
  await page.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: "Theme" }).click();
  await expect(page.getByRole("form", { name: "Theme" })).toBeVisible();
}

function preview(page: Page, scheme = "light"): Locator {
  return page.getByRole("group", { name: `Widget preview (${scheme})` });
}

async function themeProperty(locator: Locator, name: string): Promise<string> {
  return locator.evaluate((element, property) => (element as HTMLElement).style.getPropertyValue(property), name);
}

/** What the browser actually paints: the launcher's background, resolved through the custom property. */
async function launcherBackground(page: Page): Promise<string> {
  return preview(page)
    .getByRole("button", { name: /chat/ })
    .evaluate((element) => getComputedStyle(element).backgroundColor);
}

async function organisationId(page: Page): Promise<string> {
  const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
  return me.organisations[0]?.id ?? "";
}

/** Adds a new Editor to the Owner's Organisation through an Invite Link, signed in in their own browser. */
async function newEditor(owner: Page, browser: Browser): Promise<Page> {
  const person = newMember({ name: "Grace Editor" });
  const invited = await owner.request.post(`/api/organisations/${await organisationId(owner)}/invites`, {
    data: { email: person.email, role: "editor", send_email: false },
  });
  expect(invited.status()).toBe(201);
  const token = new URL(((await invited.json()) as { link: string }).link).searchParams.get("token") ?? "";
  const page = await (await browser.newContext()).newPage();
  const joined = await page.request.post("/api/invites/sign-up", {
    data: { token, name: person.name, password: person.password },
  });
  expect(joined.status()).toBe(201);
  return page;
}

test.describe("Theme editor", () => {
  test("an Owner changes the primary colour, sees the preview update and the contrast warning, and saves", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await openTheme(page);
    expect(await themeProperty(preview(page), "--theme-primary")).toBe("#4f46e5");
    expect(await launcherBackground(page)).toBe("rgb(79, 70, 229)");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The preview follows the edit before anything is saved.
    await page.getByLabel("Primary (light)", { exact: true }).fill("#b91c1c");
    await expect.poll(() => themeProperty(preview(page), "--theme-primary")).toBe("#b91c1c");
    expect(await launcherBackground(page)).toBe("rgb(185, 28, 28)");

    // A failing pair warns, and the warning goes once it is fixed.
    const contrast = page.getByRole("status", { name: "Contrast" });
    await page.getByLabel("Text on primary (light)", { exact: true }).fill("#f87171");
    await expect(contrast.getByRole("listitem")).toHaveText([
      "Text on primary (#f87171 on #b91c1c) has a contrast of 2.33:1 in light mode. WCAG AA needs 4.5:1.",
    ]);
    await page.getByLabel("Text on primary (light)", { exact: true }).fill("#ffffff");
    await expect(contrast.getByRole("listitem")).toHaveCount(0);

    await page.getByRole("radio", { name: "Bottom left" }).check();
    await page.getByRole("button", { name: "Save Theme" }).click();
    await expect(page.getByRole("status", { name: "Saved" })).toHaveText("Theme saved. The widget uses it now.");

    // Saved Themes apply at once: a reload shows them.
    await page.reload();
    await expect(page.getByLabel("Primary (light)", { exact: true })).toHaveValue("#b91c1c");
    await expect(preview(page).getByRole("button", { name: "Close chat" })).toHaveAttribute("data-position", "bottom-left");

    // The change is an Audit Event.
    await page.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: "Audit" }).click();
    const row = page.getByRole("table", { name: "Audit Events" }).getByRole("row").filter({ hasText: "theme.updated" });
    await expect(row).toHaveCount(1);
    await expect(row).toContainText('"primary":{"light":"#b91c1c"}');
  });

  test("an Editor views the Theme and its preview but can't change it", async ({ signedInPage: owner, browser }) => {
    const editor = await newEditor(owner, browser);

    await openTheme(editor);

    await expect(editor.getByText("Only Owners can change the Theme.")).toBeVisible();
    await expect(editor.getByLabel("Primary (light)", { exact: true })).toBeDisabled();
    await expect(editor.getByRole("button", { name: "Save Theme" })).toHaveCount(0);
    await expect(preview(editor).getByRole("region", { name: "Chat with Assistant" })).toBeVisible();
    expect((await new AxeBuilder({ page: editor }).withTags(AXE_TAGS).analyze()).violations).toEqual([]);
    const path = `/api/organisations/${await organisationId(owner)}/theme`;
    const theme = (await (await editor.request.get(path)).json()) as Record<string, unknown>;
    delete theme.updated_at;
    const refused = await editor.request.put(path, { data: { ...theme, radius: 0 } });
    expect(refused.status()).toBe(403);
  });
});
