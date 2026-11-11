import { expect, test } from "../fixtures";
import { quota, rowAction } from "../fixtures/documents";
import { openSection } from "../fixtures/navigation";

test.describe("Ingestion failures", () => {
  test("an unsupported file is refused before upload, and a broken one fails with its category and can be retried", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    await page.getByRole("button", { name: "New Project" }).click();
    const form = page.getByRole("form", { name: "New Project" });
    await form.getByLabel("Name").fill("Broken files");
    await form.getByRole("button", { name: "Create Project" }).click();
    await expect(quota(page)).toHaveText("0 / 500");

    // Refused in the browser: nothing is uploaded.
    await page.getByLabel("Upload", { exact: true }).setInputFiles({ name: "sheet.xlsx", mimeType: "application/octet-stream", buffer: Buffer.from("PK") });
    await expect(page.getByRole("list", { name: "Uploads" }).getByRole("alert")).toHaveText(
      "This file type isn't supported. Upload a PDF, DOCX, PPTX, HTML, Markdown or TXT file.",
    );
    await expect(page.getByText(/No Documents yet/)).toBeVisible();

    // A ".pdf" that isn't a PDF uploads, then fails as unsupported content in the worker.
    await page.getByLabel("Upload", { exact: true }).setInputFiles({ name: "broken.pdf", mimeType: "application/pdf", buffer: Buffer.from("not a pdf") });
    const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /broken\.pdf/ });
    await expect(row.getByText("Unsupported content")).toBeVisible({ timeout: 60_000 });
    await expect(row.getByText("This file isn't a valid PDF file. Check the file, then upload it again.")).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // Retrying processes it again from the stored file; it is still not a PDF, so it fails again.
    await rowAction(page, "broken.pdf", "Retry");
    await expect(page.getByText("Retrying broken.pdf.")).toBeVisible();
    await expect(row.getByText("Unsupported content")).toBeVisible({ timeout: 60_000 });
    await expect(quota(page)).toHaveText("0 / 500");
  });
});
