import { expect, test } from "../fixtures";
import { openAgentView, publishAgent } from "../fixtures/agent";
import { openSection } from "../fixtures/navigation";
import {
  addCase,
  buildOrganisation,
  call,
  evidence,
  newAgent,
  readSuggestion,
  visit,
  waitForFailedVerdicts,
} from "../fixtures/suggestion-evidence";

// A fresh Owner's Organisation (see `fixtures/suggestion-evidence.ts`). The Evaluation Model is the
// fake gateway's Claude, which has a price, so estimates and spend are real figures. The Evaluation
// Set has 20 cases: an Evaluation Run of the Live Version, and a Suggestion's check (two sides),
// each take several seconds, long enough to see them in progress.
const CASES = 20;
const NEVER_PUBLISHED = "This Agent has never been Published, so it has no Live Version replies to suggest changes from. Publish it first.";
const EVALUATION_RUN_IN_PROGRESS = "This Agent has an Evaluation Run in progress. Wait for it to finish, or cancel it, then suggest changes.";
const SUGGESTION_IN_PROGRESS = "This Agent already has a Suggestion run in progress. Wait for it to finish, or cancel it.";
const SUGGESTION_BLOCKS_EVALUATE = "This Agent has a Suggestion run in progress. Wait for it to finish, or cancel it, then evaluate.";

const utcDay = (offsetDays: number) => new Date(Date.now() + offsetDays * 86_400_000).toISOString().slice(0, 10);

