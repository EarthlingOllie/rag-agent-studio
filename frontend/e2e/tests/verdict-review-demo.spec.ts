import type AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { openAgentView } from "../fixtures/agent";
import { signInAs } from "../fixtures/auth";
import { openSection } from "../fixtures/navigation";
import { APPEARANCES } from "../fixtures/pages";

// Spec 18 in the demo. `make seed` runs before the suite (`make e2e`): after the history the demo
// Owner and Editor reviewed 40 of the HR helper's Run Verdicts and Live Verdict checks on the
// Review sample (`backend/app/seed/reviews.py`), failing 4 the Demo model passed. These tests add
// reviews, so they count up from whatever the demo Organisation holds rather than from 40.
const OWNER = { email: "owner@northwind.example", password: "northwind-owner-demo" };
const EDITOR = { email: "editor@northwind.example", password: "northwind-editor-demo" };

/** Switches the Appearance and waits for the colour transitions to settle, so axe reads the final colours. */
async function useAppearance(page: Page, appearance: (typeof APPEARANCES)[number]) {
  await page.emulateMedia({ colorScheme: appearance });
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"));
}

/** Axe's violations on the page in each Appearance, keyed by Appearance; empty when there are none. */
async function violationsInBothAppearances(page: Page, makeAxeBuilder: () => AxeBuilder) {
  const found: Record<string, string[]> = {};
  for (const appearance of APPEARANCES) {
    await useAppearance(page, appearance);
    const ids = (await makeAxeBuilder().analyze()).violations.map((violation) => violation.id);
    if (ids.length > 0) found[appearance] = ids;
  }
  await useAppearance(page, "light");
  return found;
}

async function openModelsSettings(page: Page) {
  await page.goto("/");
  await openSection(page, "Organisation sections", "Settings");
  await openSection(page, "Organisation settings", "Models");
}

function agreementCard(page: Page) {
  return page.getByRole("region", { name: "Evaluation Model agreement" });
}

/** The card's "N sample reviews in this Organisation, M of them yours." line, as numbers. */
async function sampleReviewCounts(page: Page) {
  const line = agreementCard(page).getByText(/sample reviews? in this Organisation/);
  await expect(line).toBeVisible({ timeout: 15_000 });
  const [, organisation, yours] = /^(\d+) sample reviews? in this Organisation, (\d+) of them yours/.exec(await line.innerText()) ?? [];
  return { organisation: Number(organisation), yours: Number(yours) };
}

