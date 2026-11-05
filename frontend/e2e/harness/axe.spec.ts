import { expect, test } from "./test";

test.describe("axe accessibility checks", () => {
  test("pass on an accessible page", async ({ page, makeAxeBuilder }) => {
    await page.goto("/");
    const results = await makeAxeBuilder().analyze();
    expect(results.violations).toEqual([]);
  });

  test("report a WCAG violation", async ({ page, makeAxeBuilder }) => {
    await page.goto("/");
    await page.setContent('<!doctype html><html lang="en"><title>t</title><main><img src="x.png"></main></html>');
    const results = await makeAxeBuilder().analyze();
    expect(results.violations.map((violation) => violation.id)).toContain("image-alt");
  });
});
