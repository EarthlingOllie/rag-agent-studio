import { expect, test } from "../fixtures";

test.describe("Audit tab", () => {
  test("an Owner finds their Organisation's creation in the Audit tab", async ({ signedInPage, member, makeAxeBuilder }) => {
    await signedInPage.goto("/");
    await signedInPage.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Organisation settings" }).click();
    await signedInPage.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: "Audit" }).click();

    await expect(signedInPage.getByRole("heading", { name: "Audit" })).toBeVisible();
    const table = signedInPage.getByRole("table", { name: "Audit Events" });
    const row = table.getByRole("row").filter({ hasText: "organisation.created" });
    await expect(row).toHaveCount(1);
    await expect(row).toContainText(member.name);
    await expect(row).toContainText(JSON.stringify({ name: member.organisationName }));
    await expect(signedInPage.getByText("Page 1 of 1 · 1 event")).toBeVisible();

    await signedInPage.getByLabel("Action").selectOption("organisation.created");
    await signedInPage.getByLabel("Actor").selectOption(member.name);
    await expect(row).toHaveCount(1);
    await signedInPage.getByLabel("From (UTC)").fill("2000-01-01");
    await signedInPage.getByLabel("To (UTC)").fill("2000-01-02");
    await expect(signedInPage.getByText("No Audit Events match these filters.")).toBeVisible();

    const results = await makeAxeBuilder().analyze();
    expect(results.violations).toEqual([]);
  });
});
