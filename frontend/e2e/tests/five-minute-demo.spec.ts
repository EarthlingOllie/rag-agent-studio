import type { Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { signInAs } from "../fixtures/auth";
import { BLOCKED_HOST_URL, HOST_URL } from "../fixtures/env";

// The README's five-minute demo, automated as one test, in the README's order. `make seed` runs
// before the suite (`make e2e`); the stack answers with the demo model and the real local classifier.
const OWNER = { email: "owner@northwind.example", password: "northwind-owner-demo" };
const DEMO_ANSWER = "Demo model (canned answer, not AI)";
const REFUSAL = "Sorry, I can't help with that request.";
const FALLBACK = "Sorry, I don't know the answer to that.";
const BUDGET_UNAVAILABLE = "Northwind's low-budget helper has used today's budget. Please come back tomorrow.";

/** Each attack-panel button and the Guardrail layer outcome the demo shows for it. */
const ATTACKS = [
  { button: "Instruction override", input: "Blocked", canary: "Not reached", acted: "Acted: Input Guardrail.", reply: REFUSAL },
  { button: "Prompt extraction", input: "Blocked", canary: "Not reached", acted: "Acted: Input Guardrail.", reply: REFUSAL },
  { button: "Role-play jailbreak", input: "Blocked", canary: "Not reached", acted: "Acted: Input Guardrail.", reply: REFUSAL },
  { button: "Encoded attack (base64)", input: "Passed", canary: "Replaced the reply", acted: "Acted: Canary token.", reply: FALLBACK },
  { button: "Benign control", input: "Passed", canary: "Quiet", acted: "No Guardrail layer acted.", reply: "From northwind-staff-handbook" },
];

async function openProjectTab(page: Page, tab: string) {
  await page.getByRole("navigation", { name: "Project" }).getByRole("link", { name: tab }).click();
}

/** The Thumbs-up rate a Version's KPI card shows, as a whole percentage. */
async function thumbsUp(page: Page, version: string): Promise<number> {
  await page.getByRole("combobox", { name: /^Version/ }).selectOption({ label: version });
  const card = page
    .getByRole("list", { name: `Key numbers for ${version.replace(/ \(Live\)$/, "")}` })
    .getByRole("listitem", { name: "Thumbs-up rate" });
  await expect(card).toContainText(/95% interval \d+% to \d+%/, { timeout: 15_000 });
  return Number(/(\d+)%/.exec(await card.innerText())?.[1]);
}

test("the five-minute demo", async ({ page, browser, makeAxeBuilder }) => {
  test.setTimeout(300_000);

  await test.step("1. The Studio: the demo Owner signs in to Northwind's Project", async () => {
    await signInAs(page, OWNER);
    await page.goto("/");
    await expect(page.getByText("Northwind Traders").first()).toBeVisible();
    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Projects" }).click();
    await page.getByRole("link", { name: "Northwind Handbook" }).click();
    const handbook = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /northwind-staff-handbook\.md/ });
    await expect(handbook.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 120_000 });
  });

  await test.step("2. The Knowledge Base viewer shows the flagged Chunk", async () => {
    await page.getByRole("link", { name: "northwind-staff-handbook.md" }).click();
    await expect(page.getByText(/^\d+ Chunks? flagged as possible instructions to an AI\.$/)).toBeVisible({ timeout: 15_000 });
    const flagged = page
      .getByRole("region", { name: "Chunks" })
      .getByRole("listitem")
      .filter({ has: page.getByRole("note", { name: "Guardrail flag" }) });
    await expect(flagged.filter({ hasText: "A note for AI assistants" })).toHaveCount(1);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });

  await test.step("3. The Agent editor and a Playground Trace", async () => {
    await openProjectTab(page, "Agents");
    await page.getByRole("link", { name: "HR helper" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "HR helper" })).toBeVisible({ timeout: 15_000 });
    await page.getByLabel("Question", { exact: true }).fill("How many days of annual leave do I get?");
    await page.getByRole("button", { name: "Send" }).click();
    const answer = page.getByRole("list", { name: "Playground messages" }).getByRole("listitem", { name: "HR helper" });
    await expect(answer).toContainText(DEMO_ANSWER, { timeout: 30_000 });
    await answer.getByRole("button", { name: "Trace" }).click();
    const trace = page.getByRole("dialog", { name: "Trace" });
    await expect(trace.getByRole("table", { name: "Retrieved Chunks" }).getByRole("row").nth(1)).toBeVisible({ timeout: 15_000 });
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await trace.getByRole("button", { name: "Close" }).click();
  });

  await test.step("4. Publish and revert: the HR helper's Live History tells the v2 story", async () => {
    const timeline = page.getByRole("list", { name: "Live History" });
    await expect(timeline.getByRole("listitem").nth(0)).toContainText("Published v1 → v3");
    await expect(timeline.getByRole("listitem").nth(1)).toContainText("Reverted v2 → v1");
    await expect(timeline.getByRole("listitem").nth(2)).toContainText("Published v1 → v2");
  });

  await test.step("5. The analytics comparison: v2 was worse, v3 is better but a small sample", async () => {
    await openProjectTab(page, "Analytics");
    await page.getByRole("combobox", { name: "Agent" }).selectOption({ label: "HR helper" });
    const v1 = await thumbsUp(page, "v1");
    const v2 = await thumbsUp(page, "v2");
    const v3 = await thumbsUp(page, "v3 (Live)");
    expect(v2).toBeLessThan(v1);
    expect(v1).toBeLessThan(v3);
    const v3Volume = page.getByRole("list", { name: "Key numbers for v3" }).getByRole("listitem", { name: "Volume" });
    await expect(v3Volume).toContainText("Low confidence (fewer than 30 Conversations)");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });

  await test.step("6. The embed on the shop page: a Visitor chats with the Product FAQ", async () => {
    const shop = await browser.newPage();
    await shop.goto(`${HOST_URL}/demo/`);
    const widget = shop.frameLocator('iframe[title="Chat"]');
    await widget.getByRole("button", { name: "Open chat" }).click({ timeout: 15_000 });
    await widget.getByLabel("Message").fill("Can I return a jar of honey?");
    await widget.getByRole("button", { name: "Send" }).click();
    const log = widget.getByRole("log", { name: "Conversation" });
    await expect(log.getByRole("listitem", { name: "Product FAQ", exact: true })).toContainText(DEMO_ANSWER, { timeout: 30_000 });
    await shop.close();
  });

  await test.step("7. The disallowed origin: the browser refuses to show the widget", async () => {
    const blocked = await browser.newPage();
    await blocked.goto(`${BLOCKED_HOST_URL}/`);
    await expect(blocked.getByRole("heading", { level: 1, name: "This site may not show the chat" })).toBeVisible();
    const iframe = blocked.locator('iframe[title="Chat"]');
    await expect(iframe).toHaveAttribute("src", /\/widget\/a\/agt_/, { timeout: 15_000 });
    await expect
      .poll(async () => (await (await iframe.elementHandle()).contentFrame())?.url(), { timeout: 15_000 })
      .toBe("chrome-error://chromewebdata/");
    await blocked.close();
  });

  await test.step("8. The attack panel: each button, and the Guardrail layer that acted", async () => {
    const panel = await browser.newPage();
    await panel.goto(`${HOST_URL}/demo/attacks.html`);
    for (const attack of ATTACKS) {
      await panel.getByRole("button", { name: attack.button, exact: true }).click({ timeout: 15_000 });
      const result = panel.getByRole("region", { name: attack.button });
      await expect(result.getByText(attack.acted, { exact: true })).toBeVisible({ timeout: 45_000 });
      const layers = result.getByRole("table", { name: "Guardrail layers" });
      await expect(layers.getByRole("row", { name: /Input Guardrail/ }).getByRole("cell").first()).toHaveText(attack.input);
      await expect(layers.getByRole("row", { name: /Canary token/ }).getByRole("cell").first()).toHaveText(attack.canary);
      await expect(result.locator("#stream")).toContainText(attack.reply);
      await expect(panel.getByRole("status")).toHaveText(`${attack.button}: done.`);
    }
    await panel.close();
  });

  await test.step("9. The Token Budget: one click spends it, the widget says so and the Studio alerts", async () => {
    const budget = await browser.newPage();
    await budget.goto(`${HOST_URL}/demo/budget.html`);
    const widget = budget.frameLocator('iframe[title="Chat"]');
    await expect(widget.getByRole("heading", { name: "Low-budget helper" })).toBeVisible({ timeout: 15_000 });
    await budget.getByRole("button", { name: "Use up today's Token Budget" }).click();
    await expect(budget.getByRole("status")).toContainText("Today's Token Budget is spent");
    await widget.getByLabel("Message").fill("Do you sell honey?");
    await widget.getByRole("button", { name: "Send" }).click();
    await expect(widget.getByRole("alert")).toHaveText(BUDGET_UNAVAILABLE, { timeout: 15_000 });
    await budget.close();

    await openProjectTab(page, "Agents");
    const listed = page.getByRole("list", { name: "Agents" }).getByRole("listitem").filter({ hasText: "Low-budget helper" });
    await expect(listed.getByText("Budget exhausted")).toBeVisible({ timeout: 15_000 });
  });

  await test.step("10. Organisation cost: what each Project and Agent spent, the Playground apart", async () => {
    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Cost" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Organisation cost" })).toBeVisible();
    const byProject = page.getByRole("table", { name: "Cost by Project" });
    await expect(byProject.getByRole("row", { name: /^Northwind Handbook/ })).toBeVisible({ timeout: 15_000 });
    await page.getByLabel("Break down by").selectOption("Agent");
    const byAgent = page.getByRole("table", { name: "Cost by Agent" });
    await expect(byAgent.getByRole("row", { name: /^HR helper Northwind Handbook/ })).toBeVisible({ timeout: 15_000 });
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });

  await test.step("11. The Audit tab is already full of the seeded history", async () => {
    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Organisation settings" }).click();
    await page.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: "Audit" }).click();
    const events = page.getByRole("table", { name: "Audit Events" });
    await expect(events.getByRole("row").nth(1)).toBeVisible({ timeout: 15_000 });
    for (const action of ["agent.reverted", "agent.bulk_published", "project.instructions_published"]) {
      await page.getByRole("combobox", { name: "Action" }).selectOption(action);
      await expect(events.getByRole("row").filter({ hasText: action }).first()).toBeVisible({ timeout: 15_000 });
    }
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });
});
