import AxeBuilder from "@axe-core/playwright";
import type { Browser, Locator, Page } from "@playwright/test";

import { AXE_TAGS, expect, test } from "../fixtures";
import { newMember } from "../fixtures/auth";
import { openSection } from "../fixtures/navigation";

async function openTheme(page: Page) {
  await page.goto("/");
  await openSection(page, "Organisation sections", "Settings");
  await openSection(page, "Organisation settings", "Theme");
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

/** Real 1x1 PNGs, one red and one teal, as an Owner's image files. */
const RED_PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGPYKSMDAAKDAPKqyfh0AAAAAElFTkSuQmCC", "base64");
const TEAL_PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGPgL8sDAAGLAPQ8xSAqAAAAAElFTkSuQmCC", "base64");

/** Whether the browser loaded and decoded the image, so its URL really served it. */
async function loaded(image: Locator): Promise<boolean> {
  return image.evaluate((element) => (element as HTMLImageElement).complete && (element as HTMLImageElement).naturalWidth > 0);
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
    await openSection(page, "Organisation settings", "Audit");
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

  test("an Owner uploads, replaces and removes the logo and avatar, and the preview shows them", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await openTheme(page);
    const images = page.getByRole("region", { name: "Logo and avatar" });
    await expect(images.getByText("No logo yet.")).toBeVisible();

    // Presign, PUT straight to the object store (RustFS through the Studio's proxy), confirm.
    await images.getByLabel("Upload logo").setInputFiles({ name: "logo.png", mimeType: "image/png", buffer: RED_PNG });
    await expect(images.getByText("Logo saved. The widget uses it now.")).toBeVisible();
    await images.getByLabel("Upload avatar").setInputFiles({ name: "avatar.png", mimeType: "image/png", buffer: TEAL_PNG });
    await expect(images.getByText("Avatar saved. The widget uses it now.")).toBeVisible();

    const logo = preview(page).getByRole("img", { name: "Logo" });
    const avatar = preview(page).getByRole("img", { name: "Assistant's avatar" });
    await expect.poll(() => loaded(logo)).toBe(true);
    await expect.poll(() => loaded(avatar)).toBe(true);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // Replacing serves the new file under a new URL; it survives a reload.
    const firstUrl = await logo.getAttribute("src");
    await images.getByLabel("Replace logo").setInputFiles({ name: "logo-2.png", mimeType: "image/png", buffer: TEAL_PNG });
    await expect.poll(() => logo.getAttribute("src")).not.toBe(firstUrl);
    await page.reload();
    await expect.poll(() => loaded(preview(page).getByRole("img", { name: "Logo" }))).toBe(true);
    const served = await page.request.get((await preview(page).getByRole("img", { name: "Logo" }).getAttribute("src")) ?? "");
    expect(Buffer.from(await served.body()).equals(TEAL_PNG)).toBe(true);

    // A file that isn't an allowed image type is refused with its reason.
    await page
      .getByRole("region", { name: "Logo and avatar" })
      .getByLabel("Replace logo")
      .setInputFiles({ name: "logo.svg", mimeType: "image/svg+xml", buffer: Buffer.from("<svg xmlns='http://www.w3.org/2000/svg'/>") });
    await expect(page.getByRole("region", { name: "Logo and avatar" }).getByRole("alert")).toHaveText("Upload a PNG, JPEG or WebP image.");

    await page.getByRole("region", { name: "Logo and avatar" }).getByRole("button", { name: "Remove avatar" }).click();
    await expect(page.getByRole("region", { name: "Logo and avatar" }).getByText("No avatar yet.")).toBeVisible();
    await expect(preview(page).getByRole("img", { name: "Assistant's avatar" })).toHaveCount(0);

    // Each change is an Audit Event.
    await openSection(page, "Organisation settings", "Audit");
    const rows = page.getByRole("table", { name: "Audit Events" }).getByRole("row").filter({ hasText: "theme.updated" });
    await expect(rows).toHaveCount(4);
    await expect(rows.first()).toContainText('"avatar":null');
  });

  test("an Editor sees the Theme's images but can't upload or remove them", async ({ signedInPage: owner, browser }) => {
    await openTheme(owner);
    await owner.getByLabel("Upload logo").setInputFiles({ name: "logo.png", mimeType: "image/png", buffer: RED_PNG });
    await expect(owner.getByText("Logo saved. The widget uses it now.")).toBeVisible();
    const editor = await newEditor(owner, browser);

    await openTheme(editor);

    const images = editor.getByRole("region", { name: "Logo and avatar" });
    await expect.poll(() => loaded(images.getByRole("img", { name: "Current logo" }))).toBe(true);
    await expect.poll(() => loaded(preview(editor).getByRole("img", { name: "Logo" }))).toBe(true);
    await expect(images.getByLabel("Replace logo")).toBeDisabled();
    await expect(images.getByRole("button", { name: "Remove logo" })).toHaveCount(0);
    expect((await new AxeBuilder({ page: editor }).withTags(AXE_TAGS).analyze()).violations).toEqual([]);
    const path = `/api/organisations/${await organisationId(owner)}/theme/images/avatar/uploads`;
    const refused = await editor.request.post(path, { data: { filename: "a.png", size_bytes: 10 } });
    expect(refused.status()).toBe(403);
  });
});

