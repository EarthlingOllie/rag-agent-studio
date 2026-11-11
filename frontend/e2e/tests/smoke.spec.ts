import { expect, test } from "../fixtures";

test.describe("Studio smoke", () => {
  test("the System status page shows every service operational", async ({ page }) => {
    await page.goto("/status");
    await expect(page.getByRole("heading", { name: "System status" })).toBeVisible();
    await expect(page.getByRole("status")).toHaveText("All systems operational");
    for (const service of ["API", "Database", "Redis", "Worker"]) {
      await expect(page.getByRole("row", { name: service })).toContainText("OK");
    }
    await expect(page.getByRole("row", { name: "Worker" })).toContainText("Worker replied: pong");
  });

  test("the System status page has no WCAG 2.2 AA violations", async ({ page, makeAxeBuilder }) => {
    await page.goto("/status");
    await expect(page.getByRole("status")).toHaveText("All systems operational");
    const results = await makeAxeBuilder().analyze();
    expect(results.violations).toEqual([]);
  });
});
