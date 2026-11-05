// Sandbox-only: screenshots of the Documents tab against the running stack.
import { chromium } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL;
const OUT = process.env.SHOTS_DIR;
const HANDBOOK = process.env.HANDBOOK;
const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome" });
const page = await browser.newPage({ baseURL: BASE, viewport: { width: 1280, height: 800 } });
const suffix = Date.now();
await page.request.post("/api/auth/sign-up", {
  data: { name: "Ada Editor", email: `ada-${suffix}@example.test`, password: "correct horse battery", organisation_name: "Northwind" },
});
await page.goto("/");
await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Projects" }).click();
const form = page.getByRole("form", { name: "New Project" });
await form.getByLabel("Name").fill("Northwind handbook");
await form.getByRole("button", { name: "Create Project" }).click();
await page.getByText(/No Documents yet/).waitFor();
await page.screenshot({ path: `${OUT}/studio-documents-empty.png`, fullPage: true });
await page.getByLabel("Choose files to upload").setInputFiles(HANDBOOK);
await page.getByRole("list", { name: "Uploads" }).getByText("Uploaded").waitFor();
await page.screenshot({ path: `${OUT}/studio-documents-queued.png`, fullPage: true });
await page.getByRole("cell", { name: "Ready" }).waitFor({ timeout: 60000 });
await page.screenshot({ path: `${OUT}/studio-documents-ready.png`, fullPage: true });
await page.getByLabel("Choose files to upload").setInputFiles({ name: "sheet.xlsx", mimeType: "application/vnd.ms-excel", buffer: Buffer.from("x") });
await page.getByRole("alert").waitFor();
await page.screenshot({ path: `${OUT}/studio-documents-refused.png`, fullPage: true });
const projectId = page.url().split("/projects/")[1];
const orgId = page.url().split("/organisations/")[1].split("/")[0];
const docs = await (await page.request.get(`/api/organisations/${orgId}/projects/${projectId}/documents`)).json();
const chunks = await (await page.request.get(`/api/organisations/${orgId}/projects/${projectId}/documents/${docs[0].id}/chunks`)).json();
console.log(JSON.stringify({ documents: docs, chunks }, null, 1));
await browser.close();
