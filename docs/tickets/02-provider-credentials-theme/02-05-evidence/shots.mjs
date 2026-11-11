// Screenshots of the Theme tab from the running stack (http://localhost:55173). Run from frontend/ of the clone.
import { chromium } from "@playwright/test";

const BASE = process.env.BASE ?? "http://localhost:55173";
const OUT = process.argv[2];
const id = Math.random().toString(16).slice(2, 10);
const owner = { name: "Ada Lovelace", email: `ada-${id}@example.test`, password: `correct horse ${id}`, organisation_name: "Analytical Engines" };

const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH });
const context = await browser.newContext({ baseURL: BASE, viewport: { width: 1400, height: 1500 } });
const page = await context.newPage();
await page.request.post("/api/auth/sign-up", { data: owner });
const me = await (await page.request.get("/api/auth/me")).json();
const org = me.organisations[0].id;
const shot = (name) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });

await page.goto(`/organisations/${org}/settings/theme`);
await page.getByRole("form", { name: "Theme" }).waitFor();
await shot("studio-theme-default");

await page.getByLabel("Primary (light)", { exact: true }).fill("#b91c1c");
await page.getByLabel("Corner radius (px)").fill("4");
await page.getByLabel("Font").selectOption("Merriweather");
await page.getByLabel("Text on primary (light)", { exact: true }).fill("#f87171");
await page.getByRole("status", { name: "Contrast" }).getByRole("listitem").first().waitFor();
await shot("studio-theme-contrast-warning");

await page.getByLabel("Text on primary (light)", { exact: true }).fill("#ffffff");
await page.getByRole("radio", { name: "Automatic" }).check();
await page.getByRole("radiogroup", { name: "Preview colours" }).getByRole("radio", { name: "Dark" }).check();
await page.getByRole("radio", { name: "Bottom left" }).check();
await page.getByRole("button", { name: "Save Theme" }).click();
await page.getByRole("status", { name: "Saved" }).waitFor();
await shot("studio-theme-saved-auto-dark-preview");

await page.getByRole("radio", { name: "Inline container" }).check();
await shot("studio-theme-inline-launcher");
await page.getByRole("button", { name: "Save Theme" }).click();
await page.getByRole("status", { name: "Saved" }).waitFor();

await page.goto(`/organisations/${org}/settings/audit`);
await page.getByRole("cell", { name: "theme.updated" }).first().waitFor();
await shot("studio-audit-theme-events");

// An Editor's read-only view.
const invite = await (await page.request.post(`/api/organisations/${org}/invites`, { data: { email: `grace-${id}@example.test`, role: "editor", send_email: false } })).json();
const token = new URL(invite.link).searchParams.get("token");
const editor = await (await browser.newContext({ baseURL: BASE, viewport: { width: 1400, height: 1500 } })).newPage();
await editor.request.post("/api/invites/sign-up", { data: { token, name: "Grace Hopper", password: `correct horse ${id}` } });
await editor.goto(`/organisations/${org}/settings/theme`);
await editor.getByText("Only Owners can change the Theme.").waitFor();
await editor.screenshot({ path: `${OUT}/studio-theme-editor-read-only.png`, fullPage: true });
await browser.close();
