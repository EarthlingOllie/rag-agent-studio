// Sandbox-only: screenshots of the Settings tab (OCR) and the Documents tab (Retry) against the
// running e2e stack. Run from frontend/: E2E_BASE_URL=... SHOTS_DIR=... HANDBOOK=... node <this>
import { chromium } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL;
const OUT = process.env.SHOTS_DIR;
const HANDBOOK = process.env.HANDBOOK;
const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome" });
const page = await browser.newPage({ baseURL: BASE, viewport: { width: 1280, height: 800 } });
await page.request.post("/api/auth/sign-up", {
  data: { name: "Ada Editor", email: `ada-${Date.now()}@example.test`, password: "correct horse battery", organisation_name: "Northwind" },
});
await page.goto("/");
await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Projects" }).click();
const form = page.getByRole("form", { name: "New Project" });
await form.getByLabel("Name").fill("Scanned contracts");
await form.getByRole("button", { name: "Create Project" }).click();
await page.getByLabel("Choose files to upload").setInputFiles(HANDBOOK);
const row = page.getByRole("row", { name: /northwind-staff-handbook/ });
await row.getByRole("cell", { name: /Ready/ }).waitFor({ timeout: 60000 });
const tabs = page.getByRole("navigation", { name: "Project" });
await tabs.getByRole("link", { name: "Settings" }).click();
await page.screenshot({ path: `${OUT}/studio-settings-ocr-off.png`, fullPage: true });
await page.getByRole("checkbox", { name: "Read scanned PDFs with OCR" }).check();
await page.getByText(/OCR is on\./).waitFor();
await page.screenshot({ path: `${OUT}/studio-settings-ocr-on.png`, fullPage: true });
await tabs.getByRole("link", { name: "Documents" }).click();
await row.getByRole("button", { name: /Retry/ }).waitFor();
await page.screenshot({ path: `${OUT}/studio-documents-retry.png`, fullPage: true });
await browser.close();
