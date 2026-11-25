import type { Browser, Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { liveVersion, openAgentView } from "../fixtures/agent";
import { openSection } from "../fixtures/navigation";
import {
  CITE_LINE,
  CURT_PROMPT,
  GAP_TOPIC,
  type AgentOut,
  type Draft,
  type PublishedAgent,
  addCase,
  askAsVisitor,
  editDraft,
  finishedRun,
  finishedSuggestion,
  json,
  openSuggestions,
  publishedAgent,
  readAgent,
  startSuggestion,
  suggestionList,
  suggestionOrg,
  waitForFailedVerdicts,
} from "../fixtures/suggestion-org";

// Spec 16, "The check" and "Applying" (user stories 30–46). Each test signs up a fresh Owner and
// builds what it needs in their new Organisation (fixtures/suggestion-org.ts): an Agent published
// with a curt prompt the demo model answers uncited, a Visitor reply whose Live Verdict fails
// grounding, and a Suggestion run, for which the fake proposer adds CITE_LINE to the system prompt
// and names one Knowledge Base gap. Applying and publishing change the Agent, so none of this
// touches the seeded demo.
const SUGGESTED = `${CURT_PROMPT}\n${CITE_LINE}`;
const COLLEAGUE_PROMPT = "Answer staff questions in two short sentences. Don't quote the handbook.";
const LEAVE_CASE = { question: "How many days of annual leave do I get?", reference: 'Everyone gets "25 days of annual leave" a year.' };

/** A published Agent with one failed Live Verdict, an Evaluation Set of one case (unless `withSet` is false), and a finished Suggestion. */
async function agentWithSuggestion(
  page: Page,
  browser: Browser,
  org: Awaited<ReturnType<typeof suggestionOrg>>,
  name: string,
  { prompt = CURT_PROMPT, caseQuestion = LEAVE_CASE.question, withSet = true, edit = (draft: Draft) => draft } = {},
): Promise<PublishedAgent> {
  const agent = await publishedAgent(page, org, name, { systemPrompt: prompt, edit });
  if (withSet) await addCase(page, agent, caseQuestion, LEAVE_CASE.reference);
  await askAsVisitor(browser, agent.public_id, `Can I carry leave over to next year? (${name})`);
  await waitForFailedVerdicts(page, agent, 1);
  return agent;
}

function publishEvaluation(page: Page) {
  return page.getByRole("form", { name: "Publish" }).getByRole("region", { name: "Evaluation" });
}

async function openPublishDialog(page: Page) {
  await page.getByRole("banner").getByRole("button", { name: "Publish" }).click();
  await expect(publishEvaluation(page)).toBeVisible({ timeout: 15_000 });
}

async function closeDialog(page: Page) {
  await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();
}

/** The open Suggestion's detail, from the Suggestions tab. */
async function openOnlySuggestion(page: Page, agent: PublishedAgent) {
  await openSuggestions(page, agent);
  await expect(suggestionList(page).getByRole("listitem")).toHaveCount(1, { timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Apply to Draft" })).toBeVisible({ timeout: 15_000 });
}

function review(page: Page) {
  return page.getByRole("dialog", { name: "Apply to Draft" });
}

function reviewRow(page: Page) {
  return review(page).getByRole("list", { name: "Changes to the Draft" }).getByRole("listitem").filter({ hasText: "System prompt" });
}

test.describe("Suggestions: the check and applying", () => {
  test("[US16-30][US16-31][US16-35][US16-36][US16-37][US16-38][US16-39][US16-40][US16-41][US16-43][US16-44][US16-45][US16-46][US16-61] an Owner reviews a checked Suggestion against their Draft, meets a clash and a colleague's save, applies it, and nothing is Published", async ({
    signedInPage: page,
    browser,
    member,
    makeAxeBuilder,
  }) => {
    test.setTimeout(360_000);
    const org = await suggestionOrg(page);
    const agent = await agentWithSuggestion(page, browser, org, "Leave helper");
    const suggestionId = await startSuggestion(page.request, agent);
    const suggestion = await finishedSuggestion(page.request, agent, suggestionId);
    expect(suggestion.changes.map((change) => [change.path, change.base_value, change.suggested_value])).toEqual([
      ["behaviour.system_prompt", CURT_PROMPT, SUGGESTED],
    ]);

    await test.step("[US16-30][US16-31] the Suggestion shows its check against Version 1 on the Evaluation Set: both scores, and no Regressions", async () => {
      expect(suggestion.check?.state).toBe("clear");
      await openSuggestions(page, agent);
      await expect(suggestionList(page).getByRole("listitem").first()).toContainText("Check clear", { timeout: 15_000 });
      const check = page.getByRole("region", { name: "Check against the Evaluation Set" });
      await expect(check).toContainText("Version 1: 0% · Suggestion: 0%. No Regressions.");
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    await test.step("[US16-35] the check's Run is in the Agent's Run history, labelled a Suggestion's check, with the Suggestion as its second side", async () => {
      await page.getByRole("region", { name: "Check against the Evaluation Set" }).getByRole("link", { name: "Open the check in Run detail" }).click();
      const runs = page.getByRole("list", { name: "Evaluation Runs" });
      await expect(runs.getByRole("listitem")).toHaveCount(1, { timeout: 15_000 });
      await expect(runs.getByRole("listitem").first()).toContainText("Suggestion's check");
      await expect(runs.getByRole("listitem").first()).toContainText("Version 1: 0% · Suggestion on Version 1: 0%");
      await expect(page.getByRole("region", { name: /^Run of / })).toBeVisible();
    });

    // An unrelated edit to the Draft: the Suggestion doesn't change Top-k.
    let draft = await editDraft(page.request, agent.api, (current) => ({ ...current, retrieval: { ...current.retrieval, top_k: 4 } }));

    await test.step("[US16-36] the check doesn't count in the Publish dialog: the Draft hasn't been evaluated", async () => {
      await page.goto(agent.path);
      await openPublishDialog(page);
      await expect(publishEvaluation(page)).toContainText("The Draft hasn't been evaluated against the Live Version (v1) yet.");
      await closeDialog(page);
      const summary = await json<{ state: string }>(page.request, "GET", `${agent.api}/evaluation/publish-summary`);
      expect(summary.state).toBe("no_run");
    });

    // The Editor evaluates the Draft before applying, so applying is seen to make that Run stale.
    const run = await json<{ id: string }>(page.request, "POST", `${agent.api}/evaluation/runs`, { sides: null });
    expect((await finishedRun(page.request, agent, run.id)).status).toBe("completed");

    await test.step("[US16-37][US16-40] a Draft that changed the system prompt another way clashes: the review shows both values and applying is refused, writing nothing", async () => {
      draft = await editDraft(page.request, agent.api, (current) => ({ ...current, behaviour: { ...current.behaviour, system_prompt: COLLEAGUE_PROMPT } }));
      await openOnlySuggestion(page, agent);
      await page.getByRole("button", { name: "Apply to Draft" }).click();
      const row = reviewRow(page);
      await expect(row).toContainText("Clash", { timeout: 15_000 });
      await expect(row).toContainText(`In the Draft, set it back to ${CURT_PROMPT} or to the suggested value, then apply.`);
      const diff = row.getByRole("table", { name: "The system prompt: your Draft and the Suggestion" });
      await expect(diff).toContainText(COLLEAGUE_PROMPT);
      await expect(diff).toContainText(CITE_LINE);
      await expect(review(page).getByText("1 setting clashes with your Draft: it has changed them some other way.")).toBeVisible();
      await expect(review(page).getByRole("button", { name: "Apply to Draft" })).toBeDisabled();
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      await review(page).getByRole("button", { name: "Cancel" }).click();

      // The API refuses the same apply with every clash, and the Draft is as it was.
      const refused = await page.request.post(`${agent.api}/suggestions/${suggestionId}/apply`, { data: { base_revision: draft.draft_revision } });
      expect(refused.status()).toBe(409);
      expect(await refused.json()).toMatchObject({
        conflict: "suggestion_clash",
        clashes: [{ path: "behaviour.system_prompt", base_value: CURT_PROMPT, draft_value: COLLEAGUE_PROMPT, suggested_value: SUGGESTED }],
      });
      const after = await readAgent(page, agent);
      expect(after.draft_revision).toBe(draft.draft_revision);
      expect(after.draft.behaviour.system_prompt).toBe(COLLEAGUE_PROMPT);
    });

    await test.step("[US16-41][US16-40] a colleague saves a clash while the review is open: \"Save mine over theirs\" is refused with the clash listed", async () => {
      draft = await editDraft(page.request, agent.api, (current) => ({ ...current, behaviour: { ...current.behaviour, system_prompt: CURT_PROMPT } }));
      await page.reload();
      await openOnlySuggestion(page, agent);
      await page.getByRole("button", { name: "Apply to Draft" }).click();
      await expect(reviewRow(page)).toContainText("Will be applied", { timeout: 15_000 });
      await editDraft(page.request, agent.api, (current) => ({ ...current, behaviour: { ...current.behaviour, system_prompt: COLLEAGUE_PROMPT } }));
      await review(page).getByRole("button", { name: "Apply to Draft" }).click();
      const conflict = review(page).getByRole("alert").filter({ hasText: "Someone else saved this Draft while you were editing" });
      await expect(conflict).toBeVisible({ timeout: 15_000 });
      await expect(conflict.getByRole("button", { name: "Load their changes" })).toBeVisible();
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      await conflict.getByRole("button", { name: "Save mine over theirs" }).click();
      const clashes = review(page).getByRole("list", { name: "Clashes" });
      await expect(clashes).toHaveText(`System prompt: was ${CURT_PROMPT}, your Draft has ${COLLEAGUE_PROMPT}, the Suggestion has ${SUGGESTED}.`, {
        timeout: 15_000,
      });
      await expect(review(page).getByText("Your Draft has also changed settings this Suggestion changes.")).toBeVisible();
      await review(page).getByRole("button", { name: "Cancel" }).click();
      expect((await readAgent(page, agent)).draft.behaviour.system_prompt).toBe(COLLEAGUE_PROMPT);
    });

    let before: AgentOut;
    await test.step("[US16-41][US16-39][US16-38][US16-61] with the keyboard: a colleague's unrelated save is loaded with \"Load their changes\", then the whole Suggestion is applied in one save", async () => {
      await editDraft(page.request, agent.api, (current) => ({ ...current, behaviour: { ...current.behaviour, system_prompt: CURT_PROMPT } }));
      await page.reload();
      await openOnlySuggestion(page, agent);
      const apply = page.getByRole("button", { name: "Apply to Draft" });
      await apply.focus();
      await page.keyboard.press("Enter");
      await expect(reviewRow(page)).toContainText("Will be applied", { timeout: 15_000 });
      // The review dialog has taken focus, Escape closes it and gives focus back.
      await expect.poll(() => review(page).evaluate((dialog) => dialog.contains(document.activeElement))).toBe(true);
      await page.keyboard.press("Escape");
      await expect(review(page)).toHaveCount(0);
      await expect(apply).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(reviewRow(page)).toContainText("Will be applied", { timeout: 15_000 });

      // A colleague saves an unrelated change: the Hybrid weighting.
      await editDraft(page.request, agent.api, (current) => ({ ...current, retrieval: { ...current.retrieval, hybrid_weight: 0.6 } }));
      await review(page).getByRole("button", { name: "Apply to Draft" }).click();
      const conflict = review(page).getByRole("alert").filter({ hasText: "Someone else saved this Draft while you were editing" });
      await conflict.getByRole("button", { name: "Load their changes" }).focus();
      await page.keyboard.press("Enter");
      await expect(conflict).toHaveCount(0);
      await expect(reviewRow(page)).toContainText("Will be applied");
      before = await readAgent(page, agent);
      await review(page).getByRole("button", { name: "Apply to Draft" }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByText("Applied to the Draft. Evaluate it again before Publishing.")).toBeVisible({ timeout: 15_000 });

      const after = await readAgent(page, agent);
      expect(after.draft_revision).toBe(before.draft_revision + 1);
      expect(after.draft.behaviour.system_prompt).toBe(SUGGESTED);
      // The Draft's own edit and the colleague's are kept.
      expect(after.draft.retrieval.top_k).toBe(4);
      expect(after.draft.retrieval.hybrid_weight).toBe(0.6);
    });

    await test.step("[US16-43][US16-44] applying didn't Publish: Version 1 is still Live, and the Publish dialog asks for a new Evaluation Run", async () => {
      const after = await readAgent(page, agent);
      expect(after.live_version?.number).toBe(1);
      expect((await json<{ versions: unknown[] }>(page.request, "GET", `${agent.api}/versions`)).versions).toHaveLength(1);
      await page.goto(agent.path);
      await expect(liveVersion(page, 1)).toBeVisible({ timeout: 15_000 });
      await openPublishDialog(page);
      await expect(publishEvaluation(page).getByText(/The Draft has changed since it was evaluated/)).toBeVisible();
      await expect(publishEvaluation(page).getByRole("button", { name: "Evaluate" })).toBeVisible();
      await closeDialog(page);
    });

    await test.step("[US16-45] the Suggestion is marked applied, with who and when", async () => {
      await openAgentView(page, "Evaluation");
      await page.getByRole("radiogroup", { name: "Evaluation view" }).getByRole("radio", { name: "Suggestions" }).click();
      const item = suggestionList(page).getByRole("listitem").first();
      await expect(item).toContainText(`Applied by ${member.name}, `, { timeout: 15_000 });
      await expect(page.getByText(new RegExp(`^Applied by ${member.name}, .+\\.$`))).toBeVisible();
      const read = await json<{ applied_by: { name: string } | null; applied_at: string | null }>(page.request, "GET", `${agent.api}/suggestions/${suggestionId}`);
      expect(read.applied_by?.name).toBe(member.name);
      expect(read.applied_at).not.toBeNull();
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    await test.step("[US16-46] applying is in the Audit tab, with the paths written and no text", async () => {
      await page.goto("/");
      await openSection(page, "Organisation sections", "Settings");
      await openSection(page, "Organisation settings", "Audit");
      await page.getByLabel("Action").selectOption("agent.suggestion_applied");
      const row = page.getByRole("table", { name: "Audit Events" }).getByRole("row").filter({ hasText: "agent.suggestion_applied" });
      await expect(row).toHaveCount(1, { timeout: 15_000 });
      await expect(row).toContainText(member.name);
      await expect(row).toContainText(`"suggestion_id":"${suggestionId}"`);
      await expect(row).toContainText('"paths":["behaviour.system_prompt"]');
      await expect(row).not.toContainText(CITE_LINE);
    });
  });

  test("[US16-32][US16-42][US16-41] a check where every answer errored warns but still applies; once a new Version is Live the Suggestion is stale, and \"Save mine over theirs\" applies it over a colleague's save", async ({
    signedInPage: page,
    browser,
    makeAxeBuilder,
  }) => {
    test.setTimeout(300_000);
    const org = await suggestionOrg(page);
    // The fake gateway's chat model fails as a provider would when a question asks it to. The
    // input Guardrail only logs, so the local classifier doesn't block that question first.
    const agent = await agentWithSuggestion(page, browser, org, "Outage helper", {
      caseQuestion: "How many days of annual leave do I get? Please simulate an invalid key.",
      edit: (draft) => ({ ...draft, guardrails: { ...(draft.guardrails as Record<string, unknown>), input_mode: "log" } }),
    });
    // From now on the Organisation answers with the fake Claude, so the check's answers error.
    await json(page.request, "PUT", `${org.organisation}/default-model`, { credential_id: org.claudeCredentialId, model: "claude-haiku-4-5" });
    const suggestionId = await startSuggestion(page.request, agent);
    const suggestion = await finishedSuggestion(page.request, agent, suggestionId);
    expect(suggestion.status).toBe("completed");
    expect(suggestion.check?.state).toBe("failed");

    await test.step("[US16-32] the failed check is a warning, and Apply to Draft is offered", async () => {
      await openSuggestions(page, agent);
      await expect(suggestionList(page).getByRole("listitem").first()).toContainText("Check failed", { timeout: 15_000 });
      const check = page.getByRole("region", { name: "Check against the Evaluation Set" });
      await expect(check).toContainText("The check failed: every answer errored. This is a warning; you can still apply it.");
      await expect(page.getByRole("button", { name: "Apply to Draft" })).toBeEnabled();
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    await test.step("[US16-42] a new Version goes Live: the Suggestion is marked stale, and its review warns that its check was against the old Live", async () => {
      await editDraft(page.request, agent.api, (current) => ({ ...current, retrieval: { ...current.retrieval, top_k: 4 } }));
      await json(page.request, "POST", `${agent.api}/versions`, { note: "Fewer Chunks" });
      await openSuggestions(page, agent);
      await expect(suggestionList(page).getByRole("listitem").first()).toContainText("Stale", { timeout: 15_000 });
      await expect(page.getByText("Made from Version 1, which is no longer Live: its check was against the old Live Version. You can still apply it.")).toBeVisible();
      await page.getByRole("button", { name: "Apply to Draft" }).click();
      await expect(review(page).getByText("This Suggestion was made from v1, which is no longer Live: its check was against the old Live Version.")).toBeVisible({
        timeout: 15_000,
      });
      await expect(reviewRow(page)).toContainText("Will be applied");
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    await test.step("[US16-41][US16-42] a colleague saves while the review is open; \"Save mine over theirs\" applies the stale Suggestion onto their Draft", async () => {
      await editDraft(page.request, agent.api, (current) => ({ ...current, retrieval: { ...current.retrieval, hybrid_weight: 0.6 } }));
      await review(page).getByRole("button", { name: "Apply to Draft" }).click();
      const conflict = review(page).getByRole("alert").filter({ hasText: "Someone else saved this Draft while you were editing" });
      await conflict.getByRole("button", { name: "Save mine over theirs" }).click();
      await expect(page.getByText("Applied to the Draft. Evaluate it again before Publishing.")).toBeVisible({ timeout: 15_000 });
      const after = await readAgent(page, agent);
      expect(after.draft.behaviour.system_prompt).toBe(SUGGESTED);
      expect(after.draft.retrieval.hybrid_weight).toBe(0.6);
      expect(after.live_version?.number).toBe(2);
    });
  });

  test("[US16-33][US16-34] without an Evaluation Set a change is marked Not checked; a Suggestion with only a Knowledge Base gap is never checked", async ({
    signedInPage: page,
    browser,
    makeAxeBuilder,
  }) => {
    test.setTimeout(300_000);
    const org = await suggestionOrg(page);
    const unchecked = await agentWithSuggestion(page, browser, org, "Unchecked helper", { withSet: false });
    // Its prompt already asks for citations, so the fake proposer suggests no change, only a gap.
    const gapsOnly = await agentWithSuggestion(page, browser, org, "Citing helper", { prompt: SUGGESTED });
    const [notChecked, gaps] = await Promise.all([
      finishedSuggestion(page.request, unchecked, await startSuggestion(page.request, unchecked)),
      finishedSuggestion(page.request, gapsOnly, await startSuggestion(page.request, gapsOnly)),
    ]);

    await test.step("[US16-33] no Evaluation Set: the change is marked Not checked and nothing was spent checking", async () => {
      expect(notChecked.outcome).toBe("changes");
      expect(notChecked.check).toMatchObject({ state: "not_checked", evaluation_run_id: null });
      expect(notChecked.cost.checking_usd).toBeNull();
      await openSuggestions(page, unchecked);
      await expect(suggestionList(page).getByRole("listitem").first()).toContainText("Not checked", { timeout: 15_000 });
      await expect(page.getByRole("region", { name: "Check against the Evaluation Set" })).toContainText(
        "Not checked: this Agent had no Evaluation Set, so nothing verified this Suggestion.",
      );
      await expect(page.getByRole("button", { name: "Apply to Draft" })).toBeVisible();
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    await test.step("[US16-34] only a gap: no configuration change, so no check and no Run, though the Agent has an Evaluation Set", async () => {
      expect(gaps.outcome).toBe("gaps_only");
      expect(gaps.changes).toEqual([]);
      expect(gaps.check).toBeNull();
      expect(gaps.cost.checking_usd).toBeNull();
      const runs = await json<{ kind: string }[]>(page.request, "GET", `${gapsOnly.api}/evaluation/runs`);
      expect(runs.filter((each) => each.kind === "suggestion")).toEqual([]);
      await openSuggestions(page, gapsOnly);
      const item = suggestionList(page).getByRole("listitem").first();
      await expect(item).toContainText("No configuration change", { timeout: 15_000 });
      await expect(item).not.toContainText(/Check|Not checked/);
      await expect(page.getByText("No configuration change.", { exact: true })).toBeVisible();
      await expect(page.getByRole("region", { name: "Check against the Evaluation Set" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Apply to Draft" })).toHaveCount(0);
      await expect(page.getByRole("list", { name: "Knowledge Base gaps" }).getByRole("heading", { level: 5 })).toHaveText([GAP_TOPIC]);
    });
  });
});
