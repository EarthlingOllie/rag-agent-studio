import { fileURLToPath } from "node:url";

import { expect, test } from "../fixtures";
import { rowAction } from "../fixtures/documents";
import { openSection } from "../fixtures/navigation";

const HANDBOOK = fileURLToPath(new URL("../../../seed/documents/northwind-staff-handbook.md", import.meta.url));
const OCR = "Read scanned PDFs with OCR";

test.describe("OCR toggle", () => {
  test("an Owner turns OCR on for a Project and reprocesses a Document with it through retry", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    // Two ingestion runs (upload, then retry) through the worker.
    test.slow();
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    const form = page.getByRole("form", { name: "New Project" });
    await form.getByLabel("Name").fill("Scanned contracts");
    await form.getByRole("button", { name: "Create Project" }).click();
    await page.getByLabel("Upload", { exact: true }).setInputFiles(HANDBOOK);
    const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /northwind-staff-handbook\.md/ });
    await expect(row.getByRole("cell", { name: /Ready/ })).toBeVisible({ timeout: 60_000 });

    // OCR is off by default; turning it on is saved on the Project.
    await openSection(page, "Project sections", "Settings");
    const ocr = page.getByRole("checkbox", { name: OCR });
    await expect(ocr).not.toBeChecked();
    await ocr.check();
    await expect(page.getByText(/OCR is on\. New uploads are read with OCR/)).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await page.reload();
    await expect(page.getByRole("checkbox", { name: OCR })).toBeChecked();

    // Retry sends the existing Document through ingestion again, with OCR on.
    await openSection(page, "Project sections", "Documents");
    await rowAction(page, "northwind-staff-handbook.md", "Retry");
    await expect(row.getByRole("cell", { name: /Ready/ })).toBeVisible({ timeout: 60_000 });
    // Cells: Select, Name, Type, Tags, Status, Chunks.
    expect(Number(await row.getByRole("cell").nth(5).textContent())).toBeGreaterThan(0);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });
});
