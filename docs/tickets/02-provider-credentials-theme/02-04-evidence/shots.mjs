// Screenshots of the 02-04 screens against the running sandbox stack (fake verifier, no real
// keys). Usage: NODE_PATH=<clone>/frontend/node_modules node shots.mjs <out-dir>
import { chromium } from "@playwright/test";
const OUT = process.argv[2];
const BASE = "http://localhost:52173";
const id = Math.random().toString(36).slice(2, 8);
const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome" });
const newContext = () => browser.newContext({ baseURL: BASE, viewport: { width: 1280, height: 900 } });
const owner = await (await newContext()).newPage();
const password = "correct horse battery staple";
const signUp = await owner.request.post("/api/auth/sign-up", {
  data: { name: "Ada Lovelace", email: `ada-${id}@example.test`, password, organisation_name: "Analytical Engines" },
});
const orgId = (await signUp.json()).organisations[0].id;
const shot = (page, name) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });

await owner.goto(`/organisations/${orgId}/settings/credentials`);
const form = owner.getByRole("region", { name: "Add a credential" });
async function add(provider, name, key) {
  await form.getByLabel("Provider").selectOption(provider);
  await form.getByLabel("Name").fill(name);
  await form.getByLabel("API key").fill(key);
  await form.getByRole("button", { name: "Check and save" }).click();
  await owner.getByText(`${name} was checked and saved.`).waitFor();
}
await add("Anthropic", "Negotiated Claude", "sk-ant-demo-not-a-real-key-abcd");
await add("OpenAI", "Marketing OpenAI", "sk-proj-demo-not-a-real-key-wxyz");

// The platform price table for the first credential by name.
await owner.goto(`/organisations/${orgId}/settings/models`);
await owner.getByRole("table", { name: "Prices for Marketing OpenAI" }).waitFor();
await owner.getByLabel("Show prices for").selectOption("Negotiated Claude");
const table = owner.getByRole("table", { name: "Prices for Negotiated Claude" });
await table.waitFor();
await shot(owner, "studio-prices-platform");

// An override, being entered.
await owner.getByRole("button", { name: "Override prices: Claude Sonnet 4.5" }).click();
const override = owner.getByRole("form", { name: "Override prices for Claude Sonnet 4.5" });
await override.getByLabel("Input", { exact: true }).fill("2.25");
await override.getByLabel("Output", { exact: true }).fill("11.5");
await shot(owner, "studio-prices-override-form");
await override.getByRole("button", { name: "Save prices" }).click();
await owner.getByRole("status").waitFor();
await shot(owner, "studio-prices-overridden");

// A price that isn't one.
await owner.getByRole("button", { name: "Override prices: Claude Haiku 4.5" }).click();
const haiku = owner.getByRole("form", { name: "Override prices for Claude Haiku 4.5" });
await haiku.getByLabel("Cached input").fill("-0.1");
await haiku.getByRole("button", { name: "Save prices" }).click();
await haiku.getByRole("alert").waitFor();
await shot(owner, "studio-prices-invalid");

// An Editor sees the prices with the override, and cannot change them.
const invite = await owner.request.post(`/api/organisations/${orgId}/invites`, {
  data: { email: `grace-${id}@example.test`, role: "editor", send_email: false },
});
const token = (await invite.json()).link.split("token=")[1];
const editor = await (await newContext()).newPage();
await editor.request.post("/api/invites/sign-up", { data: { token, name: "Grace Hopper", password } });
await editor.goto(`/organisations/${orgId}/settings/models`);
await editor.getByLabel("Show prices for").selectOption("Negotiated Claude");
await editor.getByRole("table", { name: "Prices for Negotiated Claude" }).waitFor();
await shot(editor, "studio-prices-editor");

await owner.goto(`/organisations/${orgId}/settings/audit`);
await owner.getByRole("cell", { name: "credential.price_overridden" }).first().waitFor();
await shot(owner, "studio-audit-price-overridden");
await browser.close();
