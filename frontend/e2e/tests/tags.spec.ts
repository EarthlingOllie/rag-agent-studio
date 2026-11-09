import type { Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { openSection } from "../fixtures/navigation";

function markdown(name: string, text: string) {
  return { name, mimeType: "text/markdown", buffer: Buffer.from(text) };
}

function row(page: Page, name: string) {
  return page.getByRole("table", { name: "Documents" }).getByRole("row", { name: new RegExp(name.replace(".", "\\.")) });
}

async function documentNames(page: Page) {
  const rows = page.getByRole("table", { name: "Documents" }).getByRole("row");
  const names = await rows.evaluateAll((all) => all.slice(1).map((r) => r.querySelectorAll("td")[1]?.textContent ?? ""));
  return names.sort();
}

test.describe("Tags", () => {
  test("an Editor organises Documents with Tags and filters the list by name, status and Tag", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    // A long journey: three uploads through the real worker, then every Tag action and filter.
    test.slow();
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    const form = page.getByRole("form", { name: "New Project" });
    await form.getByLabel("Name").fill("Tagged handbook");
    await form.getByRole("button", { name: "Create Project" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "Documents" })).toBeVisible();

    await page
      .getByLabel("Choose files to upload")
      .setInputFiles([
        markdown("leave-policy.md", "# Leave\n\nEveryone gets 25 days of annual leave."),
        markdown("expenses.md", "# Expenses\n\nClaim expenses within 30 days."),
        markdown("sales-deck.md", "# Sales\n\nOur pitch."),
      ]);
    for (const name of ["leave-policy.md", "expenses.md", "sales-deck.md"]) {
      await expect(row(page, name).getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    }

    // Create Tags.
    const tags = page.getByRole("region", { name: "Tags" });
    for (const name of ["HR", "Policy", "Sales"]) {
      await tags.getByLabel("New Tag").fill(name);
      await tags.getByRole("button", { name: "Add Tag" }).click();
      await expect(tags.getByTestId("tag-name").filter({ hasText: name })).toBeVisible();
    }
    await tags.getByLabel("New Tag").fill("hr");
    await tags.getByRole("button", { name: "Add Tag" }).click();
    await expect(tags.getByRole("alert")).toHaveText("This Project already has a Tag with that name.");

    // Several Tags on one Document.
    await row(page, "leave-policy.md").getByRole("button", { name: "Edit Tags for leave-policy.md" }).click();
    const editor = page.getByRole("group", { name: "Tags for leave-policy.md" });
    await editor.getByRole("checkbox", { name: "HR" }).check();
    await editor.getByRole("checkbox", { name: "Policy" }).check();
    await editor.getByRole("button", { name: "Save Tags" }).click();
    await expect(row(page, "leave-policy.md").getByRole("list", { name: "Tags" }).getByRole("listitem")).toHaveText(["HR", "Policy"]);

    // Bulk-apply HR to two Documents.
    await page.getByRole("checkbox", { name: "Select leave-policy.md" }).check();
    await page.getByRole("checkbox", { name: "Select expenses.md" }).check();
    const bulk = page.getByRole("group", { name: "Bulk tagging" });
    await expect(bulk.getByText("2 selected")).toBeVisible();
    await bulk.getByLabel("Tag").selectOption({ label: "HR" });
    await bulk.getByRole("button", { name: "Apply to selected" }).click();
    await expect(row(page, "expenses.md").getByRole("list", { name: "Tags" }).getByRole("listitem")).toHaveText(["HR"]);
    await bulk.getByRole("button", { name: "Clear selection" }).click();
    await expect(tags.getByRole("listitem").filter({ hasText: "HR" })).toContainText("2 Documents");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // Rename a Tag: Documents keep it under the new name.
    await tags.getByRole("button", { name: "Rename HR" }).click();
    await tags.getByLabel("Name for HR").fill("People");
    await tags.getByRole("button", { name: "Save" }).click();
    await expect(row(page, "expenses.md").getByRole("list", { name: "Tags" }).getByRole("listitem")).toHaveText(["People"]);

    // Filter by Tag, search by name, filter by status.
    await page.getByLabel("Filter by Tag").selectOption({ label: "People" });
    await expect.poll(() => documentNames(page)).toEqual(["expenses.md", "leave-policy.md"]);
    await page.getByRole("searchbox", { name: "Search by name" }).fill("LEAVE");
    await expect.poll(() => documentNames(page)).toEqual(["leave-policy.md"]);
    await page.getByLabel("Status").selectOption({ label: "Failed" });
    await expect(page.getByText("No Documents match these filters.")).toBeVisible();
    await page.getByRole("button", { name: "Clear filters" }).click();
    await expect.poll(() => documentNames(page)).toEqual(["expenses.md", "leave-policy.md", "sales-deck.md"]);

    // Delete a Tag: it leaves every Document, which stay.
    await tags.getByRole("button", { name: "Delete Policy" }).click();
    await tags.getByRole("button", { name: "Delete Tag" }).click();
    await expect(tags.getByTestId("tag-name")).toHaveText(["People", "Sales"]);
    await expect(row(page, "leave-policy.md").getByRole("list", { name: "Tags" }).getByRole("listitem")).toHaveText(["People"]);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });
});
