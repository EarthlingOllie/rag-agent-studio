import type { Browser, Locator, Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { agentAction, openAgentView } from "../fixtures/agent";
import { type MemberCredentials, newMember } from "../fixtures/auth";
import { openSection } from "../fixtures/navigation";
import { APPEARANCES } from "../fixtures/pages";

// Each test signs up a fresh Owner, whose new Organisation answers with the demo provider's model:
// deterministic, offline and free. It quotes the first Chunk it retrieves and cites it
// ("from <document> [C1]: ..."); told "Don't quote" in its system text (the Agent's prompt or the
// Project Instructions), it gives that Chunk's first sentence alone, uncited. The judge (the demo
// model, or the fake gateway's Claude when that is the Evaluation Model) passes a Reference answer
// when the answer holds the Reference answer's quoted key phrase, and grounding when it cites.
// The fake Claude has a price, so a Run it judges has a judging Cost; the demo model costs nothing.
const DEMO_KEY = "demo-no-key-needed";
const FAKE_CLAUDE_KEY = "sk-ant-e2e-test-only-not-a-real-key-p8e7";
const DONT_QUOTE = "Answer in one short sentence. Don't quote the handbook.";
const RUN_IN_PROGRESS = "This Agent already has an Evaluation Run in progress. Wait for it to finish, or cancel it.";

type Api = { organisation: string; project: string };
type RunOut = {
  id: string;
  status: string;
  progress: { done: number; total: number };
  cost: { answers_usd: string; judging_usd: string; total_usd: string; estimated_usd: string | null };
};

/** A small Markdown Document, uploaded from memory so each run has its own content. */
function markdown(name: string, body: string) {
  return { name, mimeType: "text/markdown", buffer: Buffer.from(`# ${name}\n\n${body}\n`) };
}

/** Makes the signed-in Owner's Organisation answer with the demo model by default; returns its API path. */
async function useDemoModel(page: Page): Promise<string> {
  await page.goto("/");
  const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
  const organisation = `/api/organisations/${me.organisations[0]?.id ?? ""}`;
  const credential = await page.request.post(`${organisation}/credentials`, { data: { name: "Demo model", provider: "demo", api_key: DEMO_KEY } });
  expect(credential.status()).toBe(201);
  const { id } = (await credential.json()) as { id: string };
  expect((await page.request.put(`${organisation}/default-model`, { data: { credential_id: id, model: "demo-chat" } })).status()).toBe(200);
  return organisation;
}

/** Adds the fake gateway's Claude as a Provider Credential named "Support Claude"; returns its id. */
async function addFakeClaude(page: Page, organisation: string): Promise<string> {
  const credential = await page.request.post(`${organisation}/credentials`, {
    data: { name: "Support Claude", provider: "anthropic", api_key: FAKE_CLAUDE_KEY },
  });
  expect(credential.status()).toBe(201);
  return ((await credential.json()) as { id: string }).id;
}

/** Makes the fake Claude (Claude Haiku 4.5) the Evaluation Model, through the API. */
async function judgeWithFakeClaude(page: Page, organisation: string) {
  const id = await addFakeClaude(page, organisation);
  expect((await page.request.put(`${organisation}/evaluation-model`, { data: { credential_id: id, model: "claude-haiku-4-5" } })).status()).toBe(200);
}

async function setRepeats(page: Page, organisation: string, repeats: number) {
  expect((await page.request.put(`${organisation}/evaluation-repeats`, { data: { repeats } })).status()).toBe(200);
}

/** Creates a Project in the Studio and uploads `documents` to it, waiting until each is Ready. */
async function newProject(page: Page, organisation: string, name: string, documents: ReturnType<typeof markdown>[]): Promise<Api> {
  await openSection(page, "Organisation sections", "Projects");
  await page.getByRole("button", { name: "New Project" }).click();
  const form = page.getByRole("form", { name: "New Project" });
  await form.getByLabel("Name").fill(name);
  await form.getByRole("button", { name: "Create Project" }).click();
  await expect(page.getByText(/No Documents yet/)).toBeVisible({ timeout: 15_000 });
  const project = /\/projects\/([0-9a-f-]+)/.exec(page.url())?.[1] ?? "";
  for (const document of documents) {
    await page.getByLabel("Upload", { exact: true }).setInputFiles(document);
    const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: new RegExp(document.name.replace(/\./g, "\\.")) });
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 90_000 });
  }
  return { organisation, project: `${organisation}/projects/${project}` };
}

/** Saves the Project Instructions Draft, and optionally publishes it as the next Instructions Version. */
async function saveInstructions(page: Page, api: Api, text: string, { publish = false } = {}) {
  expect((await page.request.put(`${api.project}/instructions`, { data: { markdown: text } })).status()).toBe(200);
  if (publish) expect((await page.request.post(`${api.project}/instructions/versions`, { data: { note: "Instructions" } })).status()).toBe(201);
}

/** Creates an Agent through the API and returns its API path. */
async function newAgent(page: Page, api: Api, name: string): Promise<string> {
  const created = await page.request.post(`${api.project}/agents`, { data: { name } });
  expect(created.status()).toBe(201);
  return `${api.project}/agents/${((await created.json()) as { id: string }).id}`;
}

/** Changes the Agent's Draft system prompt. */
async function setPrompt(page: Page, agent: string, prompt: string) {
  const { draft } = (await (await page.request.get(agent)).json()) as { draft: { behaviour: Record<string, unknown> } };
  const changed = { ...draft, behaviour: { ...draft.behaviour, system_prompt: prompt } };
  expect((await page.request.put(`${agent}/draft`, { data: changed })).ok()).toBe(true);
}

