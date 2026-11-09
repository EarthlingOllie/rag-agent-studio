import { fileURLToPath } from "node:url";

import { expect, test } from "../fixtures";
import { openSection } from "../fixtures/navigation";

/** The seed staff handbook (synthetic content), uploaded as an Editor would. */
const HANDBOOK = fileURLToPath(new URL("../../../seed/documents/northwind-staff-handbook.md", import.meta.url));

test.describe("Permanent Project deletion", () => {
  test("an Owner deletes an archived Project after typing its name, and its stored files go too", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    const form = page.getByRole("form", { name: "New Project" });
    await form.getByLabel("Name").fill("Retired handbook");
    await form.getByRole("button", { name: "Create Project" }).click();
    await page.getByLabel("Upload", { exact: true }).setInputFiles(HANDBOOK);
    const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /northwind-staff-handbook\.md/ });
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });

    // Where the original is stored: the presigned download URL the API redirects to.
    const projectApi = new URL(page.url()).pathname.replace(/^\//, "/api/");
    const documents = (await (await page.request.get(`${projectApi}/documents`)).json()) as { id: string }[];
    const download = await page.request.get(`${projectApi}/documents/${documents[0]?.id ?? ""}/download`, { maxRedirects: 0 });
    const stored = download.headers().location ?? "";
    expect((await page.request.get(stored)).status()).toBe(200);

    // Only an archived Project offers permanent deletion, in the page header's ⋯ menu.
    const actions = page.getByRole("menu", { name: "Project actions" });
    await page.getByRole("button", { name: "More Project actions" }).click();
    await expect(actions.getByRole("menuitem")).toHaveText(["Archive"]);
    await actions.getByRole("menuitem", { name: "Archive" }).click();
    await page.getByRole("button", { name: "Yes, archive Retired handbook" }).click();
    await expect(page.getByText(/This Project is archived/)).toBeVisible();
    await page.getByRole("button", { name: "More Project actions" }).click();
    await actions.getByRole("menuitem", { name: "Delete permanently" }).click();
    const confirm = page.getByRole("alertdialog", { name: "Delete Retired handbook permanently" });
    const button = confirm.getByRole("button", { name: "Delete Retired handbook permanently" });
    await confirm.getByLabel("Type Retired handbook to confirm").fill("retired handbook");
    await expect(button).toBeDisabled();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await confirm.getByLabel("Type Retired handbook to confirm").fill("Retired handbook");
    await button.click();

    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
    await expect(page.getByText("Retired handbook is being deleted permanently.")).toBeVisible();
    // The worker's cascade removes the Project, then its stored files.
    await expect.poll(async () => (await page.request.get(projectApi)).status(), { timeout: 30_000 }).toBe(404);
    await expect.poll(async () => (await page.request.get(stored)).status(), { timeout: 30_000 }).toBe(404);
    await page.getByRole("button", { name: "Show archived Projects" }).click();
    await expect(page.getByText("No archived Projects.")).toBeVisible();

    // The deletion is in the Audit tab.
    await openSection(page, "Organisation sections", "Settings");
    await openSection(page, "Organisation settings", "Audit");
    await expect(page.getByRole("table", { name: "Audit Events" }).getByRole("cell", { name: "project.deleted" })).toHaveCount(1);
  });
});
