import type AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { openAgentView } from "../fixtures/agent";
import { openSection } from "../fixtures/navigation";
import { APPEARANCES } from "../fixtures/pages";
import { addCase, askAsVisitor, EVALUATION_MODEL, json, publishedAgent, suggestionOrg, waitForFailedVerdicts } from "../fixtures/suggestion-org";

// Spec 19 on the stack (`make e2e`), in a fresh Owner's Organisation so the seeded demo keeps its
// Judging setup (see `fixtures/suggestion-org.ts`): the demo model answers and the fake gateway's
// Claude judges and drafts, by rule. The Project's one Document says what it doesn't cover, and the
// demo model quotes it in every reply. Visitors ask when payday is: the reply shares no word of five
// letters or more with the question, so the fake judge fails it on "answers the question", and the
// Owner passes every Review sample item, as an Editor who accepts a partial answer that says what it
// doesn't cover would. The fake drafter turns those disagreements into the one rule the fake judge
// follows, so a check of the draft on the held-out half shows agreement rising.
// The backend's `tests/integration/test_guidance_demo_path.py` walks the same path at the API seam.
const HANDBOOK = "Everyone gets 25 days of annual leave a year. This handbook doesn't cover payroll or pensions: ask HR.";
const QUESTION = "When is payday?";
// Two Review sample items a reply (grounding, answers the question): 30 sample reviews, 15 of them
// disagreeing, just what drafting needs.
const REPLIES = 15;
const PARTIAL_RULE = "Partial answers that say what they don't cover pass.";

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

interface SampleItem {
  verdict_id: string | null;
  live_verdict_id: string | null;
  check: string;
}

/** Passes every item the Review sample serves, through the API as the Review sample page does; each item's check and whether the reveal agreed. */
async function passEverySampleItem(page: Page, organisation: string): Promise<[string, boolean][]> {
  const reveals: [string, boolean][] = [];
  for (;;) {
    const { item } = await json<{ item: SampleItem | null }>(page.request, "GET", `${organisation}/review-sample/next`);
    if (item === null) return reveals;
    const reveal = await json<{ agreed: boolean }>(page.request, "POST", `${organisation}/review-sample/reviews`, {
      verdict_id: item.verdict_id,
      live_verdict_id: item.live_verdict_id,
      check: item.check,
      outcome: "pass",
      reason: item.check === "answers_question" ? "It says what the handbook doesn't cover and who to ask, which answers it." : null,
    });
    reveals.push([item.check, reveal.agreed]);
  }
}

