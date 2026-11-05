// Screenshots of the switcher, against the stack from compose.sandbox.yml. Usage: node shots.mjs <out dir>
import { chromium } from "/tmp/claude-0/-home-user-rag-agent-studio/6b18ab77-5c70-5cfd-b109-1e70fc51c71e/scratchpad/clean0110/frontend/node_modules/.pnpm/playwright@1.64.1/node_modules/playwright/index.mjs";
const OUT = process.argv[2];
const BASE = "http://localhost:55173";
const id = Math.random().toString(36).slice(2, 8);
const ada = { name: "Ada Lovelace", email: `ada-${id}@example.test`, password: "correct horse battery staple", organisation_name: "Analytical Engines" };
const charles = { name: "Charles Babbage", email: `charles-${id}@example.test`, password: "correct horse battery staple", organisation_name: "Difference Engines" };
const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome" });
const ctx = await browser.newContext({ baseURL: BASE, viewport: { width: 1100, height: 560 } });
const other = await browser.newContext({ baseURL: BASE });
const page = await ctx.newPage();
const adaOrg = (await (await page.request.post("/api/auth/sign-up", { data: ada })).json()).organisations[0].id;
const charlesOrg = (await (await other.request.post("/api/auth/sign-up", { data: charles })).json()).organisations[0].id;
await page.request.post(`/api/organisations/${adaOrg}/invites`, { data: { email: `grace-${id}@example.test`, role: "editor", send_email: false } });
await other.request.post(`/api/organisations/${charlesOrg}/invites`, { data: { email: `lovelace-team-${id}@example.test`, role: "editor", send_email: false } });
const { link } = await (await other.request.post(`/api/organisations/${charlesOrg}/invites`, { data: { email: ada.email, role: "owner", send_email: false } })).json();
await page.request.post("/api/invites/accept", { data: { token: new URL(link).searchParams.get("token") } });

await page.goto(`/organisations/${adaOrg}/settings/members`);
await page.getByRole("table", { name: "Pending invites" }).waitFor();
await page.screenshot({ path: `${OUT}/studio-switcher-first-organisation.png`, fullPage: true });
// A <select>'s open list isn't drawn in headless screenshots; show its options inline instead.
await page.getByRole("combobox", { name: "Organisation" }).evaluate((select) => { select.size = 2; });
await page.screenshot({ path: `${OUT}/studio-switcher-options.png`, clip: { x: 0, y: 0, width: 1100, height: 120 } });
await page.locator("#organisation-switcher").evaluate((select) => { select.size = 0; });
await page.getByRole("combobox", { name: "Organisation" }).selectOption({ label: "Difference Engines" });
await page.waitForURL(`**/organisations/${charlesOrg}/projects`);
await page.getByRole("link", { name: "Organisation settings" }).click();
await page.getByRole("link", { name: "Members" }).click();
await page.getByRole("table", { name: "Pending invites" }).waitFor();
await page.screenshot({ path: `${OUT}/studio-switcher-second-organisation.png`, fullPage: true });
await page.goto("/");
await page.waitForURL(`**/organisations/${charlesOrg}/projects`);
await page.screenshot({ path: `${OUT}/studio-switcher-remembered-after-reload.png`, fullPage: true });
await browser.close();
