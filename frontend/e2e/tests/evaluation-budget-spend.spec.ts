import type { Browser, Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { openAgentView } from "../fixtures/agent";
import { newMember, signUp } from "../fixtures/auth";
import {
  demoOrganisation,
  emailsTo,
  emailText,
  FAKE_CLAUDE_KEY,
  type LiveAgent,
  liveAgent,
  liveScores,
  liveVerdictOf,
  PASSING_QUESTION,
  projectWithHandbook,
  psql,
  setEvaluationBudget,
  setSampleRate,
  studioLink,
  visitorAsks,
  waitForJudged,
} from "../fixtures/live-score";
import { openSection } from "../fixtures/navigation";

// A fresh Organisation answers Visitors with the demo model, which costs nothing. Its Evaluation
// Model is the fake gateway's Claude, whose price this credential overrides to $1,000 per million
// tokens, so one Live Verdict (a few hundred tokens) costs well over the $0.01 budget and spends
// it at once. See fixtures/live-score.ts for how the demo model answers and the judge judges.
const SPENT_SUBJECT = "Your Organisation's Evaluation budget is spent";

/** Adds an Editor to the Owner's Organisation through an Invite Link; returns their signed-in page. */
async function newEditor(owner: Page, browser: Browser, organisation: string): Promise<Page> {
  const person = newMember({ name: "Budget Editor" });
  const invited = await owner.request.post(`${organisation}/invites`, { data: { email: person.email, role: "editor", send_email: false } });
  expect(invited.status()).toBe(201);
  const token = new URL(((await invited.json()) as { link: string }).link).searchParams.get("token") ?? "";
  const page = await (await browser.newContext()).newPage();
  expect((await page.request.post("/api/invites/sign-up", { data: { token, name: person.name, password: person.password } })).status()).toBe(201);
  return page;
}

interface Budget {
  evaluation_budget_usd: string | null;
  spent_usd: string;
  exhausted: boolean;
}

async function budgetOf(page: Page, organisation: string): Promise<Budget> {
  return (await (await page.request.get(`${organisation}/evaluation-budget`)).json()) as Budget;
}

/** Makes the fake Claude the Evaluation Model, priced at $1,000 per million tokens for this credential. */
async function judgeWithPriceyClaude(page: Page, organisation: string) {
  const credential = await page.request.post(`${organisation}/credentials`, {
    data: { name: "Pricey Claude", provider: "anthropic", api_key: FAKE_CLAUDE_KEY },
  });
  expect(credential.status()).toBe(201);
  const { id } = (await credential.json()) as { id: string };
  expect(
    (await page.request.put(`${organisation}/credentials/${id}/prices`, { data: { model: "claude-haiku-4-5", input: "1000", output: "1000" } })).ok(),
  ).toBe(true);
  expect((await page.request.put(`${organisation}/evaluation-model`, { data: { credential_id: id, model: "claude-haiku-4-5" } })).status()).toBe(200);
}

/** Today's Organisation cost (by Project), straight from the API. */
async function costToday(page: Page, organisation: string) {
  const today = new Date().toISOString().slice(0, 10);
  const response = await page.request.get(`${organisation}/cost?start=${today}&end=${today}`);
  expect(response.ok()).toBe(true);
  return ((await response.json()) as { total: { evaluation_usd: string; visitor_usd: string } }).total;
}

test.describe("Evaluation budget", () => {
  test("an Owner sets the monthly Evaluation budget; sampling needs one, pauses when it is spent (one email), resumes when raised or in a new month; Visitors and Evaluation Runs never wait", async ({
    signedInPage: page,
    member,
    browser,
    makeAxeBuilder,
  }) => {
    test.setTimeout(420_000);
    const org = await demoOrganisation(page);
    const project = await projectWithHandbook(page, org, "Budgeted");
    const agent: LiveAgent = await liveAgent(page, project, "Budgeted helper");
    const visitorContext = await browser.newContext();
    const visitor = visitorContext.request;
    const editor = await newEditor(page, browser, org.organisation);

    await test.step("[US15-44] no budget by default: the Live sample rate can't be turned on, in the Studio or the API", async () => {
      expect((await budgetOf(page, org.organisation)).evaluation_budget_usd).toBeNull();
      await page.goto(`/organisations/${org.organisationId}/settings/models`);
      await expect(page.getByText("Evaluation budget: none")).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText("No Evaluation budget is set, so no Visitor replies are judged.")).toBeVisible();
      await page.goto(agent.path);
      await openAgentView(page, "Embed & limits");
      const card = page.getByRole("region", { name: "Live sample rate" });
      await expect(card.getByLabel("Visitor replies judged (%)")).toBeDisabled({ timeout: 15_000 });
      await expect(card.getByLabel("Visitor replies judged (%)")).toHaveValue("0");
      await expect(card).toContainText("The Organisation has no Evaluation budget, so no reply can be judged.");
      await expect(card.getByRole("link", { name: "Organisation settings" })).toHaveAttribute("href", `/organisations/${org.organisationId}/settings/models`);
      const refused = await page.request.patch(`${agent.api}/operational-settings`, { data: { live_sample_rate: 50 } });
      expect(refused.status()).toBe(422);
      expect(await refused.text()).toContain("evaluation_budget_required");
    });

    await test.step("[US15-43][US15-60] the Owner sets it in Organisation settings with the keyboard", async () => {
      await page.goto(`/organisations/${org.organisationId}/settings/models`);
      const form = page.getByRole("form", { name: "Set the Evaluation budget" });
      const field = form.getByLabel("Evaluation budget (US dollars a month)");
      await field.focus();
      await page.keyboard.type("0.01");
      await page.keyboard.press("Enter");
      await expect(page.getByText("The Evaluation budget is now $0.01 a month.")).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText("Evaluation budget: $0.01 a month")).toBeVisible();
      expect((await budgetOf(page, org.organisation)).evaluation_budget_usd).toMatch(/^0\.01/);
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    await test.step("[US15-52] the change is an Audit Event with before and after", async () => {
      const events = (await (await page.request.get(`${org.organisation}/audit-events?action=organisation.evaluation_budget_changed`)).json()) as {
        items: { action: string; before: Record<string, unknown> | null; after: Record<string, unknown> | null; actor: { email: string } | null }[];
      };
      expect(events.items).toHaveLength(1);
      expect(events.items[0]?.actor?.email).toBe(member.email);
      expect(JSON.stringify(events.items[0]?.before)).toContain("null");
      expect(JSON.stringify(events.items[0]?.after)).toContain("0.01");
      await openSection(page, "Organisation settings", "Audit");
      await page.getByRole("combobox", { name: "Action" }).selectOption("organisation.evaluation_budget_changed");
      await expect(
        page.getByRole("table", { name: "Audit Events" }).getByRole("row").filter({ hasText: "organisation.evaluation_budget_changed" }),
      ).toHaveCount(1, { timeout: 15_000 });
    });

    await test.step("[US15-55][US15-56] an Editor sets the Live sample rate, but can't change the Evaluation budget", async () => {
      await editor.goto(agent.path);
      await openAgentView(editor, "Embed & limits");
      const card = editor.getByRole("region", { name: "Live sample rate" });
      const rate = card.getByLabel("Visitor replies judged (%)");
      await expect(rate).toBeEnabled({ timeout: 15_000 });
      await rate.fill("100");
      await card.getByRole("button", { name: "Save Live sample rate" }).click();
      await expect(card.getByText("Saved. It applies to the next Visitor reply.")).toBeVisible({ timeout: 15_000 });

      await editor.goto(`/organisations/${org.organisationId}/settings/models`);
      await expect(editor.getByText("Evaluation budget: $0.01 a month")).toBeVisible({ timeout: 15_000 });
      await expect(editor.getByText("Only Owners can change the Evaluation budget.")).toBeVisible();
      await expect(editor.getByRole("form", { name: "Set the Evaluation budget" })).toHaveCount(0);
      expect((await editor.request.put(`${org.organisation}/evaluation-budget`, { data: { evaluation_budget_usd: "500.00" } })).status()).toBe(403);
      expect((await budgetOf(page, org.organisation)).evaluation_budget_usd).toMatch(/^0\.01/);
    });

    await judgeWithPriceyClaude(page, org.organisation);
    let firstCost = 0;

    await test.step("[US15-46][US15-47] the first judgement spends the budget: one email to the Owner, and sampling pauses", async () => {
      const [first] = await visitorAsks(visitor, agent, [PASSING_QUESTION]);
      await waitForJudged(page.request, agent, 1, 1);
      await expect.poll(async () => (await budgetOf(page, org.organisation)).exhausted, { timeout: 15_000 }).toBe(true);
      firstCost = Number((await budgetOf(page, org.organisation)).spent_usd);
      expect(firstCost).toBeGreaterThanOrEqual(0.01);
      expect((await liveVerdictOf(page.request, project, agent, first ?? ""))?.status).toBe("judged");

      await expect.poll(async () => (await emailsTo(page.request, member.email, SPENT_SUBJECT)).length, { timeout: 15_000 }).toBe(1);
      const [message] = await emailsTo(page.request, member.email, SPENT_SUBJECT);
      const text = await emailText(page.request, message?.ID ?? "");
      expect(text).toContain("this month's Evaluation budget of $0.01");
      expect(studioLink(text, "/settings/models")).toBe(`/organisations/${org.organisationId}/settings/models`);
    });

    await test.step("[US15-46][US15-50] once spent, a Visitor still gets their reply, which is not judged", async () => {
      const [second] = await visitorAsks(visitor, agent, [PASSING_QUESTION]);
      expect(await liveVerdictOf(page.request, project, agent, second ?? "")).toBeNull();
      // Its Trace says so.
      const conversation = await page.request.get(`${project}/conversations?agent_id=${agent.id}&live_verdict=not_judged`);
      const { items } = (await conversation.json()) as { items: { id: string }[] };
      expect(items).toHaveLength(1);
      await page.goto(`${project.replace(/^\/api/, "")}/conversations/${items[0]?.id ?? ""}`);
      const reply = page.getByRole("list", { name: "Messages" }).getByRole("listitem", { name: "Budgeted helper" });
      await expect(reply).toContainText("Demo model (canned answer, not AI)", { timeout: 15_000 });
      await reply.getByText("Trace", { exact: true }).click();
      await expect(reply.getByRole("region", { name: "Live Verdict" })).toContainText("Not judged: the Live sample rate didn't choose this reply.");
      // A second judgement-free reply sends no second email.
      expect(await emailsTo(page.request, member.email, SPENT_SUBJECT)).toHaveLength(1);
      expect((await liveScores(page.request, agent)).get(1)?.n).toBe(1);
    });

    await test.step("[US15-45] the meter shows this month's spend against the budget in Organisation settings and on the Cost page", async () => {
      for (const path of [`/organisations/${org.organisationId}/settings/models`, `/organisations/${org.organisationId}/cost`]) {
        await page.goto(path);
        const meter = page.getByRole("meter", { name: "Evaluation budget spent this month" });
        await expect(meter).toBeVisible({ timeout: 15_000 });
        await expect(meter).toHaveAttribute("aria-valuemax", "0.01");
        expect(Number(await meter.getAttribute("aria-valuenow"))).toBeCloseTo(firstCost, 6);
        await expect(page.getByText(/^Spent: no Visitor replies are judged until the budget is raised or the month ends on 1 /)).toBeVisible();
        expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      }
    });

    await test.step("[US15-53][US15-54] Live Verdict Cost is in Organisation cost's Evaluation column, never in the Version KPIs' cost or the Token Budget", async () => {
      const cost = await costToday(page, org.organisation);
      expect(Number(cost.evaluation_usd)).toBeCloseTo(firstCost, 6);
      // The demo model answers Visitors for nothing.
      expect(Number(cost.visitor_usd)).toBe(0);
      await expect(page.getByRole("table", { name: "Cost by Project" }).getByRole("row", { name: /^Budgeted/ })).toBeVisible({ timeout: 15_000 });
      const metrics = (await (await page.request.get(`${agent.api}/metrics`)).json()) as {
        versions: { cost: { total_usd: string }; tokens: { n: number; mean: number | null } }[];
      };
      const [v1] = metrics.versions;
      expect(Number(v1?.cost.total_usd)).toBe(0);
      // Today's Token Budget usage is the Visitor replies' tokens alone: the judge's aren't added.
      const usage = (await (await page.request.get(`${agent.api}/token-usage`)).json()) as { tokens_used: number };
      expect(usage.tokens_used).toBe(Math.round((v1?.tokens.mean ?? 0) * (v1?.tokens.n ?? 0)));
    });

    await test.step("[US15-51] an Evaluation Run the Editor starts while the budget is spent is judged in full", async () => {
      const added = await editor.request.post(`${agent.api}/evaluation/cases`, {
        data: { question: PASSING_QUESTION, reference_answer: 'Everyone gets "25 days of annual leave" a year.', expected_sources: [], expect_fallback: false, source: "written" },
      });
      expect(added.status(), await added.text()).toBe(201);
      const started = await editor.request.post(`${agent.api}/evaluation/runs`, { data: { sides: null } });
      expect(started.status(), await started.text()).toBe(202);
      const { id } = (await started.json()) as { id: string };
      await expect
        .poll(async () => ((await (await editor.request.get(`${agent.api}/evaluation/runs/${id}`)).json()) as { status: string }).status, { timeout: 120_000 })
        .toBe("completed");
      const run = (await (await editor.request.get(`${agent.api}/evaluation/runs/${id}`)).json()) as { cost: { judging_usd: string } };
      expect(Number(run.cost.judging_usd)).toBeGreaterThan(0);
      expect((await budgetOf(page, org.organisation)).exhausted).toBe(true);
    });

    await test.step("[US15-49] a new month (UTC) starts a new spend record: sampling resumes on the 1st without a job", async () => {
      // The stack's clock can't move, so this month's spend record is moved back a month instead:
      // what the 1st of next month looks like to the sampling check.
      const moved = psql(
        `UPDATE evaluation_spend SET month = (month - interval '1 month')::date WHERE organisation_id = '${org.organisationId}' AND month = date_trunc('month', now() AT TIME ZONE 'UTC')::date`,
      );
      expect(moved).toBe("UPDATE 1");
      const fresh = await budgetOf(page, org.organisation);
      expect([Number(fresh.spent_usd), fresh.exhausted]).toEqual([0, false]);
      const [third] = await visitorAsks(visitor, agent, [PASSING_QUESTION]);
      await waitForJudged(page.request, agent, 1, 2);
      expect((await liveVerdictOf(page.request, project, agent, third ?? ""))?.status).toBe("judged");
      // That judgement spends the new month's budget: that month's one email.
      await expect.poll(async () => (await emailsTo(page.request, member.email, SPENT_SUBJECT)).length, { timeout: 15_000 }).toBe(2);
    });

    await test.step("[US15-48] raising the budget resumes sampling at the next reply", async () => {
      await page.goto(`/organisations/${org.organisationId}/settings/models`);
      const form = page.getByRole("form", { name: "Set the Evaluation budget" });
      await form.getByLabel("Evaluation budget (US dollars a month)").fill("1000");
      await form.getByRole("button", { name: "Save Evaluation budget" }).click();
      await expect(page.getByText("The Evaluation budget is now $1,000.00 a month.")).toBeVisible({ timeout: 15_000 });
      expect((await budgetOf(page, org.organisation)).exhausted).toBe(false);
      const [fourth] = await visitorAsks(visitor, agent, [PASSING_QUESTION]);
      await waitForJudged(page.request, agent, 1, 3);
      expect((await liveVerdictOf(page.request, project, agent, fourth ?? ""))?.status).toBe("judged");
      expect(await emailsTo(page.request, member.email, SPENT_SUBJECT)).toHaveLength(2);
    });

    await test.step("[US15-44] removing the budget keeps the rate but stops all sampling", async () => {
      await page.getByRole("button", { name: "Remove Evaluation budget" }).click();
      await expect(page.getByText("The Evaluation budget is removed: no Visitor replies are judged.")).toBeVisible({ timeout: 15_000 });
      const [fifth] = await visitorAsks(visitor, agent, [PASSING_QUESTION]);
      expect(await liveVerdictOf(page.request, project, agent, fifth ?? "")).toBeNull();
      const settings = (await (await page.request.get(`${agent.api}/operational-settings`)).json()) as { live_sample_rate: number };
      expect(settings.live_sample_rate).toBe(100);
    });

    await visitorContext.close();
    await editor.context().close();
  });

  test("[US15-58] a Member of another Organisation never sees its Live Verdicts, Live score or Evaluation budget", async ({ signedInPage: page, browser }) => {
    test.setTimeout(240_000);
    const org = await demoOrganisation(page);
    await setEvaluationBudget(page.request, org.organisation, "5.00");
    const project = await projectWithHandbook(page, org, "Private");
    const agent = await liveAgent(page, project, "Private helper");
    await setSampleRate(page.request, agent, 100);
    const visitorContext = await browser.newContext();
    const [reply] = await visitorAsks(visitorContext.request, agent, [PASSING_QUESTION]);
    await visitorContext.close();
    await waitForJudged(page.request, agent, 1, 1);
    const listed = (await (await page.request.get(`${project}/conversations?agent_id=${agent.id}`)).json()) as { items: { id: string }[] };
    const conversation = listed.items[0]?.id ?? "";

    const outsiderContext = await browser.newContext();
    const outsider = await outsiderContext.newPage();
    await signUp(outsider.request, newMember());
    for (const path of [
      `${org.organisation}/evaluation-budget`,
      `${agent.api}/metrics`,
      `${agent.api}/time-series?metric=live_score`,
      `${project}/conversations?live_verdict=passed`,
      `${project}/conversations/${conversation}/messages/${reply ?? ""}/trace`,
    ]) {
      expect((await outsider.request.get(path)).status(), path).toBe(404);
    }
    expect((await outsider.request.put(`${org.organisation}/evaluation-budget`, { data: { evaluation_budget_usd: "1.00" } })).status()).toBe(404);
    await outsider.goto(`/organisations/${org.organisationId}/settings/models`);
    await expect(outsider.getByRole("meter", { name: "Evaluation budget spent this month" })).toHaveCount(0);
    await expect(outsider.getByText("Evaluation budget: $5.00 a month")).toHaveCount(0);
    await outsiderContext.close();
  });
});