test.describe("Starting a Suggestion run", () => {
  test("[US16-1] [US16-2] [US16-3] [US16-4] [US16-5] [US16-7] [US16-8] [US16-9] [US16-10] [US16-11] an Owner starts, watches and cancels a Suggestion run, one Run at a time", async ({
    signedInPage: page,
    browser,
    makeAxeBuilder,
  }) => {
    test.setTimeout(420_000);
    const built = await buildOrganisation(page, "Suggestion runs HR");
    const name = "Run HR helper";
    const agent = await newAgent(page, built, name);
    for (let n = 1; n <= CASES; n += 1) await addCase(page, agent.api, `How many days of annual leave do I get? (${String(n)})`, 'It says "purple elephants".');

    await test.step("[US16-1] [US16-7] the Suggestions tab sits beside the Evaluation Set; starting is refused until the Agent is Published", async () => {
      await page.goto(`/organisations/${built.organisationId}/projects/${built.projectId}`);
      await openSection(page, "Project sections", "Agents");
      await page.getByRole("link", { name, exact: true }).click();
      await expect(page.getByRole("heading", { level: 1, name })).toBeVisible({ timeout: 15_000 });
      await openAgentView(page, "Evaluation");
      const tabs = page.getByRole("radiogroup", { name: "Evaluation view" });
      await expect(tabs.getByRole("radio")).toHaveText(["Evaluation Set and Runs", "Suggestions"]);
      await tabs.getByRole("radio", { name: "Suggestions" }).click();
      await expect(page.getByRole("heading", { level: 2, name: "Suggestions" })).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText("Publish this Agent first: a Suggestion is made from its Live Version's replies.")).toBeVisible();
      await expect(page.getByRole("button", { name: "Suggest changes" })).toBeDisabled();
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      const refused = await page.request.post(`${agent.api}/suggestions`, { data: {} });
      expect(refused.status()).toBe(409);
      expect(((await refused.json()) as { detail: string }).detail).toBe(NEVER_PUBLISHED);
    });

    await test.step("publish it, and two Visitor replies fail their Live Verdicts", async () => {
      await publishAgent(page, "Short answers");
      const visitor = await visit(browser, agent.publicId);
      await visitor.ask("How many days of annual leave do I get?");
      await visitor.ask("Can I carry leave over to next year?");
      await visitor.close();
      await waitForFailedVerdicts(page, agent.api, 2);
    });

    const dialog = page.getByRole("dialog", { name: "Suggest changes" });
    const counted = dialog.getByRole("status", { name: "Evidence in the range" });

    await test.step("[US16-2] [US16-3] [US16-4] [US16-5] the dialog: the last 14 UTC days, the evidence by kind with a noise warning, and the estimated Cost split", async () => {
      await openAgentView(page, "Evaluation");
      await page.getByRole("radiogroup", { name: "Evaluation view" }).getByRole("radio", { name: "Suggestions" }).click();
      await expect(page.getByRole("heading", { name: "No Suggestions yet" })).toBeVisible({ timeout: 15_000 });
      await page.getByRole("button", { name: "Suggest changes" }).click();
      await expect(dialog.getByLabel("From (UTC day)")).toHaveValue(utcDay(-13));
      await expect(dialog.getByLabel("To (UTC day)")).toHaveValue(utcDay(0));
      await expect(counted).toHaveText("2 pieces of evidence: 2 failed Live Verdicts, 0 thumbs-down, 0 rated 1 or 2, 0 failed Evaluation Cases", { timeout: 15_000 });
      await expect(dialog.getByText("Fewer than 10 pieces of evidence: the Suggestion is likely to be noise. You can still start it.")).toBeVisible();
      await expect(dialog.getByRole("button", { name: "Start Suggestion run" })).toBeEnabled();
      const estimate = await call<{ proposing_usd: string; checking_usd: string; total_usd: string }>(page.request, "POST", `${agent.api}/suggestions/estimate`, {});
      expect(Number(estimate.proposing_usd)).toBeGreaterThan(0);
      expect(Number(estimate.checking_usd)).toBeGreaterThan(0);
      await expect(dialog.getByRole("status", { name: "Estimated Cost" })).toHaveText(
        /^About \$\d+\.\d+: proposing \$\d+\.\d+, checking against the Evaluation Set \$\d+\.\d+$/,
      );
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

      // A range before the replies holds none of them.
      await dialog.getByLabel("From (UTC day)").fill(utcDay(-3));
      await dialog.getByLabel("To (UTC day)").fill(utcDay(-1));
      await expect(counted).toHaveText("0 pieces of evidence: 0 failed Live Verdicts, 0 thumbs-down, 0 rated 1 or 2, 0 failed Evaluation Cases");
      await dialog.getByLabel("To (UTC day)").fill(utcDay(0));
      await expect(counted).toContainText("2 pieces of evidence");
    });

    await test.step("[US16-11] a Suggestion run is refused while an Evaluation Run is in progress", async () => {
      const run = await call<{ id: string }>(page.request, "POST", `${agent.api}/evaluation/runs`, { sides: null });
      await dialog.getByRole("button", { name: "Start Suggestion run" }).click();
      await expect(dialog.getByText(EVALUATION_RUN_IN_PROGRESS)).toBeVisible({ timeout: 15_000 });
      await dialog.getByRole("button", { name: "Cancel" }).click();
      await expect
        .poll(async () => (await call<{ status: string }>(page.request, "GET", `${agent.api}/evaluation/runs/${run.id}`)).status, { timeout: 180_000 })
        .toBe("completed");
      await expect.poll(async () => (await evidence(page, agent.api)).evaluation_case, { timeout: 15_000 }).toBe(CASES);
    });

    await test.step("[US16-2] [US16-4] start a run of today alone; with enough evidence there is no warning", async () => {
      await page.getByRole("button", { name: "Suggest changes" }).click();
      await dialog.getByLabel("From (UTC day)").fill(utcDay(0));
      await expect(counted).toHaveText(`22 pieces of evidence: 2 failed Live Verdicts, 0 thumbs-down, 0 rated 1 or 2, ${String(CASES)} failed Evaluation Cases`, {
        timeout: 15_000,
      });
      await expect(dialog.getByText(/Fewer than 10 pieces of evidence/)).toHaveCount(0);
      await dialog.getByRole("button", { name: "Start Suggestion run" }).click();
      await expect(dialog).toHaveCount(0);
      await expect(page.getByRole("list", { name: "Suggestion runs" }).getByRole("listitem").first()).toContainText(`${utcDay(0)} to ${utcDay(0)} (UTC)`);
    });

    const listed = page.getByRole("list", { name: "Suggestion runs" }).getByRole("listitem").first();
    await test.step("[US16-9] its progress shows while it checks the Suggestion against the Evaluation Set", async () => {
      await expect(listed).toContainText("Checking", { timeout: 30_000 });
      await expect(page.getByRole("status").filter({ hasText: "Checking…" }).first()).toBeVisible();
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    const suggestionId = (await call<{ id: string }[]>(page.request, "GET", `${agent.api}/suggestions`))[0]?.id ?? "";

    await test.step("[US16-8] [US16-11] while it runs: no second Suggestion run, and Evaluate is refused", async () => {
      await expect(page.getByRole("button", { name: "Suggesting…" })).toBeDisabled();
      const second = await page.request.post(`${agent.api}/suggestions`, { data: {} });
      expect(second.status()).toBe(409);
      expect(await second.json()).toMatchObject({ detail: SUGGESTION_IN_PROGRESS, conflict: "suggestion_run_in_progress" });
      const evaluate = await page.request.post(`${agent.api}/evaluation/runs`, { data: { sides: null } });
      expect(evaluate.status()).toBe(409);
      expect(await evaluate.json()).toMatchObject({ detail: SUGGESTION_BLOCKS_EVALUATE, conflict: "suggestion_run_in_progress" });
      expect((await readSuggestion(page, agent.api, suggestionId)).status).toBe("checking");
    });

    await test.step("[US16-10] cancel the run: it stops and keeps what it spent", async () => {
      await page.getByRole("button", { name: "Cancel run" }).click();
      await expect(listed).toContainText("Cancelled", { timeout: 30_000 });
      await expect(page.getByText("This run was cancelled. It stopped before its next phase and keeps what it spent.")).toBeVisible();
      const cancelled = await readSuggestion(page, agent.api, suggestionId);
      expect(cancelled.status).toBe("cancelled");
      expect(Number(cancelled.cost.proposing_usd)).toBeGreaterThan(0);
      await expect(page.getByText(/^Proposing cost \$\d+\.\d+ \(estimated \$\d+\.\d+\)\./)).toBeVisible();
      await expect(page.getByRole("button", { name: "Suggest changes" })).toBeEnabled();
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });
  });
});
