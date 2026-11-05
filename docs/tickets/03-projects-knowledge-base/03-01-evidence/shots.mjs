// Screenshots of the 03-01 screens against the running sandbox stack. Usage: node shots.mjs <out-dir>
import { chromium } from "@playwright/test"; // run from frontend/ so the workspace's Playwright resolves
const OUT = process.argv[2];
const BASE = "http://localhost:45373";
const id = Math.random().toString(36).slice(2, 8);
const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome" });
const newPage = async () => (await browser.newContext({ baseURL: BASE, viewport: { width: 1100, height: 760 } })).newPage();
const owner = await newPage();
const signUp = await owner.request.post("/api/auth/sign-up", {
  data: { name: "Ada Lovelace", email: `ada-${id}@example.test`, password: "correct horse battery staple", organisation_name: "Analytical Engines" },
});
const orgId = (await signUp.json()).organisations[0].id;
const projects = `/api/organisations/${orgId}/projects`;
for (const [name, description] of [
  ["Sales enablement", "Decks, pricing and objection handling"],
  ["Product support", "Answers for customers"],
  ["Old launch", "The 2025 launch materials"],
]) {
  await owner.request.post(projects, { data: { name, description } });
}
const old = (await (await owner.request.get(projects)).json()).find((p) => p.name === "Old launch");
await owner.request.post(`${projects}/${old.id}/archive`);

// Create one through the Studio.
await owner.goto(`/organisations/${orgId}/projects`);
const form = owner.getByRole("form", { name: "New Project" });
await form.getByLabel("Name").fill("HR handbook");
await form.getByLabel("Description").fill("Policies for the HR Agent");
await owner.screenshot({ path: `${OUT}/studio-projects-list.png`, fullPage: true });
await form.getByRole("button", { name: "Create Project" }).click();
await owner.getByRole("heading", { level: 1, name: "HR handbook" }).waitFor();
await owner.screenshot({ path: `${OUT}/studio-project-documents-tab.png`, fullPage: true });
const tabs = owner.getByRole("navigation", { name: "Project" });
for (const tab of ["Instructions", "Agents", "Conversations", "Analytics"]) {
  await tabs.getByRole("link", { name: tab }).click();
  await owner.getByRole("heading", { level: 2, name: tab }).waitFor();
  await owner.screenshot({ path: `${OUT}/studio-project-${tab.toLowerCase()}-tab.png`, fullPage: true });
}
await owner.getByRole("button", { name: "Edit details" }).click();
await owner.getByRole("form", { name: "Project details" }).getByLabel("Name").fill("People team");
await owner.screenshot({ path: `${OUT}/studio-project-edit-details.png`, fullPage: true });
await owner.getByRole("button", { name: "Save" }).click();
await owner.getByRole("heading", { level: 1, name: "People team" }).waitFor();
await owner.getByRole("button", { name: "Archive" }).click();
await owner.screenshot({ path: `${OUT}/studio-project-archive-confirm.png`, fullPage: true });
await owner.getByRole("button", { name: "Yes, archive People team" }).click();
await owner.getByText(/This Project is archived/).waitFor();
await owner.screenshot({ path: `${OUT}/studio-project-archived-owner.png`, fullPage: true });
await owner.getByRole("link", { name: "All Projects" }).click();
await owner.getByRole("table", { name: "Projects" }).waitFor();
await owner.screenshot({ path: `${OUT}/studio-projects-after-archive.png`, fullPage: true });
await owner.getByRole("button", { name: "Show archived Projects" }).click();
await owner.getByRole("table", { name: "Archived Projects" }).waitFor();
await owner.screenshot({ path: `${OUT}/studio-archived-projects-owner.png`, fullPage: true });

// An Editor's view of an archived Project.
const invited = await owner.request.post(`/api/organisations/${orgId}/invites`, {
  data: { email: `grace-${id}@example.test`, role: "editor", send_email: false },
});
const token = new URL((await invited.json()).link).searchParams.get("token");
const editor = await newPage();
await editor.request.post("/api/invites/sign-up", { data: { token, name: "Grace Hopper", password: "a long enough password 42" } });
await editor.goto(`/organisations/${orgId}/projects/${old.id}`);
await editor.getByText("Only Owners can restore it.").waitFor();
await editor.screenshot({ path: `${OUT}/studio-project-archived-editor.png`, fullPage: true });

await owner.getByRole("button", { name: "Restore People team" }).click();
await owner.getByText("People team was restored.").waitFor();
await owner.screenshot({ path: `${OUT}/studio-project-restored.png`, fullPage: true });
await owner.goto(`/organisations/${orgId}/settings/audit`);
await owner.getByRole("table", { name: "Audit Events" }).getByRole("cell", { name: "project.restored" }).waitFor();
await owner.screenshot({ path: `${OUT}/studio-audit-project-events.png`, fullPage: true });
await browser.close();
