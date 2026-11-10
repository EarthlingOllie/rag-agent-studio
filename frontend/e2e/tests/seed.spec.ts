import { expect, test } from "../fixtures";
import { openSettings } from "../fixtures/agent";
import { signInAs } from "../fixtures/auth";
import { openSection } from "../fixtures/navigation";

// `make seed` runs before the suite (`make e2e`); these are the accounts it prints.
const OWNER = { email: "owner@northwind.example", password: "northwind-owner-demo" };
const EDITOR = { email: "editor@northwind.example", password: "northwind-editor-demo" };
const DEMO_LABEL = "Demo: canned answers, not a real model";

test.describe("Seeded demo Organisation", () => {
  test("the demo Owner finds Northwind's Project, Documents, Tags and Agents", async ({ page, makeAxeBuilder }) => {
    await signInAs(page, OWNER);
    await page.goto("/");
    await expect(page.getByText("Northwind Traders").first()).toBeVisible();

    await openSection(page, "Organisation sections", "Projects");
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

    await openSection(page, "Project sections", "Agents");
    await expect(page.getByRole("link", { name: "HR helper" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Product FAQ" })).toBeVisible();
  });

  test("one seeded Agent is Agentic and one Automatic, over the same Project; the Guardrail demo Agent is Automatic", async ({
    page,
    makeAxeBuilder,
  }) => {
    await signInAs(page, EDITOR);
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    await page.getByRole("link", { name: "Northwind Handbook" }).click();
    for (const [agent, mode] of [
      ["Product FAQ", "Agentic"],
      ["HR helper", "Automatic"],
      ["Guardrail demo", "Automatic"],
    ] as const) {
      await openSection(page, "Project sections", "Agents");
      await page.getByRole("link", { name: agent, exact: true }).click();
      await expect(page.getByRole("heading", { level: 1, name: agent })).toBeVisible({ timeout: 15_000 });
      await openSettings(page, "Retrieval");
      await expect(page.getByRole("group", { name: "Retrieval" }).getByRole("radio", { name: mode })).toBeChecked();
    }
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });

  test("the demo model is the Default Model, labelled as a demo", async ({ page, makeAxeBuilder }) => {
    await signInAs(page, EDITOR);
    await page.goto("/");
    await openSection(page, "Organisation sections", "Settings");
    await openSection(page, "Organisation settings", "Models");

    await expect(page.getByText(`Demo model, using Northwind demo model (${DEMO_LABEL})`)).toBeVisible();
    await expect(page.getByText("Only Owners can change the Default Model.")).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });
});
