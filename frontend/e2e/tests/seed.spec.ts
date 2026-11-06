import { expect, test } from "../fixtures";
import { signInAs } from "../fixtures/auth";

// `make seed` runs before the suite (`make e2e`); these are the accounts it prints.
const OWNER = { email: "owner@northwind.example", password: "northwind-owner-demo" };
const EDITOR = { email: "editor@northwind.example", password: "northwind-editor-demo" };
const DEMO_LABEL = "Demo: canned answers, not a real model";

test.describe("Seeded demo Organisation", () => {
  test("the demo Owner finds Northwind's Project, Documents, Tags and Agents", async ({ page, makeAxeBuilder }) => {
    await signInAs(page, OWNER);
    await page.goto("/");
    await expect(page.getByText("Northwind Traders").first()).toBeVisible();

    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Projects" }).click();
    await page.getByRole("link", { name: "Northwind Handbook" }).click();
    const documents = page.getByRole("table", { name: "Documents" });
    for (const [name, tag] of [
      ["northwind-staff-handbook.md", "HR"],
      ["northwind-returns-policy.md", "Products"],
      ["northwind-product-faq.docx", "Products"],
      ["northwind-spring-range.pptx", "Products"],
    ] as const) {
      const row = documents.getByRole("row", { name: new RegExp(name.replace(".", "\\.")) });
      await expect(row.getByText(tag, { exact: true })).toBeVisible();
      await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 120_000 });
    }
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    await page.getByRole("link", { name: "Agents" }).click();
    await expect(page.getByRole("link", { name: "HR helper" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Product FAQ" })).toBeVisible();
  });

  test("the demo model is the Default Model, labelled as a demo", async ({ page, makeAxeBuilder }) => {
    await signInAs(page, EDITOR);
    await page.goto("/");
    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Organisation settings" }).click();
    await page.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: "Models" }).click();

    await expect(page.getByText(`Demo model, using Northwind demo model (${DEMO_LABEL})`)).toBeVisible();
    await expect(page.getByText("Only Owners can change the Default Model.")).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });
});