async function publish(page: Page, agent: string, note: string) {
  expect((await page.request.post(`${agent}/versions`, { data: { note } })).status()).toBe(201);
}

type NewCase = { question: string; reference_answer?: string; expected_sources?: { document_id: string; passage: string }[] };

async function addCase(page: Page, agent: string, evaluationCase: NewCase) {
  const created = await page.request.post(`${agent}/evaluation/cases`, { data: evaluationCase });
  expect(created.status(), await created.text()).toBe(201);
}

async function startRun(page: Page, agent: string, data: Record<string, unknown> = {}): Promise<string> {
  const started = await page.request.post(`${agent}/evaluation/runs`, { data });
  expect(started.status(), await started.text()).toBe(202);
  return ((await started.json()) as { id: string }).id;
}

async function readRun(page: Page, agent: string, id: string): Promise<RunOut> {
  return (await (await page.request.get(`${agent}/evaluation/runs/${id}`)).json()) as RunOut;
}

/** Waits until the Run has finished, and returns it. */
async function finished(page: Page, agent: string, id: string): Promise<RunOut> {
  await expect.poll(async () => (await readRun(page, agent, id)).status, { timeout: 180_000, intervals: [250, 500, 1000] }).toMatch(/completed|failed|cancelled/);
  return readRun(page, agent, id);
}

/** Opens an Agent of a Project from the sidebar, then one of its views. */
async function openAgent(page: Page, projectName: string, agentName: string, view?: Parameters<typeof openAgentView>[1]) {
  await page.goto("/");
  await openSection(page, "Organisation sections", "Projects");
  await page.getByRole("link", { name: projectName, exact: true }).click();
  await openSection(page, "Project sections", "Agents");
  await page.getByRole("link", { name: agentName, exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: agentName })).toBeVisible({ timeout: 15_000 });
  if (view !== undefined) await openAgentView(page, view);
}

/** A labelled select in `scope`, found by the text its label starts with (the label wraps the select and its options). */
function field(scope: Locator, label: string) {
  return scope.locator("label", { hasText: new RegExp(`^${label}`) }).locator("select");
}

/** Switches the Appearance and waits for the colour transitions to settle, so axe reads the final colours. */
async function useAppearance(page: Page, appearance: (typeof APPEARANCES)[number]) {
  await page.emulateMedia({ colorScheme: appearance });
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"));
}

/** The Evaluation Set's Evaluate button (not the Publish dialog's). */
function evaluateButton(page: Page) {
  return page.getByRole("region", { name: "Evaluation Set" }).getByRole("button", { name: /^Evaluat/ });
}

function runDetail(page: Page) {
  return page.getByRole("region", { name: /^Run of / });
}

function runCase(page: Page, question: string) {
  return runDetail(page).getByRole("list", { name: "Cases" }).getByRole("listitem").filter({ has: page.getByRole("heading", { level: 4, name: question }) });
}

/** The Audit tab's events, filtered to one action. */
async function auditEvents(page: Page, action: string) {
  await page.goto("/");
  await openSection(page, "Organisation sections", "Settings");
  await openSection(page, "Organisation settings", "Audit");
  await page.getByLabel("Action").selectOption(action);
  return page.getByRole("table", { name: "Audit Events" }).getByRole("row").filter({ hasText: action });
}

async function openModels(page: Page) {
  await page.goto("/");
  await openSection(page, "Organisation sections", "Settings");
  await openSection(page, "Organisation settings", "Models");
  await expect(page.getByRole("heading", { name: "Evaluation", exact: true })).toBeVisible();
}

