// Screenshots of the 02-03 screens against the running sandbox stack (fake verifier and fake
// model gateway, no real keys). Usage: NODE_PATH=<clone>/frontend/node_modules node shots.mjs <out-dir>
import { chromium } from "@playwright/test";
const OUT = process.argv[2];
const BASE = "http://localhost:51173";
const id = Math.random().toString(36).slice(2, 8);
const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome" });
const newPage = async () => (await browser.newContext({ baseURL: BASE, viewport: { width: 1280, height: 860 } })).newPage();
const owner = await newPage();
const signUp = await owner.request.post("/api/auth/sign-up", {
  data: { name: "Ada Lovelace", email: `ada-${id}@example.test`, password: "correct horse battery staple", organisation_name: "Analytical Engines" },
});
const orgId = (await signUp.json()).organisations[0].id;
const shot = (page, name) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });

await owner.goto(`/organisations/${orgId}/settings/models`);
await owner.getByText(/No credential can be used for chat yet/).waitFor();
await shot(owner, "studio-models-no-chat-credential");

await owner.goto(`/organisations/${orgId}/settings/credentials`);
const form = owner.getByRole("region", { name: "Add a credential" });
async function add(provider, name, key) {
  await form.getByLabel("Provider").selectOption(provider);
  await form.getByLabel("Name").fill(name);
  await form.getByLabel("API key").fill(key);
  await form.getByRole("button", { name: "Check and save" }).click();
  await owner.getByText(`${name} was checked and saved.`).waitFor();
}
await add("Voyage AI", "Search embeddings", "pa-demo-not-a-real-key-9876");
await add("Anthropic", "Support Claude", "sk-ant-demo-not-a-real-key-abcd");
await add("OpenAI", "Marketing OpenAI", "sk-proj-demo-not-a-real-key-wxyz");

await owner.goto(`/organisations/${orgId}/settings/models`);
const picker = owner.getByRole("form", { name: "Choose the Default Model" });
// Chat-capable credentials only, by name: Marketing OpenAI comes first, with its chat models.
await picker.getByRole("option", { name: "GPT-4.1 mini" }).waitFor({ state: "attached" });
await shot(owner, "studio-models-picker");
await picker.getByLabel("Model").selectOption("GPT-4.1 mini");
await picker.getByRole("button", { name: "Save Default Model" }).click();
await owner.getByRole("status").waitFor();
await shot(owner, "studio-models-saved");

await owner.goto(`/organisations/${orgId}/settings/credentials`);
await owner.getByRole("button", { name: "Delete: Marketing OpenAI" }).click();
await owner.getByRole("button", { name: "Yes, delete Marketing OpenAI" }).click();
await owner.getByText("Default Model (GPT-4.1 mini)").waitFor();
await shot(owner, "studio-delete-blocked-by-default-model");

await owner.goto(`/organisations/${orgId}/settings/audit`);
await owner.getByRole("cell", { name: "default_model.changed" }).first().waitFor();
await shot(owner, "studio-audit-default-model-changed");
await browser.close();
