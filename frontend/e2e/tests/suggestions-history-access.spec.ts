import type { Browser, Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { agentAction } from "../fixtures/agent";
import { newMember, signIn, signUp } from "../fixtures/auth";
import { openSection } from "../fixtures/navigation";
import {
  CITE_LINE,
  CURT_PROMPT,
  EVALUATION_MODEL,
  type PublishedAgent,
  type SuggestionOrg,
  addCase,
  askAsVisitor,
  finishedSuggestion,
  json,
  openSuggestions,
  publishedAgent,
  readSuggestion,
  startSuggestion,
  suggestionList,
  suggestionOrg,
  waitForFailedVerdicts,
} from "../fixtures/suggestion-org";

// Spec 16, "Cost, permissions, demo and accessibility" (user stories 52–59 and 61). Each test signs
// up a fresh Owner and builds its Suggestions in their new Organisation (fixtures/suggestion-org.ts):
// the demo model answers (free), and the fake Claude, the Evaluation Model, judges and proposes at
// a price. The demo's seeded Suggestion (story 60) is read in suggestions-history-retention.spec.ts.
const LEAVE_CASE = { question: "How many days of annual leave do I get?", reference: 'Everyone gets "25 days of annual leave" a year.' };

/** A published Agent with one failed Live Verdict (and an Evaluation Set of `cases` cases). */
async function agentWithEvidence(page: Page, browser: Browser, org: SuggestionOrg, name: string, cases = 1): Promise<PublishedAgent> {
  const agent = await publishedAgent(page, org, name, { systemPrompt: CURT_PROMPT });
  for (let index = 1; index <= cases; index++) {
    await addCase(page, agent, cases === 1 ? LEAVE_CASE.question : `${LEAVE_CASE.question} (${String(index)})`, LEAVE_CASE.reference);
  }
  await askAsVisitor(browser, agent.public_id, `Can I carry leave over to next year? (${name})`);
  await waitForFailedVerdicts(page, agent, 1);
  return agent;
}

/** The Organisation's Evaluation spend over the last 30 days, through the Cost API (Owners only). */
async function evaluationSpend(page: Page, org: SuggestionOrg): Promise<number> {
  const cost = await json<{ total: { evaluation_usd: string } }>(page.request, "GET", `${org.organisation}/cost`);
  return Number(cost.total.evaluation_usd);
}

/** Adds a new Editor to the Owner's Organisation through an Invite Link, signed in in their own browser. */
async function newEditor(owner: Page, browser: Browser, org: SuggestionOrg, name: string): Promise<Page> {
  const person = newMember({ name });
  const invited = await json<{ link: string }>(owner.request, "POST", `${org.organisation}/invites`, { email: person.email, role: "editor", send_email: false });
  const token = new URL(invited.link).searchParams.get("token") ?? "";
  const page = await (await browser.newContext()).newPage();
  await json(page.request, "POST", "/api/invites/sign-up", { token, name: person.name, password: person.password });
  return page;
}

test.describe("Suggestions: Cost, permissions and accessibility", () => {
  test("[US16-52][US16-53][US16-54][US16-61] with the keyboard, an Owner starts a Suggestion run with no Evaluation budget; the Evaluation Model proposes it, and its Cost is frozen and counted in Organisation cost's Evaluation column", async ({
    signedInPage: page,
    browser,
    makeAxeBuilder,
  }) => {
    test.setTimeout(300_000);
    const org = await suggestionOrg(page);
    const agent = await agentWithEvidence(page, browser, org, "Costed helper");
    // The Live Verdict's judging is spent before the run starts: what the run adds is its own.
    await expect.poll(async () => (await json<{ spent_usd: string }>(page.request, "GET", `${org.organisation}/evaluation-budget`)).spent_usd, { timeout: 30_000 }).not.toBe("0");
    const before = await evaluationSpend(page, org);

    await test.step("[US16-53] the Owner removes the Evaluation budget, which stops Live Verdicts but never Suggestion runs", async () => {
      const budget = await json<{ evaluation_budget_usd: string | null }>(page.request, "PUT", `${org.organisation}/evaluation-budget`, { evaluation_budget_usd: null });
      expect(budget.evaluation_budget_usd).toBeNull();
    });

    await test.step("[US16-61][US16-53] the Suggestions tab and run dialog work from the keyboard and announce the evidence and estimate", async () => {
      await openSuggestions(page, agent);
      await expect(page.getByRole("heading", { name: "No Suggestions yet" })).toBeVisible({ timeout: 15_000 });
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      const suggest = page.getByRole("button", { name: "Suggest changes" });
      await suggest.focus();
      await page.keyboard.press("Enter");
      const dialog = page.getByRole("dialog", { name: "Suggest changes" });
      await expect.poll(() => dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
      await expect(dialog.getByRole("status", { name: "Evidence in the range" })).toHaveText(
        "1 piece of evidence: 1 failed Live Verdict, 0 thumbs-down, 0 rated 1 or 2, 0 failed Evaluation Cases",
        { timeout: 15_000 },
      );
      await expect(dialog.getByText("Fewer than 10 pieces of evidence: the Suggestion is likely to be noise. You can still start it.")).toBeVisible();
      await expect(dialog.getByRole("status", { name: "Estimated Cost" })).toHaveText(/^About \$\S+: proposing \$\S+, checking against the Evaluation Set \$\S+$/);
      await expect(dialog.getByText(/The Evaluation budget never applies\./)).toBeVisible();
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      // Escape closes the dialog and gives focus back; Enter opens it again.
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(suggest).toBeFocused();
      await page.keyboard.press("Enter");
      await dialog.getByRole("button", { name: "Start Suggestion run" }).focus();
      await page.keyboard.press("Enter");
      await expect(dialog).toHaveCount(0);
      const item = suggestionList(page).getByRole("listitem").first();
      await expect(item).toContainText("Completed", { timeout: 120_000 });
      await expect(item).toContainText("Check clear", { timeout: 120_000 });
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    const listed = await json<{ id: string }[]>(page.request, "GET", `${agent.api}/suggestions`);
    const suggestionId = listed[0]?.id ?? "";

    await test.step("[US16-54] the Evaluation Model proposed it, not the demo model the Agent answers with", async () => {
      await expect(page.getByText(`Proposed by anthropic:${EVALUATION_MODEL}.`, { exact: false })).toBeVisible();
      const read = await readSuggestion(page.request, agent, suggestionId);
      expect([read.model_provider, read.model_name]).toEqual(["anthropic", EVALUATION_MODEL]);
      const run = await json<{ judge_provider: string; judge_model: string }>(page.request, "GET", `${agent.api}/evaluation/runs/${read.check?.evaluation_run_id ?? ""}`);
      expect([run.judge_provider, run.judge_model]).toEqual(["anthropic", EVALUATION_MODEL]);
    });

    await test.step("[US16-52] proposing and checking each have a frozen Cost, shown on the Suggestion and added to Organisation cost's Evaluation column", async () => {
      const read = await finishedSuggestion(page.request, agent, suggestionId);
      const proposing = Number(read.cost.proposing_usd);
      const checking = Number(read.cost.checking_usd);
      expect(proposing).toBeGreaterThan(0);
      expect(checking).toBeGreaterThan(0);
      await expect(page.getByText(/^Proposing cost \$\S+ \(estimated \$\S+\)\. Checking cost \$\S+ \(estimated \$\S+\)\.$/)).toBeVisible();
      await expect.poll(async () => (await evaluationSpend(page, org)) - before, { timeout: 30_000 }).toBeCloseTo(proposing + checking, 9);
      // Frozen: read again, it hasn't moved.
      expect((await readSuggestion(page.request, agent, suggestionId)).cost).toEqual(read.cost);

      await page.goto(`/organisations/${org.organisationId}/projects`);
      await openSection(page, "Organisation sections", "Cost");
      const row = page.getByRole("table", { name: "Cost by Project" }).getByRole("row", { name: new RegExp(`^${org.projectName}`) });
      await expect(row).toBeVisible({ timeout: 15_000 });
      await expect(row.getByRole("cell").nth(3)).not.toHaveText("$0.00");
    });
  });

  test("[US16-55][US16-56] an Editor reads the Owner's Suggestion, starts and cancels a run, applies and deletes Suggestions", async ({ signedInPage: owner, browser, member }) => {
    test.setTimeout(360_000);
    const org = await suggestionOrg(owner);
    const agent = await agentWithEvidence(owner, browser, org, "Shared helper");
    const ownersId = await startSuggestion(owner.request, agent);
    await finishedSuggestion(owner.request, agent, ownersId);
    // From now on a check answers 10 cases 9 times on each side: long enough to cancel.
    await json(owner.request, "PUT", `${org.organisation}/evaluation-repeats`, { repeats: 9 });
    for (let index = 2; index <= 10; index++) await addCase(owner, agent, `${LEAVE_CASE.question} (${String(index)})`, LEAVE_CASE.reference);
    const editor = await newEditor(owner, browser, org, "Suggestions Editor");

    await test.step("[US16-56] the Editor reads the Owner's Suggestion", async () => {
      await openSuggestions(editor, agent);
      await expect(suggestionList(editor).getByRole("listitem")).toHaveCount(1, { timeout: 15_000 });
      await expect(editor.getByRole("table", { name: "Suggested change to the system prompt" })).toContainText(CITE_LINE);
      await expect(editor.getByRole("region", { name: "Check against the Evaluation Set" })).toContainText("Version 1: 0% · Suggestion: 0%");
    });

    await test.step("[US16-55] the Editor starts a run and cancels it while it runs; it keeps what it spent", async () => {
      await editor.getByRole("button", { name: "Suggest changes" }).click();
      const dialog = editor.getByRole("dialog", { name: "Suggest changes" });
      await expect(dialog.getByRole("status", { name: "Evidence in the range" })).toContainText("1 failed Live Verdict", { timeout: 15_000 });
      await dialog.getByRole("button", { name: "Start Suggestion run" }).click();
      const cancel = editor.getByRole("button", { name: "Cancel run" });
      await expect(cancel).toBeVisible({ timeout: 15_000 });
      await cancel.click();
      await expect(editor.getByText("This run was cancelled. It stopped before its next phase and keeps what it spent.")).toBeVisible({ timeout: 30_000 });
      await expect(suggestionList(editor).getByRole("listitem").first()).toContainText("Cancelled");
    });

    await test.step("[US16-55] the Editor applies the Owner's Suggestion to the Draft", async () => {
      await suggestionList(editor).getByRole("listitem").nth(1).getByRole("button", { name: /^Suggestion of / }).click();
      await editor.getByRole("button", { name: "Apply to Draft" }).click();
      const review = editor.getByRole("dialog", { name: "Apply to Draft" });
      await expect(review.getByRole("list", { name: "Changes to the Draft" })).toContainText("Will be applied", { timeout: 15_000 });
      await review.getByRole("button", { name: "Apply to Draft" }).click();
      await expect(editor.getByText("Applied to the Draft. Evaluate it again before Publishing.")).toBeVisible({ timeout: 15_000 });
      await expect(suggestionList(editor).getByRole("listitem").nth(1)).toContainText("Applied by Suggestions Editor, ");
    });

    await test.step("[US16-55] the Editor deletes the cancelled run", async () => {
      await suggestionList(editor).getByRole("listitem").first().getByRole("button", { name: /^Suggestion of / }).click();
      await editor.getByRole("button", { name: "Delete Suggestion" }).click();
      await editor.getByRole("alertdialog", { name: "Delete this Suggestion?" }).getByRole("button", { name: "Delete Suggestion" }).click();
      await expect(editor.getByText("Suggestion deleted.")).toBeVisible({ timeout: 15_000 });
      await expect(suggestionList(editor).getByRole("listitem")).toHaveCount(1);
    });

    await test.step("[US16-56] the Owner reads what the Editor did", async () => {
      await openSuggestions(owner, agent);
      await expect(suggestionList(owner).getByRole("listitem")).toHaveCount(1, { timeout: 15_000 });
      await expect(suggestionList(owner).getByRole("listitem").first()).toContainText("Applied by Suggestions Editor, ");
      expect(member.name).not.toBe("Suggestions Editor");
    });
    await editor.context().close();
  });

  test("[US16-57][US16-58][US16-59] an archived Agent's Suggestions stay readable but read only until it is restored, Permanent deletion takes them, and another Organisation never reaches them", async ({
    signedInPage: page,
    browser,
    makeAxeBuilder,
  }) => {
    test.setTimeout(300_000);
    const org = await suggestionOrg(page);
    const agent = await agentWithEvidence(page, browser, org, "Archived helper", 0);
    const suggestionId = await startSuggestion(page.request, agent);
    await finishedSuggestion(page.request, agent, suggestionId);
    const suggestion = `${agent.api}/suggestions/${suggestionId}`;
    const { draft_revision: revision } = await json<{ draft_revision: number }>(page.request, "GET", `${suggestion}/diff`);

    await test.step("[US16-59] a Member of another Organisation can't see or reach the Suggestions", async () => {
      const stranger = await browser.newContext();
      const outsider = newMember({ name: "Outsider" });
      await signUp(stranger.request, outsider);
      await signIn(stranger.request, outsider);
      const reads = [`${agent.api}/suggestions`, suggestion, `${suggestion}/diff`, `${agent.api}/suggestions/evidence`];
      for (const url of reads) expect((await stranger.request.get(url)).status(), url).toBe(404);
      expect((await stranger.request.post(`${agent.api}/suggestions`, { data: {} })).status()).toBe(404);
      expect((await stranger.request.post(`${suggestion}/apply`, { data: { base_revision: revision } })).status()).toBe(404);
      expect((await stranger.request.post(`${suggestion}/cancel`)).status()).toBe(404);
      expect((await stranger.request.delete(suggestion)).status()).toBe(404);
      // Their own Organisation's path to it doesn't reach it either.
      const theirs = (await (await stranger.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
      const crossed = suggestion.replace(org.organisationId, theirs.organisations[0]?.id ?? "");
      expect((await stranger.request.get(crossed)).status()).toBe(404);
      await stranger.close();
      // Nothing was changed for the Owner.
      expect((await readSuggestion(page.request, agent, suggestionId)).applied_at).toBeNull();
    });

    await test.step("[US16-57] archived: the Suggestion reads, but no run starts and it can't be applied or deleted", async () => {
      await page.goto(agent.path);
      await expect(page.getByRole("heading", { level: 1, name: agent.name })).toBeVisible({ timeout: 15_000 });
      await agentAction(page, "Archive");
      await page.getByRole("alertdialog", { name: `Archive ${agent.name}?` }).getByRole("button", { name: `Yes, archive ${agent.name}` }).click();
      await expect(page.getByRole("status", { name: "Archived" })).toContainText("This Agent is archived.");
      await openSuggestions(page, agent);
      await expect(page.getByText("This Agent is archived: its Suggestions are read only, and it starts no Suggestion run.")).toBeVisible({ timeout: 15_000 });
      await expect(suggestionList(page).getByRole("listitem")).toHaveCount(1);
      await expect(page.getByRole("table", { name: "Suggested change to the system prompt" })).toContainText(CITE_LINE);
      await expect(page.getByRole("button", { name: "Suggest changes" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Apply to Draft" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Delete Suggestion" })).toHaveCount(0);
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      expect((await page.request.post(`${agent.api}/suggestions`, { data: {} })).status()).toBe(409);
      expect((await page.request.post(`${suggestion}/apply`, { data: { base_revision: revision } })).status()).toBe(409);
      expect((await page.request.delete(suggestion)).status()).toBe(409);
    });

    await test.step("[US16-57] restoring the Agent brings its Suggestions back to use", async () => {
      await page.getByRole("status", { name: "Archived" }).getByRole("button", { name: `Restore ${agent.name}` }).click();
      await expect(page.getByRole("status", { name: "Archived" })).toHaveCount(0, { timeout: 15_000 });
      await openSuggestions(page, agent);
      await expect(suggestionList(page).getByRole("listitem")).toHaveCount(1, { timeout: 15_000 });
      await expect(page.getByRole("button", { name: "Apply to Draft" })).toBeVisible({ timeout: 15_000 });
      await expect(page.getByRole("button", { name: "Suggest changes" })).toBeEnabled();
    });

    await test.step("[US16-58] Permanent deletion of the Agent takes its Suggestions with it", async () => {
      await agentAction(page, "Archive");
      await page.getByRole("alertdialog", { name: `Archive ${agent.name}?` }).getByRole("button", { name: `Yes, archive ${agent.name}` }).click();
      await expect(page.getByRole("status", { name: "Archived" })).toBeVisible({ timeout: 15_000 });
      await agentAction(page, "Delete permanently");
      const confirm = page.getByRole("alertdialog", { name: `Delete ${agent.name} permanently` });
      await confirm.getByLabel(`Type ${agent.name} to confirm`).fill(agent.name);
      await confirm.getByRole("button", { name: `Delete ${agent.name} permanently` }).click();
      await expect(page.getByText(`${agent.name} was deleted permanently.`)).toBeVisible({ timeout: 15_000 });
      expect((await page.request.get(suggestion)).status()).toBe(404);
      expect((await page.request.get(`${agent.api}/suggestions`)).status()).toBe(404);
    });
  });
});
