// Screenshots of the 02-02 screens against the running sandbox stack (fake verifier; no AWS account,
// made-up ARNs and AWS's documentation example access key).
// Usage: NODE_PATH=<clone>/frontend/node_modules node shots.mjs <out-dir>
import { chromium } from "playwright";
const OUT = process.argv[2];
const BASE = "http://localhost:51173";
const id = Math.random().toString(36).slice(2, 8);
const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome" });
const page = await (await browser.newContext({ baseURL: BASE, viewport: { width: 1280, height: 900 } })).newPage();
const signUp = await page.request.post("/api/auth/sign-up", {
  data: { name: "Ada Lovelace", email: `ada-${id}@example.test`, password: "correct horse battery staple", organisation_name: "Analytical Engines" },
});
const orgId = (await signUp.json()).organisations[0].id;
const shot = (name) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
await page.goto(`/organisations/${orgId}/settings/credentials`);
await page.getByText("No credentials yet.").waitFor();
const form = page.getByRole("region", { name: "Add a credential" });
await form.getByLabel("Provider").selectOption("Amazon Bedrock");
await form.getByRole("region", { name: "Set up the role in AWS" }).getByLabel("Trust policy").waitFor();
await shot("studio-bedrock-role-setup");
await form.getByLabel("Name").fill("Bedrock prod");
await form.getByLabel("AWS region").fill("eu-west-2");
for (const reason of ["role_not_assumable", "missing_model_access", "wrong_region"]) {
  await form.getByLabel("Role ARN").fill(`arn:aws:iam::111122223333:role/fake-fail-${reason}`);
  await form.getByRole("button", { name: "Check and save" }).click();
  await page.getByRole("alert").waitFor();
  await page.getByRole("alert").scrollIntoViewIfNeeded();
  await shot(`studio-bedrock-failed-${reason.replaceAll("_", "-")}`);
}
await form.getByLabel("Role ARN").fill("arn:aws:iam::111122223333:role/StudioBedrockAccess");
await form.getByRole("button", { name: "Check and save" }).click();
await page.getByText("Bedrock prod was checked and saved.").waitFor();
await form.getByLabel("Access keys").check();
await shot("studio-bedrock-access-keys");
await form.getByLabel("Name").fill("Bedrock sandbox");
await form.getByLabel("Access key ID").fill("AKIAIOSFODNN7EXAMPLE");
await form.getByLabel("Secret access key").fill("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY");
await form.getByLabel("AWS region").fill("us-east-1");
await form.getByRole("button", { name: "Check and save" }).click();
await page.getByText("Bedrock sandbox was checked and saved.").waitFor();
await shot("studio-bedrock-credentials-list");
await browser.close();
