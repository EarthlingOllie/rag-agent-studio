// Screenshots of the Require MFA policy from the running stack. Run from the frontend folder:
//   STUDIO=http://localhost:45273 OUT=<dir> node shots.mjs
import { createHmac, randomUUID } from "node:crypto";
import { chromium } from "@playwright/test";

const STUDIO = process.env.STUDIO ?? "http://localhost:45273";
const OUT = process.env.OUT ?? ".";
const B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
function totp(secret, step) {
  let bits = "";
  for (const c of secret) bits += B32.indexOf(c).toString(2).padStart(5, "0");
  const bytes = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(step));
  const d = createHmac("sha1", Buffer.from(bytes)).update(counter).digest();
  const o = d[d.length - 1] & 0x0f;
  return String((d.readUInt32BE(o) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}
const step = () => Math.floor(Date.now() / 30_000);

const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH });
const suffix = randomUUID().slice(0, 8);
const owner = { name: "Ada Owner", email: `ada-${suffix}@example.test`, password: `correct horse ${suffix}`, organisation_name: "Analytical Engines" };
const editor = { name: "Grace Editor", email: `grace-${suffix}@example.test`, password: `battery staple ${suffix}` };

const ownerPage = await (await browser.newContext({ baseURL: STUDIO, viewport: { width: 1200, height: 800 } })).newPage();
await ownerPage.request.post("/api/auth/sign-up", { data: owner });
const me = await (await ownerPage.request.get("/api/auth/me")).json();
const org = me.organisations[0].id;
const enrolled = await (await ownerPage.request.post("/api/auth/mfa/enrolment")).json();
await ownerPage.request.post("/api/auth/mfa/enrolment/confirm", { data: { code: totp(enrolled.secret, step()) } });
const invite = await (await ownerPage.request.post(`/api/organisations/${org}/invites`, { data: { email: editor.email, role: "editor", send_email: false } })).json();
const token = invite.link.split("token=")[1];

const editorPage = await (await browser.newContext({ baseURL: STUDIO, viewport: { width: 1200, height: 800 } })).newPage();
await editorPage.request.post("/api/invites/sign-up", { data: { token, name: editor.name, password: editor.password } });

await ownerPage.goto(`/organisations/${org}/settings`);
await ownerPage.getByRole("button", { name: "Require two-factor authentication" }).waitFor();
await ownerPage.screenshot({ path: `${OUT}/studio-policy-off.png` });
await ownerPage.getByRole("button", { name: "Require two-factor authentication" }).click();
await ownerPage.getByRole("button", { name: "Stop requiring two-factor authentication" }).waitFor();
await ownerPage.screenshot({ path: `${OUT}/studio-policy-on.png` });

await editorPage.goto(`/organisations/${org}/projects`);
await editorPage.getByText("requires two-factor authentication. Set it up to continue.").waitFor();
await editorPage.screenshot({ path: `${OUT}/studio-editor-must-enrol.png` });
await editorPage.getByRole("button", { name: "Set up two-factor authentication" }).click();
const secret = (await editorPage.locator("code").textContent()) ?? "";
const s = step();
await editorPage.getByLabel("Code from your app").fill(totp(secret, s));
await editorPage.getByRole("button", { name: "Turn on" }).click();
await editorPage.getByRole("button", { name: "I've saved my recovery codes" }).click();
await editorPage.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Projects" }).click();
await editorPage.getByRole("heading", { name: "Projects" }).waitFor();
await editorPage.screenshot({ path: `${OUT}/studio-editor-after-enrolling.png` });
await editorPage.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Security" }).click();
const turnOff = editorPage.getByRole("form", { name: "Turn off two-factor authentication" });
await turnOff.getByLabel("Password").fill(editor.password);
await turnOff.getByLabel("Code from your app or a recovery code").fill(totp(secret, s + 1));
await turnOff.getByRole("button", { name: "Turn off" }).click();
await turnOff.getByRole("alert").waitFor();
await turnOff.screenshot({ path: `${OUT}/studio-disable-refused.png` });

await ownerPage.goto(`/organisations/${org}/settings/audit`);
await ownerPage.getByRole("cell", { name: "organisation.mfa_policy_changed" }).waitFor();
await ownerPage.screenshot({ path: `${OUT}/studio-audit-policy-change.png`, fullPage: true });
await browser.close();
