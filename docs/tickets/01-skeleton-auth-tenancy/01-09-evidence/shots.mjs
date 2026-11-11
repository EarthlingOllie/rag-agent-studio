// Screenshots of the 01-09 screens against the running sandbox stack. Usage: node shots.mjs <out-dir>
import { chromium } from "playwright"; // run with frontend/node_modules on NODE_PATH, or adjust to the local playwright install
const OUT = process.argv[2];
const BASE = "http://localhost:45173";
const id = Math.random().toString(36).slice(2, 8);
const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome" });
const newPage = async () => (await browser.newContext({ baseURL: BASE, viewport: { width: 1100, height: 760 } })).newPage();
const owner = await newPage();
const signUp = await owner.request.post("/api/auth/sign-up", {
  data: { name: "Ada Lovelace", email: `ada-${id}@example.test`, password: "correct horse battery staple", organisation_name: "Analytical Engines" },
});
const orgId = (await signUp.json()).organisations[0].id;
async function join(name, role) {
  const page = await newPage();
  const invited = await owner.request.post(`/api/organisations/${orgId}/invites`, {
    data: { email: `${name.split(" ")[0].toLowerCase()}-${id}@example.test`, role, send_email: false },
  });
  const token = new URL((await invited.json()).link).searchParams.get("token");
  await page.request.post("/api/invites/sign-up", { data: { token, name, password: "a long enough password 42" } });
  return page;
}
const grace = await join("Grace Hopper", "editor");
await join("Charles Babbage", "editor");
await owner.goto(`/organisations/${orgId}/settings/members`);
const members = owner.getByRole("table", { name: "Members" });
await members.waitFor();
await owner.screenshot({ path: `${OUT}/studio-members-list.png`, fullPage: true });
await owner.getByLabel("Role for Ada Lovelace").selectOption("Editor");
await owner.getByRole("alert").waitFor();
await owner.screenshot({ path: `${OUT}/studio-last-owner-refused.png`, fullPage: true });
await owner.getByLabel("Role for Grace Hopper").selectOption("Owner");
await owner.getByText("Grace Hopper is now an Owner.").waitFor();
await owner.screenshot({ path: `${OUT}/studio-role-changed.png`, fullPage: true });
await owner.getByLabel("Role for Grace Hopper").selectOption("Editor");
await owner.getByText("Grace Hopper is now an Editor.").waitFor();
await owner.getByRole("button", { name: "Remove Charles Babbage" }).click();
await owner.screenshot({ path: `${OUT}/studio-remove-confirm.png`, fullPage: true });
await owner.getByRole("button", { name: "Yes, remove Charles Babbage" }).click();
await owner.getByText("Charles Babbage was removed and can no longer open this Organisation.").waitFor();
await owner.screenshot({ path: `${OUT}/studio-member-removed.png`, fullPage: true });
// The Editor's view: no Owner-only tabs; then leaving.
await grace.goto(`/organisations/${orgId}/settings`);
await grace.getByRole("button", { name: "Leave Analytical Engines" }).waitFor();
await grace.screenshot({ path: `${OUT}/studio-editor-settings.png`, fullPage: true });
await grace.goto(`/organisations/${orgId}/settings/members`);
await grace.getByText("Only Owners can manage Members and invites.").waitFor();
await grace.screenshot({ path: `${OUT}/studio-editor-members-address.png`, fullPage: true });
await grace.goto(`/organisations/${orgId}/settings`);
await grace.getByRole("button", { name: "Leave Analytical Engines" }).click();
await grace.screenshot({ path: `${OUT}/studio-leave-confirm.png`, fullPage: true });
await grace.getByRole("button", { name: "Yes, leave Analytical Engines" }).click();
await grace.getByText("You don't belong to any Organisation yet.").waitFor();
await grace.screenshot({ path: `${OUT}/studio-after-leaving.png`, fullPage: true });
await owner.goto(`/organisations/${orgId}/settings/audit`);
await owner.getByRole("cell", { name: "member.left" }).waitFor();
await owner.screenshot({ path: `${OUT}/studio-audit-member-events.png`, fullPage: true });
await browser.close();
