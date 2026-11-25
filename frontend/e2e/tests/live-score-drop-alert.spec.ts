import { readFile } from "node:fs/promises";

import type { Browser, Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { newMember } from "../fixtures/auth";
import {
  demoOrganisation,
  emailsTo,
  emailText,
  FAILING_QUESTION,
  type LiveAgent,
  liveAgent,
  liveScores,
  PASSING_QUESTION,
  projectWithHandbook,
  publishWith,
  runHourlyRollup,
  setEvaluationBudget,
  setSampleRate,
  studioLink,
  visitorAsks,
  visitorsAsk,
  waitForJudged,
} from "../fixtures/live-score";

// A fresh Organisation answers and judges with the demo model (see fixtures/live-score.ts): a
// question about annual leave passes its Live Verdict, the same question with a quoted phrase the
// handbook lacks fails "answers the question". The Live score drop check runs in the hourly
// rollup's alerts step, which the test runs by hand (as rollout-widget-analytics.spec.ts does);
// the stack has no clock a test can move.
const SUBJECT = "Live score dropped";

/** Whether the Agent read says the Live score drop alert stands. */
async function alerted(page: Page, agent: LiveAgent): Promise<boolean> {
  return ((await (await page.request.get(agent.api)).json()) as { live_score_drop_alert: boolean }).live_score_drop_alert;
}

/** Adds an Editor to the Owner's Organisation through an Invite Link; returns their signed-in page. */
async function newEditor(owner: Page, browser: Browser, organisation: string): Promise<Page> {
  const person = newMember({ name: "Live score Editor" });
  const invited = await owner.request.post(`${organisation}/invites`, { data: { email: person.email, role: "editor", send_email: false } });
  expect(invited.status()).toBe(201);
  const token = new URL(((await invited.json()) as { link: string }).link).searchParams.get("token") ?? "";
  const page = await (await browser.newContext()).newPage();
  expect((await page.request.post("/api/invites/sign-up", { data: { token, name: person.name, password: person.password } })).status()).toBe(201);
  return page;
}

test.describe("Live score and its drop alert", () => {
  test("a Version's Live score card, comparison, CSV and Time series; the drop alert waits for 30 Live Verdicts, emails once, shows a badge and clears", async ({
    signedInPage: page,
    member,
    browser,
    makeAxeBuilder,
  }) => {
    test.setTimeout(600_000);
    const org = await demoOrganisation(page);
    await setEvaluationBudget(page.request, org.organisation, "5.00");
    const project = await projectWithHandbook(page, org, "Leave");
    const projectPath = project.replace(/^\/api/, "");
    const agent = await liveAgent(page, project, "Leave helper");
    await setSampleRate(page.request, agent, 100);
    const visitorContext = await browser.newContext();
    const visitor = visitorContext.request;
    const card = (version: number, name: string) =>
      page.getByRole("list", { name: `Key numbers for v${String(version)}` }).getByRole("listitem", { name });

    await test.step("[US15-29][US15-30] v1's Live score card: Low sample under 30 Live Verdicts, then its interval and sample size", async () => {
      await visitorsAsk(visitor, agent, PASSING_QUESTION, 29);
      await waitForJudged(page.request, agent, 1, 29);
      await page.goto(`${projectPath}/analytics?agent=${agent.id}`);
      await expect(card(1, "Live score")).toContainText("n = 29 judged replies (29 passed)", { timeout: 15_000 });
      await expect(card(1, "Live score").getByText("Low sample")).toHaveAttribute("title", "Fewer than 30 judged Live Verdicts");

      await visitorsAsk(visitor, agent, PASSING_QUESTION, 1);
      await waitForJudged(page.request, agent, 1, 30);
      await page.reload();
      await expect(card(1, "Live score")).toContainText("n = 30 judged replies (30 passed)", { timeout: 15_000 });
      await expect(card(1, "Live score")).toContainText("100%");
      await expect(card(1, "Live score")).toContainText(/95% interval 89% to 100%/);
      await expect(card(1, "Live score").getByText("Low sample")).toHaveCount(0);
    });

    await test.step("[US15-37] v2 is made Live; with 29 Live Verdicts, 2 failed, the hourly check doesn't alert", async () => {
      await publishWith(page, agent.api, "Answer from the handbook, kindly.", "Kinder answers");
      await visitorsAsk(visitor, agent, PASSING_QUESTION, 27);
      await visitorsAsk(visitor, agent, FAILING_QUESTION, 2);
      await waitForJudged(page.request, agent, 2, 29);
      runHourlyRollup();
      expect(await alerted(page, agent)).toBe(false);
      expect(await emailsTo(page.request, member.email, SUBJECT)).toHaveLength(0);
    });

    await test.step("[US15-36][US15-38] at 30 Live Verdicts a 10-point drop (100% to 90%) raises the alert", async () => {
      await visitorsAsk(visitor, agent, FAILING_QUESTION, 1);
      await waitForJudged(page.request, agent, 2, 30);
      const v2 = (await liveScores(page.request, agent)).get(2);
      expect([v2?.passed, v2?.n]).toEqual([27, 30]);
      runHourlyRollup();
      expect(await alerted(page, agent)).toBe(true);
    });

    let email = "";
    await test.step("[US15-40] one email to the Owner, linking to the Version comparison and the failed Live Verdicts", async () => {
      await expect.poll(async () => (await emailsTo(page.request, member.email, SUBJECT)).length, { timeout: 15_000 }).toBe(1);
      const [message] = await emailsTo(page.request, member.email, SUBJECT);
      expect(message?.Subject).toBe("Leave helper's Live score dropped");
      email = await emailText(page.request, message?.ID ?? "");
      expect(email).toContain("v2's Live score is 90% (27 of 30 judged replies); v1's was 100% (30 of 30)");
      // The alert stands, so a later hourly check doesn't email again.
      runHourlyRollup();
      expect(await alerted(page, agent)).toBe(true);
      expect(await emailsTo(page.request, member.email, SUBJECT)).toHaveLength(1);
    });

    await test.step("[US15-31][US15-35] the email's comparison link: the Live score row favours v1, and its CSV column", async () => {
      await page.goto(studioLink(email, "/analytics?"));
      await expect(page.getByLabel("First Version").locator("option:checked")).toHaveText("v1");
      await expect(page.getByLabel("Second Version").locator("option:checked")).toHaveText("v2 (Live)");
      const row = page
        .getByRole("table", { name: "v1 compared with v2" })
        .getByRole("row")
        .filter({ has: page.getByRole("rowheader", { name: "Live score", exact: true }) });
      await expect(row.getByRole("cell")).toHaveText(["100%", "90%", "−10 pts", "v1"], { timeout: 15_000 });
      const downloading = page.waitForEvent("download");
      await page.getByRole("link", { name: "Export as CSV" }).click();
      const lines = (await readFile(await (await downloading).path(), "utf8")).trim().split("\n");
      expect(lines).toContain("Live score,1.0000,0.9000,-0.1000,v1");
      // The v2 card: its score, interval and sample size.
      await expect(card(2, "Live score")).toContainText("90%");
      await expect(card(2, "Live score")).toContainText(/95% interval 74% to 97%/);
      await expect(card(2, "Live score")).toContainText("n = 30 judged replies (27 passed)");
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    await test.step("[US15-32] the Live score as a Time series metric, with the Live History markers", async () => {
      const section = page.getByRole("region", { name: "Over time" });
      await section.getByLabel("Metric").selectOption({ label: "Live score" });
      await expect(section.getByText(/Live score per day, from/)).toBeVisible({ timeout: 15_000 });
      const changes = section.getByRole("list", { name: "Live Version changes" }).getByRole("listitem");
      await expect(changes).toHaveCount(2);
      await expect(changes.nth(0)).toContainText("v1 published");
      await expect(changes.nth(1)).toContainText("v2 published (from v1)");
      await section.getByRole("radio", { name: "Table" }).click();
      const table = section.getByRole("table", { name: "Live score, the numbers behind the chart" });
      // Today's point: 57 of 60 judged replies passed, both Versions together.
      await expect(table.getByRole("row").last().getByRole("cell")).toHaveText(["95%", "60"], { timeout: 15_000 });
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    await test.step("[US15-40] the email's failed link opens the Conversations viewer filtered to failed Live Verdicts", async () => {
      await page.goto(studioLink(email, "live=failed"));
      await expect(page).toHaveURL(/live=failed/);
      const conversations = page.getByRole("list", { name: "Conversations" }).getByRole("listitem");
      await expect(conversations).toHaveCount(3, { timeout: 15_000 });
      for (let index = 0; index < 3; index += 1) await expect(conversations.nth(index)).toContainText("1 failed");
    });

    await test.step("[US15-41][US15-57][US15-60] the Live score drop badge on the Agent list and the Agent page, for an Editor too", async () => {
      const editor = await newEditor(page, browser, org.organisation);
      for (const viewer of [page, editor]) {
        await viewer.goto(`${projectPath}/agents`);
        const row = viewer.getByRole("table", { name: "Agents" }).getByRole("row").filter({ hasText: "Leave helper" });
        await expect(row.getByText("Live score drop", { exact: true })).toBeVisible({ timeout: 15_000 });
        await expect(row.getByText("Live score drop", { exact: true })).toHaveAttribute("title", /clearly lower than the previous Live Version/);
        await viewer.goto(agent.path);
        await expect(viewer.getByRole("heading", { level: 1, name: "Leave helper" })).toBeVisible({ timeout: 15_000 });
        await expect(viewer.getByText("Live score drop", { exact: true })).toBeVisible();
      }
      // The Editor also reads the Live score and a failed reply's Live Verdict.
      await editor.goto(`${projectPath}/analytics?agent=${agent.id}`);
      await expect(
        editor.getByRole("list", { name: "Key numbers for v2" }).getByRole("listitem", { name: "Live score" }),
      ).toContainText("n = 30 judged replies (27 passed)", { timeout: 15_000 });
      await editor.goto(`${projectPath}/conversations?agent=${agent.id}&live=failed`);
      await editor.getByRole("list", { name: "Conversations" }).getByRole("listitem").first().getByRole("link").first().click();
      const reply = editor.getByRole("list", { name: "Messages" }).getByRole("listitem", { name: "Leave helper" });
      await reply.getByText("Trace", { exact: true }).click();
      const checks = reply.getByRole("region", { name: "Live Verdict" }).getByRole("list", { name: "Live Verdict checks" });
      await expect(checks.getByRole("listitem").filter({ hasText: "Answers the question" })).toContainText(
        "Fake judge: the answer shares no key phrase with the question.",
        { timeout: 15_000 },
      );
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      await editor.context().close();
    });

    await test.step("[US15-33] Playground replies don't count towards the Live score", async () => {
      const before = (await liveScores(page.request, agent)).get(2);
      const tried = await page.request.post(`${agent.api}/playground/conversations`);
      const { id } = (await tried.json()) as { id: string };
      const asked = await page.request.post(`${agent.api}/playground/conversations/${id}/messages`, { data: { content: FAILING_QUESTION } });
      expect(await asked.text()).toContain("event: done");
      // A Visitor reply sent after it is judged, so the Playground's would have been by now too.
      await visitorsAsk(visitor, agent, PASSING_QUESTION, 1);
      await waitForJudged(page.request, agent, 2, 31);
      expect((await liveScores(page.request, agent)).get(2)?.passed).toBe((before?.passed ?? 0) + 1);
    });

    await test.step("[US15-34] Deleting a Conversation (the Purge's path) leaves the Live score as it was", async () => {
      const [reply] = await visitorAsks(visitor, agent, [FAILING_QUESTION]);
      await waitForJudged(page.request, agent, 2, 32);
      const before = (await liveScores(page.request, agent)).get(2);
      expect([before?.passed, before?.n]).toEqual([28, 32]);
      const listed = (await (await page.request.get(`${project}/conversations?agent_id=${agent.id}&live_verdict=failed&page_size=100`)).json()) as {
        items: { id: string; preview: string | null }[];
      };
      const conversation = await Promise.all(
        listed.items.map(async (each) => {
          const detail = (await (await page.request.get(`${project}/conversations/${each.id}`)).json()) as { messages: { id: string }[] };
          return detail.messages.some((message) => message.id === reply) ? each.id : null;
        }),
      ).then((ids) => ids.find((id) => id !== null));
      expect(conversation).toBeDefined();
      expect((await page.request.delete(`${project}/conversations/${conversation ?? ""}`)).status()).toBe(204);
      const after = (await liveScores(page.request, agent)).get(2);
      expect([after?.passed, after?.n]).toEqual([28, 32]);
      runHourlyRollup();
      const rolledUp = (await liveScores(page.request, agent)).get(2);
      expect([rolledUp?.passed, rolledUp?.n]).toEqual([28, 32]);
    });

    await test.step("[US15-42][US15-39] the alert clears once the drop is no longer clear", async () => {
      // 28 of 32 plus 25 passes: 53 of 57 (93%) against 100% of 30 is no longer a clear drop.
      // (US15-39, a drop under 5 points that is still significant, needs hundreds of Live Verdicts
      // a side; backend/tests/integration/test_live_score_alert.py covers it. Here the badge
      // follows the same hourly check down as well as up.)
      await visitorsAsk(visitor, agent, PASSING_QUESTION, 25);
      await waitForJudged(page.request, agent, 2, 57);
      runHourlyRollup();
      expect(await alerted(page, agent)).toBe(false);
      await page.goto(`${projectPath}/agents`);
      const row = page.getByRole("table", { name: "Agents" }).getByRole("row").filter({ hasText: "Leave helper" });
      await expect(row).toBeVisible({ timeout: 15_000 });
      await expect(row.getByText("Live score drop", { exact: true })).toHaveCount(0);
    });

    await test.step("[US15-42] a later drop alerts again, and making another Version Live clears it at once", async () => {
      // 53 of 72 (74%): clearly lower again.
      await visitorsAsk(visitor, agent, FAILING_QUESTION, 15);
      await waitForJudged(page.request, agent, 2, 72);
      runHourlyRollup();
      expect(await alerted(page, agent)).toBe(true);
      await expect.poll(async () => (await emailsTo(page.request, member.email, SUBJECT)).length, { timeout: 15_000 }).toBe(2);
      await page.goto(agent.path);
      await expect(page.getByText("Live score drop", { exact: true })).toBeVisible({ timeout: 15_000 });
      // The Owner reverts to v1: no hourly check is needed to clear the badge.
      expect((await page.request.post(`${agent.api}/revert`)).ok()).toBe(true);
      expect(await alerted(page, agent)).toBe(false);
      await page.reload();
      await expect(page.getByRole("heading", { level: 1, name: "Leave helper" })).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText("Live score drop", { exact: true })).toHaveCount(0);
    });
    await visitorContext.close();
  });
});
