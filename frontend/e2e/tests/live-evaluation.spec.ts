import { expect, test } from "../fixtures";
import { openAgentView } from "../fixtures/agent";
import { signInAs } from "../fixtures/auth";
import { openSection } from "../fixtures/navigation";

// `make seed` runs before the suite (`make e2e`). The seed gives Northwind an Evaluation budget and
// the HR helper a Live sample rate, and its history judged v1's and v2's Visitor replies with the
// demo model: v2's cite nothing, so they failed grounding. The demo model judges by rule: grounding
// passes when the reply cites a Chunk, answering the question when it shares a long word with it.
const OWNER = { email: "owner@northwind.example", password: "northwind-owner-demo" };
const SEEDED_RATE = 90;
const BOOT = /<script id="widget-boot" type="application\/json">(.*?)<\/script>/;

test.describe("Live evaluation", () => {
  test("an Owner judges every HR helper reply, sees a widget reply's Live Verdict in its Trace, and adds a failed reply to the Evaluation Set", async ({
    page,
    browser,
    makeAxeBuilder,
  }) => {
    test.setTimeout(240_000);
    await signInAs(page, OWNER);
    await page.goto("/");

    await test.step("Organisation settings show the seeded Evaluation budget and this month's meter", async () => {
      await openSection(page, "Organisation sections", "Settings");
      await openSection(page, "Organisation settings", "Models");
      const budget = page.getByRole("form", { name: "Set the Evaluation budget" });
      await expect(budget.getByLabel("Evaluation budget (US dollars a month)")).toHaveValue(/^20(\.00)?$/, { timeout: 15_000 });
      await expect(page.getByRole("meter", { name: "Evaluation budget spent this month" })).toBeVisible();
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    await openSection(page, "Organisation sections", "Projects");
    await page.getByRole("link", { name: "Northwind Handbook" }).click();
    await openSection(page, "Project sections", "Agents");
    await page.getByRole("link", { name: "HR helper", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: "HR helper" })).toBeVisible({ timeout: 15_000 });
    const agentPath = /\/organisations\/[^/]+\/projects\/[^/]+\/agents\/[^/?#]+/.exec(page.url())?.[0] ?? "";
    const agentApi = `/api${agentPath}`;
    const { public_id: publicId } = (await (await page.request.get(agentApi)).json()) as { public_id: string };
    // A question only this run asks, so its Conversation is easy to find.
    const question = `How many days of annual leave do I get? (run ${String(Date.now())})`;
    // The case this test adds, deleted when it ends.
    const added: { id?: string | undefined } = {};

    try {
      await test.step("set the HR helper's Live sample rate to 100% in Embed & limits", async () => {
        await openAgentView(page, "Embed & limits");
        const card = page.getByRole("region", { name: "Live sample rate" });
        const rate = card.getByLabel("Visitor replies judged (%)");
        await expect(rate).toHaveValue(String(SEEDED_RATE), { timeout: 15_000 });
        await rate.fill("100");
        await card.getByRole("button", { name: "Save Live sample rate" }).click();
        await expect(card.getByText("Saved. It applies to the next Visitor reply.")).toBeVisible({ timeout: 15_000 });
      });

      await test.step("a Visitor sends the HR helper a widget message", async () => {
        const visitor = await browser.newContext();
        const shell = await (await visitor.request.get(`/widget/a/${publicId}`)).text();
        const boot = JSON.parse(BOOT.exec(shell)?.[1] ?? "{}") as { bootstrap_token: string };
        const started = await visitor.request.post(`/api/widget/agents/${publicId}/conversations`, {
          data: { bootstrap_token: boot.bootstrap_token },
        });
        expect(started.status()).toBe(201);
        const { conversation_token: token } = (await started.json()) as { conversation_token: string };
        const asked = await visitor.request.post(`/api/widget/agents/${publicId}/messages`, {
          data: { content: question },
          headers: { Authorization: `Bearer ${token}` },
        });
        expect(asked.status()).toBe(200);
        expect(await asked.text()).toContain("event: done");
        await visitor.close();
      });

      await test.step("its Live Verdict shows in the Conversations viewer's Trace", async () => {
        await openAgentView(page, "Conversations");
        await page.getByRole("link", { name: question }).click({ timeout: 15_000 });
        const reply = page.getByRole("list", { name: "Messages" }).getByRole("listitem", { name: "HR helper" });
        const verdict = reply.getByRole("region", { name: "Live Verdict" });
        // The worker judges it in the background: reload until it has.
        await expect(async () => {
          await page.reload();
          await reply.getByText("Trace", { exact: true }).click();
          await expect(verdict.getByRole("list", { name: "Live Verdict checks" })).toBeVisible({ timeout: 2_000 });
        }).toPass({ timeout: 60_000 });
        const checks = verdict.getByRole("list", { name: "Live Verdict checks" });
        await expect(checks.getByRole("listitem").filter({ hasText: "Grounded" })).toContainText("Fake judge: the answer cites the knowledge base.");
        await expect(checks.getByRole("listitem").filter({ hasText: "Answers the question" })).toContainText("Pass");
        await expect(verdict).toContainText(/Judged by demo · demo-chat/);
        expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      });

      await test.step("filter to failed replies and add one to the Evaluation Set", async () => {
        await openAgentView(page, "Conversations");
        await page.getByRole("group", { name: "Filter Conversations" }).getByLabel("Live Verdict").selectOption("failed");
        await expect(page).toHaveURL(/live=failed/);
        const list = page.getByRole("list", { name: "Conversations" });
        await expect(list.getByRole("listitem").first()).toContainText(/\d+ failed/, { timeout: 15_000 });
        await list.getByRole("listitem").first().getByRole("link").first().click();
        await expect(page.getByRole("heading", { level: 4, name: "Conversation with HR helper" })).toBeVisible({ timeout: 15_000 });

        // Open every reply's Trace, then pick one whose Live Verdict failed.
        const replies = page.getByRole("list", { name: "Messages" }).getByRole("listitem", { name: "HR helper" });
        for (let index = 0; index < (await replies.count()); index += 1) {
          await replies.nth(index).getByText("Trace", { exact: true }).click();
        }
        const failed = replies
          .filter({
            has: page.getByRole("region", { name: "Live Verdict" }).getByText("Fake judge: the answer cites nothing to support it."),
          })
          .first();
        await expect(failed).toBeVisible({ timeout: 15_000 });
        expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

        await failed.getByRole("button", { name: "More actions for this reply" }).click();
        await page.getByRole("menuitem", { name: "Add to Evaluation Set" }).click();
        const editor = page.getByRole("dialog", { name: "Add to Evaluation Set" });
        await expect(editor.getByLabel("Question")).not.toHaveValue("", { timeout: 15_000 });
        const reference = `Cites the handbook (run ${String(Date.now())}).`;
        await editor.getByLabel("Reference answer").fill(reference);
        await editor.getByRole("button", { name: "Save case" }).click();
        await expect(page.getByText("Added to the Evaluation Set.")).toBeVisible({ timeout: 15_000 });
        const cases = (await (await page.request.get(`${agentApi}/evaluation/cases`)).json()) as {
          id: string;
          reference_answer: string | null;
          source: string;
        }[];
        const found = cases.find((each) => each.reference_answer === reference);
        expect(found?.source).toBe("from_message");
        added.id = found?.id;
      });
    } finally {
      // Leave the seeded HR helper as the other demo tests expect it.
      await page.request.patch(`${agentApi}/operational-settings`, { data: { live_sample_rate: SEEDED_RATE } });
      if (added.id !== undefined) await page.request.delete(`${agentApi}/evaluation/cases/${added.id}`);
    }
  });
});