/** The Owner invites a new person as an Editor with a copied link; they join in their own browser. */
async function inviteNewEditor(owner: Page, browser: Browser, person: MemberCredentials): Promise<Page> {
  await owner.goto("/");
  await openSection(owner, "Organisation sections", "Settings");
  await openSection(owner, "Organisation settings", "Members");
  await owner.getByRole("button", { name: "Invite someone" }).click();
  const form = owner.getByRole("form", { name: "Invite someone" });
  await form.getByLabel("Email", { exact: true }).fill(person.email);
  await form.getByLabel("Role").selectOption("Editor");
  await form.getByLabel("Email the invite link").uncheck();
  await form.getByRole("button", { name: "Invite" }).click();
  const link = new URL(await owner.getByLabel(`Invite link for ${person.email}`).inputValue());
  const page = await (await browser.newContext()).newPage();
  await page.goto(link.pathname + link.search);
  await page.getByLabel("Your name").fill(person.name);
  await page.getByLabel("Password").fill(person.password);
  await page.getByRole("button", { name: "Create account and join" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
  return page;
}

test.describe("Evaluation Runs", () => {
  test("an Editor evaluates a never-published Agent's Draft alone from the Evaluation view: the estimated Cost shows first, progress shows while it runs, a second Run is refused, and Cancel stops it", async ({
    signedInPage: page,
  }) => {
    test.setTimeout(300_000);
    const stamp = String(Date.now());
    const organisation = await useDemoModel(page);
    await judgeWithFakeClaude(page, organisation);
    await setRepeats(page, organisation, 9);
    const api = await newProject(page, organisation, `Baseline ${stamp}`, [markdown(`leave-${stamp}.md`, "Everyone gets 25 days of annual leave.")]);
    const agent = await newAgent(page, api, "Baseline helper");
    // 40 cases × 9 repeats: long enough to watch it run, and to cancel it.
    for (let index = 1; index <= 40; index++) {
      await addCase(page, agent, { question: `How much annual leave do I get? (${String(index)})`, reference_answer: `Quotes "leave-${stamp}.md".` });
    }
    await openAgent(page, `Baseline ${stamp}`, "Baseline helper", "Evaluation");
    await expect(page.getByText("No Runs yet. Evaluate to answer the set with the Draft.")).toBeVisible({ timeout: 15_000 });

    await test.step("the Evaluate dialog offers the Draft alone, with the estimated Cost before starting", async () => {
      await evaluateButton(page).click();
      const dialog = page.getByRole("dialog", { name: "Evaluate" });
      const first = field(dialog, "First side");
      const second = field(dialog, "Second side");
      await expect(first.locator("option:checked")).toHaveText("Draft");
      await expect(first.getByRole("option")).toHaveText(["Draft"]);
      await expect(second.locator("option:checked")).toHaveText("None: the first side runs alone");
      const estimate = dialog.getByRole("status", { name: "Estimated Cost" });
      await expect(estimate).toHaveText(/^About \$\S+: answers \$0\.00, judging \$\S+$/, { timeout: 15_000 });
      expect(await estimate.textContent()).not.toMatch(/judging \$0\.00/);
      await expect(dialog.getByText(/^40 cases × 1 side × 9 repeats, at each side's mean Cost per reply/)).toBeVisible();
      await dialog.getByRole("button", { name: "Start Run" }).click();
      await expect(dialog).toHaveCount(0);
    });

    const runs = (await (await page.request.get(`${agent}/evaluation/runs`)).json()) as RunOut[];
    expect(runs).toHaveLength(1);
    const runId = runs[0]?.id ?? "";

    await test.step("while it runs, its progress moves and Evaluate is disabled; a second Run is refused", async () => {
      const progress = runDetail(page).getByRole("meter", { name: "Answers given" });
      await expect(progress).toHaveAttribute("aria-valuemax", "360", { timeout: 15_000 });
      await expect.poll(async () => Number(await progress.getAttribute("aria-valuenow")), { timeout: 120_000 }).toBeGreaterThan(0);
      const seen = Number(await progress.getAttribute("aria-valuenow"));
      await expect.poll(async () => Number(await progress.getAttribute("aria-valuenow")), { timeout: 60_000 }).toBeGreaterThan(seen);
      await expect(progress).toHaveAttribute("aria-valuetext", /^\d+ of 360 answers$/);
      await expect(runDetail(page).getByText("Running")).toBeVisible();
      await expect(evaluateButton(page)).toHaveText("Evaluating…");
      await expect(evaluateButton(page)).toBeDisabled();
      const again = await page.request.post(`${agent}/evaluation/runs`, { data: {} });
      expect(again.status()).toBe(409);
      expect(await again.text()).toContain(RUN_IN_PROGRESS);
    });

    await test.step("Cancel stops the Run, keeping what it answered, and Evaluate comes back", async () => {
      await runDetail(page).getByRole("button", { name: "Cancel Run" }).click();
      await expect(runDetail(page).getByText("This Run was cancelled. The answers it gave before stopping are kept.")).toBeVisible({ timeout: 15_000 });
      await expect(runDetail(page).getByText("Cancelled", { exact: true })).toBeVisible();
      await expect(runDetail(page).getByRole("button", { name: "Cancel Run" })).toHaveCount(0);
      await expect(evaluateButton(page)).toHaveText("Evaluate");
      await expect(evaluateButton(page)).toBeEnabled();
      const cancelled = await readRun(page, agent, runId);
      expect(cancelled.status).toBe("cancelled");
      expect(cancelled.progress.done).toBeGreaterThan(0);
      expect(cancelled.progress.done).toBeLessThan(360);
      // It stopped: a moment later it has given no more answers (at most the one in flight).
      await page.reload();
      await expect(runDetail(page).getByText("Cancelled", { exact: true })).toBeVisible({ timeout: 15_000 });
      expect((await readRun(page, agent, runId)).progress.done).toBeLessThanOrEqual(cancelled.progress.done + 1);
      // The Draft alone answered: one side, named by its Draft revision.
      await expect(runDetail(page).getByText(/^Cancelled · Draft revision \d+ · no Project Instructions · demo demo-chat · judged by anthropic claude-haiku-4-5 · 9 repeats$/)).toBeVisible();
    });
  });

  test("an Editor picks two Versions as the sides and sees each side's Evaluation score, the improvement, each case's repeat count and every answer's Trace, with the Run's Cost split and its details kept in the history", async ({
    signedInPage: page,
  }) => {
    test.setTimeout(300_000);
    const stamp = String(Date.now());
    const organisation = await useDemoModel(page);
    await judgeWithFakeClaude(page, organisation);
    const document = `handbook-${stamp}.md`;
    const projectName = `Two Versions ${stamp}`;
    const api = await newProject(page, organisation, projectName, [markdown(document, "Everyone gets 25 days of annual leave. Leave rolls over.")]);
    await saveInstructions(page, api, "Be friendly.", { publish: true });
    const agent = await newAgent(page, api, "Leave helper");
    const question = `How much annual leave do I get, ${stamp}?`;
    await addCase(page, agent, { question, reference_answer: `Quotes "${document}" and cites it.` });
    // v1 quotes the handbook; v2, told not to quote, gives one uncited sentence.
    await publish(page, agent, "Quotes the handbook");
    await setPrompt(page, agent, DONT_QUOTE);
    await publish(page, agent, "One short sentence");
    await openAgent(page, projectName, "Leave helper", "Evaluation");

    await test.step("choose Version 2 (Live) against Version 1, not the default Draft", async () => {
      await evaluateButton(page).click();
      const dialog = page.getByRole("dialog", { name: "Evaluate" });
      const first = field(dialog, "First side");
      const second = field(dialog, "Second side");
      await expect(first.locator("option:checked")).toHaveText("Version 2 (Live)", { timeout: 15_000 });
      await expect(second.locator("option:checked")).toHaveText("Draft");
      await expect(first.getByRole("option")).toHaveText(["Draft", "Version 2 (Live)", "Version 1"]);
      // The same side twice is refused.
      await second.selectOption({ label: "Version 2 (Live)" });
      await expect(dialog.getByText("Choose two different sides.")).toBeVisible();
      await expect(dialog.getByRole("button", { name: "Start Run" })).toBeDisabled();
      await second.selectOption({ label: "Version 1" });
      // No Draft side: no choice of the Draft's Instructions.
      await expect(dialog.getByLabel("Draft's Instructions")).toHaveCount(0);
      await expect(dialog.getByRole("status", { name: "Estimated Cost" })).toHaveText(/^About \$/, { timeout: 15_000 });
      await expect(dialog.getByText(/^1 case × 2 sides × 3 repeats/)).toBeVisible();
      await dialog.getByRole("button", { name: "Start Run" }).click();
      await expect(dialog).toHaveCount(0);
    });

    const runs = (await (await page.request.get(`${agent}/evaluation/runs`)).json()) as RunOut[];
    expect(runs).toHaveLength(1);
    const run = await finished(page, agent, runs[0]?.id ?? "");
    expect(run.status).toBe("completed");

    await test.step("each side's Evaluation score, and the case that fails on Version 2 and passes on Version 1 as an improvement", async () => {
      const detail = runDetail(page);
      await expect(detail.getByRole("group", { name: "Version 2", exact: true })).toContainText("First side: Version 2", { timeout: 30_000 });
      await expect(detail.getByRole("group", { name: "Version 2", exact: true })).toContainText("Evaluation score: 0%");
      await expect(detail.getByRole("group", { name: "Version 2", exact: true })).toContainText("0 passed, 1 failed");
      await expect(detail.getByRole("group", { name: "Version 1", exact: true })).toContainText("Second side: Version 1");
      await expect(detail.getByRole("group", { name: "Version 1", exact: true })).toContainText("Evaluation score: 100%");
      await expect(detail.getByRole("group", { name: "Version 1", exact: true })).toContainText("1 passed, 0 failed");
      await expect(detail.getByText(/^0 Regressions and 1 improvement:/)).toBeVisible();
      const result = runCase(page, question).getByRole("group", { name: "Result" });
      await expect(result.getByText("Improvement", { exact: true })).toBeVisible();
      await expect(result.getByText("Regression", { exact: true })).toHaveCount(0);
      // Each side's repeat count; steady results aren't marked Unsteady.
      await expect(result).toContainText("Version 2:Fail0/3 repeats passed");
      await expect(result).toContainText("Version 1:Pass3/3 repeats passed");
      await expect(result.getByText("Unsteady")).toHaveCount(0);
    });

    await test.step("each answer with its Verdicts and its Trace: Searches, retrieved Chunks, Citations and Guardrail outcomes", async () => {
      const failing = runCase(page, question).getByRole("group", { name: "Answers of Version 2" });
      await expect(failing.getByText(/^Repeat \d: /)).toHaveCount(3);
      await expect(failing.getByRole("list", { name: "Verdicts" }).first()).toContainText(`Reference answer: Fail. Fake judge: the answer lacks “${document}”.`);
      await expect(failing.getByRole("list", { name: "Verdicts" }).first()).toContainText("Grounding: Fail. Fake judge: the answer cites nothing to support it.");
      const passing = runCase(page, question).getByRole("group", { name: "Answers of Version 1" });
      await expect(passing.getByText(`from ${document} [C1]`).first()).toBeVisible();
      const trace = passing.getByRole("group", { name: "Trace" }).first();
      await trace.locator("summary").click();
      await expect(trace.getByText("Answered by")).toBeVisible();
      await expect(trace.getByRole("definition").first()).toHaveText("Agent Version v1");
      await expect(trace.getByText("Pinned by Agent Version v1")).toBeVisible();
      await expect(trace.getByRole("heading", { name: "Guardrails" })).toBeVisible();
      await expect(trace.getByText("No Guardrail stepped in.")).toBeVisible();
      const chunks = trace.getByRole("table", { name: /^(Chunks found by Search 1|Retrieved Chunks)$/ });
      await expect(chunks.getByRole("row").filter({ hasText: document })).toContainText("Cited");
      // Version 2's answers retrieved the same Chunk but cited nothing.
      const uncited = failing.getByRole("group", { name: "Trace" }).first();
      await uncited.locator("summary").click();
      await expect(uncited.getByRole("table", { name: /^(Chunks found by Search 1|Retrieved Chunks)$/ }).getByRole("row").filter({ hasText: document })).toContainText("Given, not cited");
    });

    await test.step("the Run's Cost split into answers and judging, and its details in the history", async () => {
      const detail = runDetail(page);
      await expect(detail.getByText(/^Completed · Version 2 · Instructions v1 · demo demo-chat against Version 1 · Instructions v1 · demo demo-chat · judged by anthropic claude-haiku-4-5 · 3 repeats$/)).toBeVisible();
      await expect(detail.getByText(/^Cost \$\S+: answers \$0\.00, judging \$\S+ \(estimated \$\S+\)$/)).toBeVisible();
      expect(Number(run.cost.answers_usd)).toBe(0);
      expect(Number(run.cost.judging_usd)).toBeGreaterThan(0);
      expect(Number(run.cost.total_usd)).toBe(Number(run.cost.judging_usd));
    });

    await test.step("a later Run of the Draft keeps the first in the history, with its sides, Instructions, Evaluation Model, repeats and Cost", async () => {
      await evaluateButton(page).click();
      const dialog = page.getByRole("dialog", { name: "Evaluate" });
      await expect(dialog.getByRole("status", { name: "Estimated Cost" })).toHaveText(/^About \$/, { timeout: 15_000 });
      await dialog.getByRole("button", { name: "Start Run" }).click();
      const list = page.getByRole("list", { name: "Evaluation Runs" });
      await expect(list.getByRole("listitem")).toHaveCount(2, { timeout: 15_000 });
      await expect.poll(async () => ((await (await page.request.get(`${agent}/evaluation/runs`)).json()) as RunOut[]).every((each) => each.status === "completed"), { timeout: 120_000 }).toBe(true);
      await page.reload();
      const older = list.getByRole("listitem").nth(1);
      await expect(older).toContainText("Version 2: 0% · Version 1: 100%", { timeout: 15_000 });
      await expect(older).toContainText("6 / 6 answers");
      await expect(older).toContainText(/Cost \$\S+/);
      await expect(list.getByRole("listitem").first()).toContainText("Version 2: 0% · Draft revision");
      await older.getByRole("button", { name: /^Run of / }).click();
      await expect(older.getByRole("button", { name: /^Run of / })).toHaveAttribute("aria-current", "true");
      await expect(runDetail(page).getByText(/^Completed · Version 2 · Instructions v1 · demo demo-chat against Version 1 · Instructions v1 · demo demo-chat · judged by anthropic claude-haiku-4-5 · 3 repeats$/)).toBeVisible();
      await expect(runDetail(page).getByText(/^Cost \$\S+: answers \$0\.00, judging \$\S+/)).toBeVisible();
    });

    await test.step("Organisation cost shows the Runs' Cost in the Evaluation column", async () => {
      const all = (await (await page.request.get(`${agent}/evaluation/runs`)).json()) as RunOut[];
      const spent = all.reduce((sum, each) => sum + Number(each.cost.total_usd), 0);
      expect(spent).toBeGreaterThan(0);
      await page.goto("/");
      await openSection(page, "Organisation sections", "Cost");
      const byProject = page.getByRole("table", { name: "Cost by Project" });
      await expect(byProject.getByRole("columnheader")).toHaveText(["Project", "Visitors", "Playground", "Evaluation", "Total"]);
      const row = byProject.getByRole("row", { name: new RegExp(`^${projectName}`) });
      await expect(row).toBeVisible();
      // The Project names the row; its cells are Visitors, Playground, Evaluation and Total.
      const [visitors, playground, evaluation, total] = await row.getByRole("cell").allTextContents();
      expect([visitors, playground]).toEqual(["$0.00", "$0.00"]);
      expect(evaluation).not.toBe("$0.00");
      // The Evaluation amount is what the Runs cost (shown to two significant digits below a cent), and nothing else was spent.
      const amount = Number((evaluation ?? "").replace(/[$,]/g, ""));
      expect(Math.abs(amount - spent) / spent).toBeLessThan(0.05);
      expect(total).toBe(evaluation);
    });
  });

  test("an Editor chooses the Instructions the Draft side answers with: the Current Instructions Version by default, or the Instructions Draft", async ({
    signedInPage: page,
  }) => {
    test.setTimeout(300_000);
    const stamp = String(Date.now());
    const organisation = await useDemoModel(page);
    const document = `policy-${stamp}.md`;
    const projectName = `Instructions choice ${stamp}`;
    const api = await newProject(page, organisation, projectName, [markdown(document, "Everyone gets 25 days of annual leave. Leave rolls over.")]);
    await saveInstructions(page, api, "Be friendly.", { publish: true });
    // The Instructions Draft, not yet published, tells the model not to quote.
    await saveInstructions(page, api, `Be friendly. ${DONT_QUOTE}`);
    const agent = await newAgent(page, api, "Instructions helper");
    const question = `How much leave do I get, ${stamp}?`;
    await addCase(page, agent, { question, reference_answer: `Quotes "${document}".` });
    await openAgent(page, projectName, "Instructions helper", "Evaluation");

    await test.step("by default the Draft answers with the Current Instructions Version, and quotes", async () => {
      await evaluateButton(page).click();
      const dialog = page.getByRole("dialog", { name: "Evaluate" });
      const instructions = dialog.getByLabel("Draft's Instructions");
      await expect(instructions.locator("option:checked")).toHaveText("Current Instructions Version (v1)", { timeout: 15_000 });
      await expect(instructions.getByRole("option")).toHaveText(["Current Instructions Version (v1)", "Instructions Draft", "Instructions v1"]);
      await dialog.getByRole("button", { name: "Start Run" }).click();
      await expect(runDetail(page).getByText(/^Completed · Draft revision \d+ · Instructions v1 · demo demo-chat · judged by demo demo-chat · 3 repeats$/)).toBeVisible({ timeout: 120_000 });
      await expect(runDetail(page).getByText("Evaluation score: 100%")).toBeVisible();
      await expect(runCase(page, question).getByText(`from ${document} [C1]`).first()).toBeVisible();
    });

    await test.step("with the Instructions Draft chosen, the Draft answers as those Instructions say", async () => {
      await evaluateButton(page).click();
      const dialog = page.getByRole("dialog", { name: "Evaluate" });
      await dialog.getByLabel("Draft's Instructions").selectOption({ label: "Instructions Draft" });
      await expect(dialog.getByRole("status", { name: "Estimated Cost" })).toHaveText(/^About \$/, { timeout: 15_000 });
      await dialog.getByRole("button", { name: "Start Run" }).click();
      await expect(runDetail(page).getByText(/^Completed · Draft revision \d+ · Instructions Draft · demo demo-chat · judged by demo demo-chat · 3 repeats$/)).toBeVisible({ timeout: 120_000 });
      await expect(runDetail(page).getByText("Evaluation score: 0%")).toBeVisible();
      await expect(runCase(page, question).getByText(`from ${document} [C1]`)).toHaveCount(0);
      await expect(runCase(page, question).getByRole("list", { name: "Verdicts" }).first()).toContainText(`Reference answer: Fail. Fake judge: the answer lacks “${document}”.`);
    });
  });

  test("an Editor sees a case whose repeats disagreed marked Unsteady with its repeat count, and a Stale expectation skipped, neither pass nor fail", async ({
    signedInPage: page,
  }) => {
    test.setTimeout(300_000);
    const stamp = String(Date.now());
    const organisation = await useDemoModel(page);
    await setRepeats(page, organisation, 9);
    const leave = `leave-${stamp}.md`;
    const other = `canteen-${stamp}.md`;
    const passage = "Everyone gets 25 days of annual leave.";
    const projectName = `Unsteady ${stamp}`;
    const api = await newProject(page, organisation, projectName, [
      markdown(leave, `${passage} Leave rolls over.`),
      markdown(other, "The canteen opens at noon and serves soup."),
    ]);
    const agent = await newAgent(page, api, "Steady helper");
    const documents = (await (await page.request.get(`${api.project}/documents`)).json()) as { id: string; name: string }[];
    const leaveId = documents.find((each) => each.name === leave)?.id ?? "";
    const unsteadyQuestion = `How much annual leave do I get, ${stamp}?`;
    const staleQuestion = `Where is the annual leave rule, ${stamp}?`;
    await addCase(page, agent, { question: unsteadyQuestion, reference_answer: `Quotes "${leave}".` });
    await addCase(page, agent, { question: staleQuestion, expected_sources: [{ document_id: leaveId, passage }] });

    await test.step("the Knowledge Base changes while the first case's repeats are answering", async () => {
      const runId = await startRun(page, agent);
      // Once a couple of repeats have passed, the leave Document goes: the later repeats can't quote it.
      await expect.poll(async () => (await readRun(page, agent, runId)).progress.done, { timeout: 120_000, intervals: [25] }).toBeGreaterThanOrEqual(2);
      expect((await page.request.delete(`${api.project}/documents/${leaveId}`)).status()).toBe(204);
      expect((await finished(page, agent, runId)).status).toBe("completed");
    });

    await test.step("the case is marked Unsteady, with how many of its 9 repeats passed", async () => {
      await openAgent(page, projectName, "Steady helper", "Evaluation");
      const result = runCase(page, unsteadyQuestion).getByRole("group", { name: "Result" });
      await expect(result.getByText("Unsteady", { exact: true })).toBeVisible({ timeout: 15_000 });
      await expect(result).toContainText(/^(Fail ?Unsteady ?[1-4]|Pass ?Unsteady ?[5-8])\/9 repeats passed$/);
      // The Evaluation Set's latest result says so too.
      const row = page.getByRole("table", { name: "Evaluation Cases" }).getByRole("row").filter({ hasText: unsteadyQuestion });
      await expect(row.getByText("Unsteady", { exact: true })).toBeVisible();
      await expect(row).toContainText(/[1-8]\/9/);
      await page.getByRole("radiogroup", { name: "Filter by latest result" }).getByRole("radio", { name: "Unsteady" }).click();
      await expect(page.getByRole("table", { name: "Evaluation Cases" }).getByRole("row").filter({ hasText: stamp })).toHaveText([new RegExp(unsteadyQuestion.replace(/[?]/g, "\\?"))]);
    });

    await test.step("in the next Run the Expected source's Document is gone: that expectation is skipped, neither pass nor fail", async () => {
      await evaluateButton(page).click();
      await page.getByRole("dialog", { name: "Evaluate" }).getByRole("button", { name: "Start Run" }).click();
      await expect(runDetail(page).getByText(/^Completed · /)).toBeVisible({ timeout: 120_000 });
      const stale = runCase(page, staleQuestion);
      await expect(stale.getByText(/An Expected source's Document or passage is gone, so it was skipped: neither pass nor fail\./)).toBeVisible();
      const verdicts = stale.getByRole("list", { name: "Verdicts" }).first();
      await expect(verdicts).toContainText("Expected source: Stale, skipped.");
      await expect(verdicts).not.toContainText("Expected source: Pass");
      await expect(verdicts).not.toContainText("Expected source: Fail");
    });
  });

  test("an Owner chooses the Evaluation Model and the Evaluation repeats in Models settings, both audited, and the Evaluation Model's credential can't be deleted while chosen", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    const organisation = await useDemoModel(page);
    await addFakeClaude(page, organisation);
    await openModels(page);
    const section = page.getByRole("region", { name: "Evaluation" });

    await test.step("the Default Model judges and each side answers 3 times, by default", async () => {
      await expect(section.getByText("Evaluation Model: the Default Model")).toBeVisible();
      await expect(section.getByText("Each side of a Run answers every case 3 times.")).toBeVisible();
      const repeats = section.getByRole("radiogroup", { name: "Evaluation repeats" });
      await expect(repeats.getByRole("radio")).toHaveText(["1", "3", "5", "7", "9"]);
      await expect(repeats.getByRole("radio", { name: "3" })).toHaveAttribute("aria-checked", "true");
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    await test.step("choose Claude Haiku 4.5 as the Evaluation Model", async () => {
      const form = section.getByRole("form", { name: "Choose the Evaluation Model" });
      await expect(form.getByLabel("Judge with").getByRole("option")).toHaveText(["Use the Default Model", "Demo model (Demo: canned answers, not a real model)", "Support Claude (Anthropic)"]);
      await form.getByLabel("Judge with").selectOption({ label: "Support Claude (Anthropic)" });
      await field(form, "Model").selectOption({ label: "Claude Haiku 4.5" });
      await form.getByRole("button", { name: "Save Evaluation Model" }).click();
      await expect(page.getByText("Evaluation Runs are now judged by Claude Haiku 4.5.")).toBeVisible();
      await expect(section.getByText("Evaluation Model: Claude Haiku 4.5, using Support Claude (Anthropic)")).toBeVisible();
    });

    await test.step("set the repeats to 7, then 1", async () => {
      const repeats = section.getByRole("radiogroup", { name: "Evaluation repeats" });
      await repeats.getByRole("radio", { name: "7" }).click();
      await expect(page.getByText("Each side of a Run now answers every case 7 times.")).toBeVisible();
      await expect(repeats.getByRole("radio", { name: "7" })).toHaveAttribute("aria-checked", "true");
      await repeats.getByRole("radio", { name: "1" }).click();
      await expect(section.getByText("Each side of a Run answers every case 1 times.")).toBeVisible();
      await page.reload();
      await expect(page.getByRole("region", { name: "Evaluation" }).getByRole("radiogroup", { name: "Evaluation repeats" }).getByRole("radio", { name: "1" })).toHaveAttribute("aria-checked", "true");
      await expect(page.getByRole("region", { name: "Evaluation" }).getByText("Evaluation Model: Claude Haiku 4.5, using Support Claude (Anthropic)")).toBeVisible();
      // Only 1, 3, 5, 7 or 9.
      expect((await page.request.put(`${organisation}/evaluation-repeats`, { data: { repeats: 4 } })).status()).toBe(422);
      const saved = (await (await page.request.get(`${organisation}/evaluation-settings`)).json()) as { repeats: number; evaluation_model: { model: string } };
      expect(saved).toMatchObject({ repeats: 1, evaluation_model: { model: "claude-haiku-4-5" } });
    });

    await test.step("the Evaluation Model's credential can't be deleted while it is chosen", async () => {
      await openSection(page, "Organisation settings", "Credentials");
      await page.getByRole("button", { name: "Delete: Support Claude" }).click();
      await page.getByRole("button", { name: "Yes, delete Support Claude" }).click();
      await expect(page.getByText("Evaluation Model (Claude Haiku 4.5)")).toBeVisible();
      await expect(page.getByRole("table", { name: "Provider Credentials" }).getByRole("row", { name: /Support Claude/ })).toBeVisible();
    });

    await test.step("both changes are Audit Events", async () => {
      const model = await auditEvents(page, "organisation.evaluation_model_changed");
      await expect(model).toHaveCount(1);
      await expect(model).toContainText("claude-haiku-4-5");
      const repeats = await auditEvents(page, "organisation.evaluation_repeats_changed");
      await expect(repeats).toHaveCount(2);
    });
  });

  test("an Editor sees the Evaluation Model and repeats but can't change them, in the Studio or through the API", async ({ signedInPage: page, browser }) => {
    const organisation = await useDemoModel(page);
    const credential = await addFakeClaude(page, organisation);
    const editor = await inviteNewEditor(page, browser, newMember({ name: "Eval Editor" }));
    await openModels(editor);
    const section = editor.getByRole("region", { name: "Evaluation" });
    await expect(section.getByText("Evaluation Model: the Default Model")).toBeVisible();
    await expect(section.getByText("Each side of a Run answers every case 3 times.")).toBeVisible();
    await expect(section.getByText("Only Owners can change the Evaluation Model and Evaluation repeats.")).toBeVisible();
    await expect(section.getByRole("form", { name: "Choose the Evaluation Model" })).toHaveCount(0);
    await expect(section.getByRole("radiogroup", { name: "Evaluation repeats" })).toHaveCount(0);
    expect((await editor.request.put(`${organisation}/evaluation-model`, { data: { credential_id: credential, model: "claude-haiku-4-5" } })).status()).toBe(403);
    expect((await editor.request.put(`${organisation}/evaluation-repeats`, { data: { repeats: 9 } })).status()).toBe(403);
    const unchanged = (await (await page.request.get(`${organisation}/evaluation-settings`)).json()) as unknown;
    expect(unchanged).toEqual({ evaluation_model: null, repeats: 3 });
    await editor.context().close();
  });

  test("a Member archives an Agent: its Evaluation Set and Runs stay, read only, no new Run starts, and Restore brings the set back", async ({
    signedInPage: page,
  }) => {
    test.setTimeout(300_000);
    const stamp = String(Date.now());
    const organisation = await useDemoModel(page);
    await setRepeats(page, organisation, 1);
    const document = `archive-${stamp}.md`;
    const projectName = `Archive ${stamp}`;
    const api = await newProject(page, organisation, projectName, [markdown(document, "Everyone gets 25 days of annual leave.")]);
    const agent = await newAgent(page, api, "Archived helper");
    const question = `How much leave do I get, ${stamp}?`;
    await addCase(page, agent, { question, reference_answer: `Quotes "${document}".` });
    expect((await finished(page, agent, await startRun(page, agent))).status).toBe("completed");
    await openAgent(page, projectName, "Archived helper", "Evaluation");

    await agentAction(page, "Archive");
    await page.getByRole("alertdialog", { name: "Archive Archived helper?" }).getByRole("button", { name: "Yes, archive Archived helper" }).click();
    await expect(page.getByText("This Agent is archived: its Evaluation Set and Runs are read only, and it starts no Run.")).toBeVisible({ timeout: 15_000 });
    const set = page.getByRole("region", { name: "Evaluation Set" });
    await expect(set.getByRole("table", { name: "Evaluation Cases" }).getByRole("row").filter({ hasText: question })).toHaveCount(1);
    await expect(set.getByRole("button", { name: /^(Evaluate|New case|Copy from another Agent)$/ })).toHaveCount(0);
    await expect(set.getByRole("button", { name: `More actions for ${question}` })).toHaveCount(0);
    await expect(page.getByRole("list", { name: "Evaluation Runs" }).getByRole("listitem")).toHaveCount(1);
    await expect(runDetail(page).getByText("Evaluation score: 100%")).toBeVisible();
    const refused = await page.request.post(`${agent}/evaluation/runs`, { data: {} });
    expect(refused.status()).toBe(409);
    expect((await (await page.request.get(`${agent}/evaluation/runs`)).json()) as unknown[]).toHaveLength(1);

    await page.getByRole("status", { name: "Archived" }).getByRole("button", { name: "Restore Archived helper" }).click();
    await expect(page.getByText("This Agent is archived: its Evaluation Set and Runs are read only, and it starts no Run.")).toHaveCount(0, { timeout: 15_000 });
    await expect(set.getByRole("table", { name: "Evaluation Cases" }).getByRole("row").filter({ hasText: question })).toHaveCount(1);
    await expect(evaluateButton(page)).toBeEnabled();
    await expect(page.getByRole("list", { name: "Evaluation Runs" }).getByRole("listitem")).toHaveCount(1);
  });

  test("a keyboard user writes a case in the case editor and starts a Run from the Evaluation view, and the editor, the Evaluate dialog and the Run detail pass axe in light and dark", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    test.setTimeout(300_000);
    const stamp = String(Date.now());
    const organisation = await useDemoModel(page);
    await setRepeats(page, organisation, 1);
    const handbook = `keyboard-${stamp}.md`;
    const projectName = `Keyboard ${stamp}`;
    await newProject(page, organisation, projectName, [markdown(handbook, "Everyone gets 25 days of annual leave.")]);
    const api = { organisation, project: `${organisation}/projects/${/\/projects\/([0-9a-f-]+)/.exec(page.url())?.[1] ?? ""}` };
    await newAgent(page, api, "Keyboard helper");
    await openAgent(page, projectName, "Keyboard helper", "Evaluation");
    const question = `How much leave do I get, ${stamp}?`;

    await test.step("the case editor opens, fills and saves from the keyboard, and passes axe", async () => {
      const newCase = page.getByRole("button", { name: "New case" }).first();
      await newCase.focus();
      await page.keyboard.press("Enter");
      const editor = page.getByRole("dialog", { name: "New Evaluation Case" });
      await expect(editor).toBeVisible();
      for (const appearance of APPEARANCES) {
        await useAppearance(page, appearance);
        expect((await makeAxeBuilder().include('[role="dialog"]').analyze()).violations, appearance).toEqual([]);
      }
      // Focus starts inside the dialog; Escape closes it and focus goes back to New case.
      await expect.poll(() => editor.evaluate((dialog) => dialog.contains(document.activeElement))).toBe(true);
      await page.keyboard.press("Escape");
      await expect(editor).toHaveCount(0);
      await expect(newCase).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(editor).toBeVisible();
      await editor.getByLabel("Question").focus();
      await page.keyboard.type(question);
      // Tab through to the Reference answer, typing it there.
      const reference = editor.getByLabel("Reference answer");
      for (let step = 0; step < 6 && !(await reference.evaluate((element) => element === document.activeElement)); step++) await page.keyboard.press("Tab");
      await expect(reference).toBeFocused();
      await page.keyboard.type(`Quotes "${handbook}".`);
      const save = editor.getByRole("button", { name: "Save case" });
      for (let step = 0; step < 6 && !(await save.evaluate((element) => element === document.activeElement)); step++) await page.keyboard.press("Tab");
      await expect(save).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(editor).toHaveCount(0, { timeout: 15_000 });
      await expect(page.getByRole("table", { name: "Evaluation Cases" }).getByRole("row").filter({ hasText: question })).toHaveCount(1);
    });

    await test.step("the Evaluate dialog is announced, passes axe and starts a Run from the keyboard", async () => {
      await useAppearance(page, "light");
      await evaluateButton(page).focus();
      await page.keyboard.press("Enter");
      const dialog = page.getByRole("dialog", { name: "Evaluate" });
      await expect(dialog).toBeVisible();
      await expect(dialog.getByRole("status", { name: "Estimated Cost" })).toHaveText(/^About \$/, { timeout: 15_000 });
      for (const appearance of APPEARANCES) {
        await useAppearance(page, appearance);
        expect((await makeAxeBuilder().include('[role="dialog"]').analyze()).violations, appearance).toEqual([]);
      }
      const start = dialog.getByRole("button", { name: "Start Run" });
      await start.focus();
      await page.keyboard.press("Enter");
      await expect(dialog).toHaveCount(0);
    });

    await test.step("the Run detail passes axe, and a Trace opens from the keyboard", async () => {
      await expect(runDetail(page).getByText("Evaluation score: 100%")).toBeVisible({ timeout: 120_000 });
      const trace = runCase(page, question).getByRole("group", { name: "Trace" }).first();
      await trace.locator("summary").focus();
      await page.keyboard.press("Enter");
      await expect(trace.getByText("Answered by")).toBeVisible();
      for (const appearance of APPEARANCES) {
        await useAppearance(page, appearance);
        expect((await makeAxeBuilder().analyze()).violations, appearance).toEqual([]);
      }
    });
  });
});
