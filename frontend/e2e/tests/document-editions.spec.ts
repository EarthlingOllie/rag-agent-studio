import { expect, test } from "../fixtures";
import { openSection } from "../fixtures/navigation";

/** A small handbook, uploaded from memory so each run has its own content. */
function handbook(name: string, body: string) {
  return { name, mimeType: "text/markdown", buffer: Buffer.from(`# Handbook\n\n${body}\n`) };
}

test.describe("Document editions", () => {
  test("a duplicate is refused, a new edition replaces the Document in place, and delete removes it", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    const form = page.getByRole("form", { name: "New Project" });
    await form.getByLabel("Name").fill("Editions");
    await form.getByRole("button", { name: "Create Project" }).click();
    await expect(page.getByText(/No Documents yet/)).toBeVisible();
    const table = page.getByRole("table", { name: "Documents" });

    // Upload, then the identical file again: refused, with a link to the existing Document.
    const first = handbook("handbook-2026.md", `Everyone gets 25 days of annual leave. ${String(Date.now())}`);
    await page.getByLabel("Choose files to upload").setInputFiles(first);
    const row = table.getByRole("row", { name: /handbook-2026\.md/ });
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    await page.getByLabel("Choose files to upload").setInputFiles({ ...first, name: "copy.md" });
    const refusal = page.getByRole("alert");
    await expect(refusal).toContainText("This file is already in the Project as handbook-2026.md.");
    await refusal.getByRole("link", { name: "Show handbook-2026.md" }).click();
    await expect(page).toHaveURL(/#document-/);
    await expect(table.getByRole("row")).toHaveCount(2);

    // A new edition replaces it in place.
    await row.getByLabel("New edition of handbook-2026.md").setInputFiles(
      handbook("handbook-2027.md", `Everyone gets 28 days of annual leave. ${String(Date.now())}`),
    );
    const replaced = table.getByRole("row", { name: /handbook-2027\.md/ });
    await expect(replaced.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    await expect(replaced).not.toContainText("New edition 2");
    await expect(table.getByRole("row")).toHaveCount(2);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // Delete, after confirming.
    await replaced.getByRole("button", { name: "Delete handbook-2027.md" }).click();
    await page.getByRole("group", { name: "Delete handbook-2027.md?" }).getByRole("button", { name: "Delete" }).click();
    await expect(page.getByText(/No Documents yet/)).toBeVisible();
  });
});
