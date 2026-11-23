import { expect, test } from "../fixtures";
import { signInAs } from "../fixtures/auth";
import { openSection } from "../fixtures/navigation";

// `make seed` runs before the suite (`make e2e`). The seed's history judged most of the HR
// helper's Visitor replies with the demo model: v2's uncited replies failed grounding, so v2's
// Live score is below v1's. Read-only: nothing here changes the demo Organisation.
const OWNER = { email: "owner@northwind.example", password: "northwind-owner-demo" };

test.describe("Live score in the demo", () => {
  test("[US15-59][US15-31] the HR helper's Version comparison shows v2's Live score below v1's, v1 the Better side", async ({ page, makeAxeBuilder }) => {
    await signInAs(page, OWNER);
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    await page.getByRole("link", { name: "Northwind Handbook" }).click();
    await openSection(page, "Project sections", "Analytics");
    await page.getByRole("combobox", { name: "Agent" }).selectOption({ label: "HR helper" });
    await page.getByLabel("First Version").selectOption({ label: "v1" });
    await page.getByLabel("Second Version").selectOption({ label: "v2" });
    const row = page
      .getByRole("table", { name: "v1 compared with v2" })
      .getByRole("row")
      .filter({ has: page.getByRole("rowheader", { name: "Live score", exact: true }) });
    const cells = row.getByRole("cell");
    await expect(cells.nth(3)).toHaveText("v1", { timeout: 15_000 });
    const v1 = Number(/(\d+)%/.exec(await cells.nth(0).innerText())?.[1]);
    const v2 = Number(/(\d+)%/.exec(await cells.nth(1).innerText())?.[1]);
    expect(v2).toBeLessThan(v1);
    await expect(cells.nth(2)).toHaveText(/^−\d+ pts$/);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });

  test("[US15-60] the Live score card, the Live Verdict filter and the Trace's Live Verdict are announced and work from the keyboard", async ({
    page,
    makeAxeBuilder,
  }) => {
    await signInAs(page, OWNER);
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    await page.getByRole("link", { name: "Northwind Handbook" }).click();
    await openSection(page, "Project sections", "Analytics");
    await page.getByRole("combobox", { name: "Agent" }).selectOption({ label: "HR helper" });
    await page.getByRole("combobox", { name: /^Version/ }).selectOption({ label: "v1" });
    // The KPI card is a list item named by its heading, its interval and sample size in words.
    const card = page.getByRole("list", { name: "Key numbers for v1" }).getByRole("listitem", { name: "Live score" });
    await expect(card).toContainText(/95% interval \d+% to \d+%/, { timeout: 15_000 });
    await expect(card).toContainText(/n = \d+ judged replies \(\d+ passed\)/);

    // The Conversations viewer's Live Verdict filter, chosen with the keyboard.
    await openSection(page, "Project sections", "Conversations");
    const filter = page.getByRole("group", { name: "Filter Conversations" }).getByLabel("Live Verdict");
    await expect(filter).toBeVisible({ timeout: 15_000 });
    await filter.focus();
    await expect(filter).toBeFocused();
    await filter.selectOption("failed");
    await expect(page).toHaveURL(/live=failed/);
    const first = page.getByRole("list", { name: "Conversations" }).getByRole("listitem").first();
    await expect(first).toContainText(/\d+ failed/, { timeout: 15_000 });
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // Into a failed Conversation from the keyboard, then its first reply's Trace.
    await first.getByRole("link").first().focus();
    await page.keyboard.press("Enter");
    const replies = page.getByRole("list", { name: "Messages" }).getByRole("listitem", { name: "HR helper" });
    await expect(replies.first()).toBeVisible({ timeout: 15_000 });
    // The Trace folds open from its summary, a native disclosure.
    const trace = replies.first().getByRole("group", { name: "Trace" }).locator("summary");
    await trace.focus();
    await expect(trace).toBeFocused();
    await page.keyboard.press("Enter");
    // The Live Verdict is a region named by its heading.
    await expect(replies.first().getByRole("region", { name: "Live Verdict" })).toBeVisible({ timeout: 15_000 });
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });
});