test.describe("Judging guidance on the stack", () => {
  test("[US19-9] [US19-10] [US19-12] [US19-13] [US19-15] [US19-19] [US19-20] [US19-21] [US19-26] [US19-27] [US19-32] [US19-35] an Owner drafts guidance from disagreements, checks it and sees agreement rise, saves it, and the next Run is judged under the new Judging setup; the card passes axe in light and dark", async ({
    signedInPage: page,
    browser,
    makeAxeBuilder,
  }) => {
    test.setTimeout(300_000);
    const org = await suggestionOrg(page, "Judging guidance HR", HANDBOOK);
    const agent = await publishedAgent(page, org, "Guidance HR helper", { systemPrompt: "You help staff with the handbook." });
    await json(page.request, "PATCH", `${agent.api}/operational-settings`, { conversation_messages_per_minute: 120, ip_messages_per_minute: 600 });

    await test.step("Visitors' replies are judged, and the Owner reviews every Review sample item", async () => {
      for (let n = 0; n < REPLIES; n += 1) await askAsVisitor(browser, agent.public_id, QUESTION);
      await waitForFailedVerdicts(page, agent, REPLIES);
      const reveals = await passEverySampleItem(page, org.organisation);
      // Every reply cites the handbook (grounding agreed) and fails "answers the question".
      expect(reveals.filter(([check, agreed]) => check === "grounding" && agreed)).toHaveLength(REPLIES);
      expect(reveals.filter(([check, agreed]) => check === "answers_question" && !agreed)).toHaveLength(REPLIES);
      expect(reveals).toHaveLength(2 * REPLIES);
    });

    await openModelsSettings(page);
    const card = page.getByRole("region", { name: "Judging guidance" });
    await expect(card.getByText("No guidance: the Evaluation Model judges by its own instructions alone.")).toBeVisible({ timeout: 15_000 });
    const agreement = page.getByRole("region", { name: "Evaluation Model agreement" });
    await expect(agreement.getByText(`${String(REPLIES)} of ${String(2 * REPLIES)} sample reviews agreed: 0 false passes, ${String(REPLIES)} false fails`)).toBeVisible({
      timeout: 15_000,
    });
    expect(await violationsInBothAppearances(page, makeAxeBuilder)).toEqual({});

    await test.step("[US19-10] [US19-12] [US19-13] the Owner drafts guidance, seeing its estimated Cost first", async () => {
      const draftGroup = card.getByRole("group", { name: "Draft guidance" });
      const draftButton = draftGroup.getByRole("button", { name: "Draft guidance", exact: true });
      await expect(draftButton).toBeEnabled({ timeout: 15_000 });
      await draftButton.click();
      const confirm = page.getByRole("dialog", { name: "Draft guidance from disagreements?" });
      await expect(confirm.getByText(/Estimated Cost: \$\d/)).toBeVisible();
      await confirm.getByRole("button", { name: "Draft guidance", exact: true }).click();
      await expect(confirm).toBeHidden();
      await draftGroup.getByRole("button", { name: "Open the draft" }).click({ timeout: 60_000 });
    });

    const editor = card.getByRole("form", { name: "Edit the Judging guidance" });
    const text = editor.getByRole("textbox", { name: "Judging guidance" });
    await test.step("[US19-13] [US19-15] the draft opens in the editor with its explanation", async () => {
      await expect(text).toHaveValue(PARTIAL_RULE);
      const explanation = editor.getByRole("group", { name: "The draft's explanation" });
      await expect(explanation.getByText(/^Drafted by the Evaluation Model from \d+ disagreeing reviews outside the held-out half\./)).toBeVisible();
      await expect(explanation.getByRole("listitem").filter({ hasText: `Fake drafter: ${PARTIAL_RULE}` })).toBeVisible();
      expect(await violationsInBothAppearances(page, makeAxeBuilder)).toEqual({});
    });

    await test.step("[US19-19] [US19-20] [US19-21] a check on the held-out reviews shows agreement rising", async () => {
      await editor.getByRole("button", { name: "Check guidance" }).click();
      const result = editor.getByRole("group", { name: "Check result" });
      const line = result.getByText(/^On held-out reviews, this guidance would agree on \d+ of \d+ \(now \d+\)\.$/);
      await expect(line).toBeVisible({ timeout: 60_000 });
      const [, agreed, of, before] = /would agree on (\d+) of (\d+) \(now (\d+)\)/.exec(await line.innerText()) ?? [];
      expect(Number(of)).toBe(REPLIES);
      expect(Number(agreed)).toBe(REPLIES);
      expect(Number(before)).toBeLessThan(Number(agreed));
      await expect(result.getByText(/^False passes: 0, false fails: 0\./)).toBeVisible();
      // Fewer than 30 held-out reviews: a Low sample.
      await expect(result.getByText("Low sample")).toBeVisible();
      await expect(editor.getByRole("button", { name: "Check again" })).toBeVisible();
      expect(await violationsInBothAppearances(page, makeAxeBuilder)).toEqual({});
    });

    await test.step("[US19-26] [US19-27] the Owner saves it: version 1 is current, and agreement starts again under it", async () => {
      await editor.getByRole("button", { name: "Save guidance" }).click();
      const confirm = page.getByRole("dialog", { name: "Save the Judging guidance?" });
      await expect(confirm.getByText("New Evaluation Runs and Live Verdicts are judged with it, and it starts a new Judging setup.", { exact: true })).toBeVisible();
      await confirm.getByRole("button", { name: "Save guidance" }).click();
      await expect(page.getByText("Judging guidance version 1 is saved: new judgements use it.")).toBeVisible();
      const current = card.getByRole("group", { name: "Current guidance" });
      await expect(current.getByText(/^Version 1, saved by /)).toBeVisible();
      await expect(current.getByText(PARTIAL_RULE, { exact: true })).toBeVisible();
      await expect(current.getByText(/^Checked before saving: would agree on \d+ of \d+ \(now \d+\)/)).toBeVisible();
      await expect(card.getByRole("list", { name: "Guidance versions" }).getByText(/^Version 1, drafted, saved by /)).toBeVisible();
      await expect(agreement.getByText(`${EVALUATION_MODEL} (Anthropic) with guidance version 1`, { exact: true })).toBeVisible();
      await expect(agreement.getByText("No sample reviews under this Judging setup yet.")).toBeVisible();
      await expect(agreement.getByRole("table", { name: "Earlier Judging setups" })).toContainText(`${EVALUATION_MODEL} (Anthropic) with no guidance`);
      expect(await violationsInBothAppearances(page, makeAxeBuilder)).toEqual({});
    });

    await test.step("[US19-32] the next Run's header shows the new Judging setup", async () => {
      await addCase(page, agent, QUESTION, 'It says "ask HR".');
      await json(page.request, "PUT", `${org.organisation}/evaluation-repeats`, { repeats: 1 });
      await json(page.request, "POST", `${agent.api}/evaluation/runs`, {});
      await page.goto(agent.path);
      await expect(page.getByRole("heading", { level: 1, name: agent.name })).toBeVisible({ timeout: 15_000 });
      await openAgentView(page, "Evaluation");
      const runDetail = page.getByRole("region", { name: /^Run of / });
      await expect(runDetail.getByText(`judged by anthropic ${EVALUATION_MODEL} with guidance version 1`, { exact: false })).toBeVisible({ timeout: 60_000 });
    });
  });
});
