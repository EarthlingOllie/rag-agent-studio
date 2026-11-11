// Screenshots of the 02-01 screens against the running sandbox stack (fake verifier, no real keys).
// Usage: NODE_PATH=<clone>/frontend/node_modules node shots.mjs <out-dir>
import { chromium } from "playwright";
const OUT = process.argv[2];
const BASE = "http://localhost:47173";
const id = Math.random().toString(36).slice(2, 8);
const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome" });
const newPage = async () => (await browser.newContext({ baseURL: BASE, viewport: { width: 1280, height: 860 } })).newPage();
const owner = await newPage();
const signUp = await owner.request.post("/api/auth/sign-up", {
  data: { name: "Ada Lovelace", email: `ada-${id}@example.test`, password: "correct horse battery staple", organisation_name: "Analytical Engines" },
});
const orgId = (await signUp.json()).organisations[0].id;
const shot = (page, name) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
await owner.goto(`/organisations/${orgId}/settings/credentials`);
await owner.getByText("No credentials yet.").waitFor();
await shot(owner, "studio-credentials-empty");
const form = owner.getByRole("region", { name: "Add a credential" });
async function add(provider, name, key) {
  await form.getByLabel("Provider").selectOption(provider);
  await form.getByLabel("Name").fill(name);
  await form.getByLabel("API key").fill(key);
  await form.getByRole("button", { name: "Check and save" }).click();
}
await add("OpenAI", "Marketing OpenAI", "fake-fail-invalid_key-demo-0000");
await owner.getByRole("alert").waitFor();
await shot(owner, "studio-add-check-failed");
await form.getByLabel("API key").fill("sk-proj-demo-not-a-real-key-wxyz");
await form.getByRole("button", { name: "Check and save" }).click();
await owner.getByText("Marketing OpenAI was checked and saved.").waitFor();
await add("Anthropic", "Legal Anthropic", "sk-ant-demo-not-a-real-key-abcd");
await owner.getByText("Legal Anthropic was checked and saved.").waitFor();
await add("Voyage AI", "Search embeddings", "pa-demo-not-a-real-key-9876");
await owner.getByText("Search embeddings was checked and saved.").waitFor();
await shot(owner, "studio-credentials-list");
await owner.getByRole("button", { name: "Check now: Legal Anthropic" }).click();
await owner.getByText("Legal Anthropic passed its check.").waitFor();
await shot(owner, "studio-recheck-passed");
await owner.getByRole("button", { name: "Rotate key: Marketing OpenAI" }).click();
await owner.getByLabel("New API key for Marketing OpenAI").fill("fake-fail-quota_exceeded-demo-1111");
await owner.getByRole("button", { name: "Check and rotate" }).click();
await owner.getByRole("alert").waitFor();
await shot(owner, "studio-rotate-check-failed");
await owner.getByLabel("New API key for Marketing OpenAI").fill("sk-proj-demo-rotated-key-n3w1");
await owner.getByRole("button", { name: "Check and rotate" }).click();
await owner.getByText("The key of Marketing OpenAI was checked and replaced.").waitFor();
await shot(owner, "studio-rotated");
await owner.getByRole("button", { name: "Delete: Search embeddings" }).click();
await shot(owner, "studio-delete-confirm");
await owner.getByRole("button", { name: "Yes, delete Search embeddings" }).click();
await owner.getByText("Search embeddings was deleted.").waitFor();
await shot(owner, "studio-deleted");
// The Editor's view.
const editor = await newPage();
const invited = await owner.request.post(`/api/organisations/${orgId}/invites`, {
  data: { email: `grace-${id}@example.test`, role: "editor", send_email: false },
});
const token = new URL((await invited.json()).link).searchParams.get("token");
await editor.request.post("/api/invites/sign-up", { data: { token, name: "Grace Hopper", password: "a long enough password 42" } });
await editor.goto(`/organisations/${orgId}/settings/credentials`);
await editor.getByText("Only Owners can add, check, rotate or delete credentials.").waitFor();
await shot(editor, "studio-editor-credentials");
// The Audit tab with the credential events.
await owner.goto(`/organisations/${orgId}/settings/audit`);
await owner.getByText("credential.deleted").first().waitFor();
await shot(owner, "studio-audit-credential-events");
await browser.close();
