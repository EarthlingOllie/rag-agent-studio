import { fileURLToPath } from "node:url";

import { expect, test } from "../fixtures";

/** The seed staff handbook (synthetic content), uploaded as an Editor would. */
const HANDBOOK = fileURLToPath(new URL("../../../seed/documents/northwind-staff-handbook.md", import.meta.url));

test.describe("Documents", () => {
  test("an Owner uploads the seed handbook and it goes from Queued to Ready", async ({ signedInPage: page, makeAxeBuilder }) => {
    await page.goto("/");
    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Projects" }).click();
    const form = page.getByRole("form", { name: "New Project" });
    await form.getByLabel("Name").fill("Northwind handbook");
    await form.getByRole("button", { name: "Create Project" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "Documents" })).toBeVisible();
    await expect(page.getByText(/No Documents yet/)).toBeVisible();

    // Presign, PUT straight to the object store (RustFS through the Studio's proxy), confirm.
    await page.getByLabel("Choose files to upload").setInputFiles(HANDBOOK);
    await expect(page.getByRole("list", { name: "Uploads" }).getByText("Uploaded")).toBeVisible();

    // The list polls the status endpoint until the Document is Ready, without a reload.
    const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /northwind-staff-handbook\.md/ });
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    const chunks = Number(await row.getByRole("cell").nth(2).textContent());
    expect(chunks).toBeGreaterThan(0);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The Project's Document count, and its Chunks through the API.
    await page.getByRole("link", { name: "All Projects" }).click();
    const projectRow = page.getByRole("row", { name: /Northwind handbook/ });
    await expect(projectRow.getByRole("cell", { name: "1", exact: true }).first()).toBeVisible();
  });
});