test.describe("Theme editor: colours, shape, type, mode and launcher", () => {
  /** The fonts an Owner can choose from, as the curated list names them. */
  const CURATED_FONTS = [
    "Inter (sans-serif)",
    "Roboto (sans-serif)",
    "Open Sans (sans-serif)",
    "Lato (sans-serif)",
    "Source Sans 3 (sans-serif)",
    "Nunito (sans-serif)",
    "Work Sans (sans-serif)",
    "IBM Plex Sans (sans-serif)",
    "Merriweather (serif)",
    "Lora (serif)",
    "Source Serif 4 (serif)",
    "JetBrains Mono (monospace)",
  ];

  test("an Owner sets the surface and accent colours, the corner radius and a curated font, previews them and saves", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await openTheme(page);

    // Surface and accent, for light and dark mode.
    await page.getByLabel("Surface (light)", { exact: true }).fill("#fef3c7");
    await page.getByLabel("Surface (dark)", { exact: true }).fill("#1e1b4b");
    await page.getByLabel("Accent (light)", { exact: true }).fill("#9a3412");
    await page.getByLabel("Accent (dark)", { exact: true }).fill("#fdba74");
    await expect.poll(() => themeProperty(preview(page), "--theme-surface")).toBe("#fef3c7");
    expect(await themeProperty(preview(page), "--theme-accent")).toBe("#9a3412");
    await expect(preview(page).getByRole("link", { name: "Opening hours, page 2" })).toHaveCSS("color", "rgb(154, 52, 18)");

    // The corner radius: out of range is refused before saving, a whole number in range is previewed.
    const radius = page.getByLabel("Corner radius (px)");
    await radius.fill("40");
    await expect(page.getByText("Use a whole number from 0 to 24.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Save Theme" })).toBeDisabled();
    await radius.fill("4");
    await expect(page.getByText("Use a whole number from 0 to 24.")).toHaveCount(0);
    await expect.poll(() => themeProperty(preview(page), "--theme-radius")).toBe("4px");

    // The font comes from a curated list only; the preview loads it from the allowlisted stylesheet.
    const font = page.getByLabel("Font", { exact: true });
    expect(await font.getByRole("option").allTextContents()).toEqual(CURATED_FONTS);
    await font.selectOption({ label: "Merriweather (serif)" });
    await expect.poll(() => themeProperty(preview(page), "--theme-font-family")).toContain('"Merriweather"');
    await expect(page.locator('link[rel="stylesheet"][href*="fonts.googleapis.com/css2?family=Merriweather"]')).toHaveCount(1);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    await page.getByRole("button", { name: "Save Theme" }).click();
    await expect(page.getByRole("status", { name: "Saved" })).toHaveText("Theme saved. The widget uses it now.");

    await page.reload();
    await expect(page.getByLabel("Surface (dark)", { exact: true })).toHaveValue("#1e1b4b");
    await expect(page.getByLabel("Accent (dark)", { exact: true })).toHaveValue("#fdba74");
    await expect(page.getByLabel("Corner radius (px)")).toHaveValue("4");
    await expect(page.getByLabel("Font", { exact: true })).toHaveValue("Merriweather");
    const path = `/api/organisations/${await organisationId(page)}/theme`;
    const saved = (await (await page.request.get(path)).json()) as Record<string, unknown>;
    expect(saved).toMatchObject({
      radius: 4,
      font: "Merriweather",
      colours: { surface: { light: "#fef3c7", dark: "#1e1b4b" }, accent: { light: "#9a3412", dark: "#fdba74" } },
    });

    // A font outside the list can't be saved through the API either.
    delete saved.updated_at;
    delete saved.logo;
    delete saved.avatar;
    expect((await page.request.put(path, { data: { ...saved, font: "https://fonts.example/evil.css" } })).status()).toBe(422);

    await openSection(page, "Organisation settings", "Audit");
    const row = page.getByRole("table", { name: "Audit Events" }).getByRole("row").filter({ hasText: "theme.updated" });
    await expect(row).toHaveCount(1);
    for (const change of ['"radius":4', '"font":"Merriweather"', '"surface":{', '"accent":{']) await expect(row).toContainText(change);
  });

  test("an Owner chooses dark, automatic or light mode and an inline or bubble launcher, and the preview and saved Theme follow", async ({
    signedInPage: page,
  }) => {
    await openTheme(page);
    const mode = page.getByRole("radiogroup", { name: "Mode" });
    const launcher = page.getByRole("radiogroup", { name: "Launcher" });
    await expect(mode.getByRole("radio", { name: "Light" })).toBeChecked();
    await expect(launcher.getByRole("radio", { name: "Floating bubble" })).toBeChecked();

    // Dark: the preview shows the dark colours.
    await mode.getByRole("radio", { name: "Dark" }).check();
    await expect(preview(page, "dark")).toHaveAttribute("data-scheme", "dark");
    expect(await themeProperty(preview(page, "dark"), "--theme-primary")).toBe("#818cf8");

    // Automatic: the Owner previews either scheme.
    await mode.getByRole("radio", { name: "Automatic" }).check();
    const previewColours = page.getByRole("radiogroup", { name: "Preview colours" });
    await expect(previewColours).toBeVisible();
    await expect(preview(page, "light")).toBeVisible();
    await previewColours.getByRole("radio", { name: "Dark" }).check();
    await expect(preview(page, "dark")).toBeVisible();

    // Inline: no launcher or bubble corner, the chat sits in the page.
    await launcher.getByRole("radio", { name: "Inline container" }).check();
    await expect(page.getByRole("radiogroup", { name: "Bubble position" })).toHaveCount(0);
    await expect(preview(page, "dark").getByRole("button", { name: /chat/ })).toHaveCount(0);
    await expect(preview(page, "dark").getByRole("region", { name: "Chat with Assistant" })).toBeVisible();

    await page.getByRole("button", { name: "Save Theme" }).click();
    await expect(page.getByRole("status", { name: "Saved" })).toHaveText("Theme saved. The widget uses it now.");
    await page.reload();
    await expect(page.getByRole("radiogroup", { name: "Mode" }).getByRole("radio", { name: "Automatic" })).toBeChecked();
    await expect(page.getByRole("radiogroup", { name: "Launcher" }).getByRole("radio", { name: "Inline container" })).toBeChecked();
    const path = `/api/organisations/${await organisationId(page)}/theme`;
    expect(await (await page.request.get(path)).json()).toMatchObject({ mode: "auto", launcher_type: "inline" });

    // Back to a light bubble in the bottom-left corner.
    await page.getByRole("radiogroup", { name: "Mode" }).getByRole("radio", { name: "Light" }).check();
    await page.getByRole("radiogroup", { name: "Launcher" }).getByRole("radio", { name: "Floating bubble" }).check();
    await page.getByRole("radiogroup", { name: "Bubble position" }).getByRole("radio", { name: "Bottom left" }).check();
    await expect(page.getByRole("radiogroup", { name: "Preview colours" })).toHaveCount(0);
    await expect(preview(page).getByRole("button", { name: "Close chat" })).toHaveAttribute("data-position", "bottom-left");
    await page.getByRole("button", { name: "Save Theme" }).click();
    await expect(page.getByRole("status", { name: "Saved" })).toHaveText("Theme saved. The widget uses it now.");
    expect(await (await page.request.get(path)).json()).toMatchObject({
      mode: "light",
      launcher_type: "bubble",
      launcher_position: "bottom-left",
    });
  });
});