test.describe("Verdict review in the demo", () => {
  test("[US18-38] [US18-1] [US18-8] [US18-9] [US18-12] [US18-28] [US18-39] the agreement card shows the seeded reviews with false passes; reviewing an item on the Review sample shows the reveal and the count goes up; both pass axe in light and dark", async ({
    page,
    makeAxeBuilder,
  }) => {
    test.setTimeout(120_000);
    await signInAs(page, EDITOR);
    await openModelsSettings(page);

    // The seeded reviews: past Low sample, with a few false passes and no false fails.
    const card = agreementCard(page);
    await expect(card.getByText(/^\d+% agreed$/)).toBeVisible({ timeout: 15_000 });
    await expect(card.getByText(/^\d+ of \d+ sample reviews agreed: [1-9]\d* false passes?, 0 false fails$/)).toBeVisible();
    await expect(card.getByText(/^95% interval \d+% to \d+%$/)).toBeVisible();
    const perCheck = card.getByRole("table", { name: "Agreement per check" });
    for (const check of ["Grounding", "Answers the question", "Reference answer"]) {
      await expect(perCheck.getByRole("rowheader", { name: check })).toBeVisible();
    }
    const before = await sampleReviewCounts(page);
    expect(before.organisation).toBeGreaterThanOrEqual(40);
    expect(await violationsInBothAppearances(page, makeAxeBuilder)).toEqual({});

    // The card links to the Review sample, which serves one item without the Evaluation Model's outcome.
    await card.getByRole("link", { name: "Review sample" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Review sample" })).toBeVisible();
    const item = page.getByRole("article", { name: "Item to review" });
    await expect(item).toBeVisible({ timeout: 15_000 });
    await expect(item.getByRole("heading", { level: 3, name: "Question" })).toBeVisible();
    await expect(page.getByText(`${String(before.organisation)} sample reviews so far, ${String(before.yours)} of them yours.`)).toBeVisible();
    await expect(page.getByRole("heading", { name: /You (agreed with|differed from) the Evaluation Model/ })).toHaveCount(0);
    expect(await violationsInBothAppearances(page, makeAxeBuilder)).toEqual({});

    // Pass, from the keyboard: the reveal shows the Evaluation Model's pass or fail beside it.
    const pass = page.getByRole("group", { name: "Your verdict" }).getByRole("button", { name: "Pass" });
    await pass.focus();
    await page.keyboard.press("Enter");
    const reveal = page.getByRole("region", { name: /^You (agreed with|differed from) the Evaluation Model$/ });
    await expect(reveal).toBeVisible({ timeout: 15_000 });
    await expect(reveal.getByText("Evaluation Model", { exact: true })).toBeVisible();
    expect(await violationsInBothAppearances(page, makeAxeBuilder)).toEqual({});

    // The next item counts the review; so does the agreement card.
    await reveal.getByRole("button", { name: "Next" }).click();
    await expect(page.getByText(`${String(before.organisation + 1)} sample reviews so far, ${String(before.yours + 1)} of them yours.`)).toBeVisible({
      timeout: 15_000,
    });
    await openModelsSettings(page);
    expect(await sampleReviewCounts(page)).toEqual({ organisation: before.organisation + 1, yours: before.yours + 1 });
  });

  test("[US18-16] [US18-18] [US18-39] the Owner disagrees with a Verdict in the HR helper's Run detail and sees the review on it", async ({ page, makeAxeBuilder }) => {
    test.setTimeout(120_000);
    await signInAs(page, OWNER);
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    await page.getByRole("link", { name: "Northwind Handbook" }).click();
    await openSection(page, "Project sections", "Agents");
    await page.getByRole("link", { name: "HR helper", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: "HR helper" })).toBeVisible({ timeout: 15_000 });
    await openAgentView(page, "Evaluation");

    // The newest Run's detail is shown: the Editor's Draft against v3. A judged Verdict nobody has reviewed yet.
    const runDetail = page.getByRole("region", { name: /^Run of / });
    await expect(runDetail.getByRole("list", { name: "Cases" })).toBeVisible({ timeout: 15_000 });
    const controls = runDetail
      .getByRole("group", { name: /^Your review of the (Reference answer|Grounding) Verdict$/ })
      .filter({ has: page.getByRole("button", { name: "Disagree" }) })
      .first();
    await expect(controls).toBeVisible();
    const reason = `The answer adds a detail the handbook doesn't give (${String(Date.now())}).`;
    await controls.getByRole("button", { name: "Disagree" }).click();
    const form = controls.getByRole("form", { name: "Why you disagree" });
    await form.getByLabel(/^Why you disagree/).fill(reason);
    await form.getByRole("button", { name: "Save disagreement" }).click();

    // The review is shown on the Verdict: Disagreed, by the Owner, not from the Review sample, with the reason.
    const shown = runDetail.getByRole("group", { name: /^Your review of the / }).filter({ hasText: reason });
    await expect(shown).toBeVisible({ timeout: 15_000 });
    await expect(shown.getByText("Disagreed", { exact: true })).toBeVisible();
    await expect(shown.getByText(/^by Nadia Novak on /)).toBeVisible();
    await expect(shown.getByText(/from the Review sample/)).toHaveCount(0);
    await expect(shown.getByRole("button", { name: "Change review" })).toBeVisible();
    await expect(shown.getByRole("button", { name: "Remove review" })).toBeVisible();
    expect(await violationsInBothAppearances(page, makeAxeBuilder)).toEqual({});
  });
});
