import type { Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { openAgentView } from "../fixtures/agent";
import { rowAction } from "../fixtures/documents";
import { openSection } from "../fixtures/navigation";

// Each test signs up a fresh Owner, whose new Organisation answers with the demo provider's model
// (or the fake gateway's Claude): deterministic and offline. The demo model quotes the first
// Chunk it retrieves and cites it ("from <document> [C1]: ..."); told "Don't quote" in its system
// text, it gives that Chunk's first sentence alone, uncited. Its judge passes a Reference answer
// when the answer holds the Reference answer's quoted key phrase.
const DEMO_KEY = "demo-no-key-needed";
// The fake gateway's chat model answers "Fake reply from anthropic:claude-haiku-4-5." and fails
// with a provider error when the question asks it to.
const FAKE_CLAUDE_KEY = "sk-ant-e2e-test-only-not-a-real-key-p9q2";

type Api = { organisation: string; project: string };

/** A small Markdown Document, uploaded from memory so each run has its own content. */
function markdown(name: string, body: string) {
  return { name, mimeType: "text/markdown", buffer: Buffer.from(`# ${name}\n\n${body}\n`) };
}

/** Makes the Organisation answer with the demo model (or the fake Claude) by default. */
async function useModel(page: Page, model: "demo" | "fake-claude" = "demo"): Promise<string> {
  await page.goto("/");
  const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
  const organisation = `/api/organisations/${me.organisations[0]?.id ?? ""}`;
  const credential = await page.request.post(`${organisation}/credentials`, {
    data:
      model === "demo"
        ? { name: "Demo model", provider: "demo", api_key: DEMO_KEY }
        : { name: "Support Claude", provider: "anthropic", api_key: FAKE_CLAUDE_KEY },
  });
  expect(credential.status()).toBe(201);
  const { id } = (await credential.json()) as { id: string };
  const chosen = await page.request.put(`${organisation}/default-model`, {
    data: { credential_id: id, model: model === "demo" ? "demo-chat" : "claude-haiku-4-5" },
  });
  expect(chosen.status()).toBe(200);
  return organisation;
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
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
  }
  return { organisation, project: `${organisation}/projects/${project}` };
}

/** Creates an Agent through the API, optionally Published as v1, and returns its API path. */
async function newAgent(page: Page, api: Api, name: string, { publish = false } = {}): Promise<string> {
  const created = await page.request.post(`${api.project}/agents`, { data: { name } });
  expect(created.status()).toBe(201);
  const agent = `${api.project}/agents/${((await created.json()) as { id: string }).id}`;
  if (publish) expect((await page.request.post(`${agent}/versions`, { data: { note: "First release" } })).status()).toBe(201);
  return agent;
}

/** The Project's Documents by name, with their ids. */
async function documentIds(page: Page, api: Api): Promise<Record<string, string>> {
  const listed = (await (await page.request.get(`${api.project}/documents`)).json()) as { id: string; name: string }[];
  return Object.fromEntries(listed.map((document) => [document.name, document.id]));
}

type NewCase = {
  question: string;
  reference_answer?: string;
  expected_sources?: { document_id: string; passage: string }[];
  expect_fallback?: boolean;
};

/** Adds a case to the Agent's Evaluation Set through the API, and returns its id. */
async function addCase(page: Page, agent: string, evaluationCase: NewCase): Promise<string> {
  const created = await page.request.post(`${agent}/evaluation/cases`, { data: evaluationCase });
  expect(created.status()).toBe(201);
  return ((await created.json()) as { id: string }).id;
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

/** The Evaluation Set's table, and one case's row in it. */
function caseTable(page: Page) {
  return page.getByRole("table", { name: "Evaluation Cases" });
}

function caseRow(page: Page, question: string) {
  return caseTable(page).getByRole("row").filter({ has: page.getByRole("cell", { name: question, exact: true }) });
}

/** The Audit tab's events, filtered to one action. */
async function auditEvents(page: Page, action: string) {
  await page.goto("/");
  await openSection(page, "Organisation sections", "Settings");
  await openSection(page, "Organisation settings", "Audit");
  await page.getByLabel("Action").selectOption(action);
  return page.getByRole("table", { name: "Audit Events" }).getByRole("row").filter({ hasText: action });
}

test.describe("Evaluation Cases", () => {
  test("an Editor writes a case by hand: it needs an expectation, and takes Expected sources picked from passages of two Documents", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    test.slow();
    const organisation = await useModel(page);
    const stamp = String(Date.now());
    const leave = `Everyone gets 25 days of annual leave. Leave rolls over until March ${stamp}.`;
    const sick = `Sick leave is paid from the first day. A note is needed after five days ${stamp}.`;
    const api = await newProject(page, organisation, "Hand-written cases", [markdown("leave-policy.md", leave), markdown("sick-policy.md", sick)]);
    await newAgent(page, api, "Policy helper");
    await openAgent(page, "Hand-written cases", "Policy helper", "Evaluation");
    await expect(page.getByRole("heading", { name: "No Evaluation Cases yet" })).toBeVisible({ timeout: 15_000 });

    const question = "How much leave do I get, and what about when I'm ill?";
    await page.getByRole("button", { name: "New case" }).first().click();
    const editor = page.getByRole("dialog", { name: "New Evaluation Case" });
    await editor.getByLabel("Question").fill(question);

    await test.step("a case with no expectation is refused", async () => {
      await editor.getByRole("button", { name: "Save case" }).click();
      await expect(editor.getByText("Add an Expected source, write a Reference answer or tick Expect Fallback Text: a case needs at least one expectation.")).toBeVisible();
      await expect(editor.getByLabel("Reference answer")).toHaveAttribute("aria-invalid", "true");
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    await test.step("pick a passage of each Document as an Expected source", async () => {
      for (const [name, passage] of [
        ["leave-policy.md", "Everyone gets 25 days of annual leave."],
        ["sick-policy.md", "Sick leave is paid from the first day."],
      ] as const) {
        await editor.getByRole("button", { name: "Add Expected source" }).click();
        const picker = editor.getByRole("group", { name: "Pick a passage" });
        await picker.getByLabel("Document").selectOption({ label: name });
        await picker.getByRole("list", { name: "Chunks" }).getByRole("button", { name: "Use Chunk 1 as the passage" }).click();
        // The Chunk fills the passage; the Editor trims it to the sentence that matters.
        await expect(picker.getByRole("textbox", { name: "Passage" })).toHaveValue(new RegExp(passage.replace(/\./g, "\\.")));
        await picker.getByRole("textbox", { name: "Passage" }).fill(passage);
        await picker.getByRole("button", { name: "Add passage" }).click();
        await expect(editor.getByRole("list", { name: "Expected sources" }).getByRole("listitem").filter({ hasText: name })).toContainText(`“${passage}”`);
      }
      await expect(editor.getByRole("list", { name: "Expected sources" }).getByRole("listitem")).toHaveCount(2);
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    await test.step("save it: the set lists it with both Expected sources", async () => {
      await editor.getByRole("button", { name: "Save case" }).click();
      await expect(editor).toBeHidden({ timeout: 15_000 });
      const row = caseRow(page, question);
      await expect(row).toHaveCount(1, { timeout: 15_000 });
      const sources = row.getByRole("list", { name: "Expected sources" }).getByRole("listitem");
      await expect(sources).toHaveText(["leave-policy.md: “Everyone gets 25 days of annual leave.”", "sick-policy.md: “Sick leave is paid from the first day.”"]);
      await expect(row).toContainText("Not run yet");
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });
  });

  test("an Owner marks a case Expect Fallback Text, edits a case and deletes it, and the deletion is an Audit Event", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    const organisation = await useModel(page);
    const api = await newProject(page, organisation, "Case upkeep", []);
    const agent = await newAgent(page, api, "Upkeep helper");
    await addCase(page, agent, { question: "What is the parking policy?", reference_answer: 'Mentions "parking permits".' });
    await openAgent(page, "Case upkeep", "Upkeep helper", "Evaluation");
    await expect(caseRow(page, "What is the parking policy?")).toHaveCount(1, { timeout: 15_000 });

    await test.step("a case marked Expect Fallback Text can't also hold a Reference answer", async () => {
      await page.getByRole("button", { name: "New case" }).click();
      const editor = page.getByRole("dialog", { name: "New Evaluation Case" });
      await editor.getByLabel("Question").fill("What is the CEO's home address?");
      await editor.getByLabel("Reference answer").fill("Something made up.");
      await editor.getByRole("checkbox", { name: "Expect Fallback Text" }).check();
      await editor.getByRole("button", { name: "Save case" }).click();
      await expect(editor.getByText(/Expect Fallback Text can't be combined with a Reference answer/)).toBeVisible();
      await editor.getByLabel("Reference answer").fill("");
      await editor.getByRole("button", { name: "Save case" }).click();
      await expect(editor).toBeHidden({ timeout: 15_000 });
      await expect(caseRow(page, "What is the CEO's home address?")).toContainText("Expects the Fallback Text.", { timeout: 15_000 });
    });

    await test.step("edit a case: its question and Reference answer change in the set", async () => {
      await page.getByRole("button", { name: "More actions for What is the parking policy?" }).click();
      await page.getByRole("menu", { name: "Actions for What is the parking policy?" }).getByRole("menuitem", { name: "Edit" }).click();
      const editor = page.getByRole("dialog", { name: "Edit Evaluation Case" });
      await expect(editor.getByLabel("Question")).toHaveValue("What is the parking policy?");
      await expect(editor.getByLabel("Reference answer")).toHaveValue('Mentions "parking permits".');
      await editor.getByLabel("Question").fill("Where can staff park?");
      await editor.getByLabel("Reference answer").fill('Mentions "the staff car park".');
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      await editor.getByRole("button", { name: "Save case" }).click();
      await expect(editor).toBeHidden({ timeout: 15_000 });
      await expect(caseRow(page, "Where can staff park?")).toContainText('Mentions "the staff car park".', { timeout: 15_000 });
      await expect(caseRow(page, "What is the parking policy?")).toHaveCount(0);
      await expect(caseTable(page).getByRole("row")).toHaveCount(3);
    });

    await test.step("delete a case after confirming", async () => {
      await page.getByRole("button", { name: "More actions for Where can staff park?" }).click();
      await page.getByRole("menu", { name: "Actions for Where can staff park?" }).getByRole("menuitem", { name: "Delete" }).click();
      const confirm = page.getByRole("alertdialog", { name: "Delete this Evaluation Case?" });
      await expect(confirm).toContainText("“Where can staff park?” leaves the Evaluation Set.");
      await confirm.getByRole("button", { name: "Delete case" }).click();
      await expect(caseRow(page, "Where can staff park?")).toHaveCount(0, { timeout: 15_000 });
      await expect(caseTable(page).getByRole("row")).toHaveCount(2);
    });

    await test.step("the Audit tab records the deletion, and the case it deleted", async () => {
      const cases = (await (await page.request.get(`${agent}/evaluation/cases`)).json()) as { question: string }[];
      expect(cases.map((each) => each.question)).toEqual(["What is the CEO's home address?"]);
      const rows = await auditEvents(page, "agent.evaluation_case_deleted");
      await expect(rows).toHaveCount(1, { timeout: 15_000 });
      await expect(rows).toContainText('"source":"written"');
    });
  });

  test("an Editor is warned which Agents' cases use a Document before deleting it or uploading a new edition, then finds the Stale cases with the set's filters", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    test.slow();
    const organisation = await useModel(page);
    const stamp = String(Date.now());
    const api = await newProject(page, organisation, "Keeping cases valid", [
      markdown("leave-policy.md", `Everyone gets 25 days of annual leave. Leave rolls over until March ${stamp}.`),
      markdown("sick-policy.md", `Sick leave is paid from the first day. A note is needed after five days ${stamp}.`),
    ]);
    const ids = await documentIds(page, api);
    const leave = { document_id: ids["leave-policy.md"] ?? "", passage: "Everyone gets 25 days of annual leave." };
    const sick = { document_id: ids["sick-policy.md"] ?? "", passage: "Sick leave is paid from the first day." };
    const first = await newAgent(page, api, "Leave helper");
    const second = await newAgent(page, api, "Sickness helper");
    await addCase(page, first, { question: "How many days of leave do I get?", expected_sources: [leave] });
    await addCase(page, first, { question: "Is sick leave paid?", expected_sources: [sick] });
    await addCase(page, first, { question: "Who won the cup final?", expect_fallback: true });
    await addCase(page, first, { question: "Can I carry leave over?", reference_answer: 'Says "until March".' });
    await addCase(page, second, { question: "When do I need a sick note?", expected_sources: [sick] });
    await addCase(page, second, { question: "Is the first sick day paid?", expected_sources: [sick] });

    await test.step("deleting a Document warns which Agents' cases hold an Expected source in it", async () => {
      await page.goto("/");
      await openSection(page, "Organisation sections", "Projects");
      await page.getByRole("link", { name: "Keeping cases valid", exact: true }).click();
      await rowAction(page, "sick-policy.md", "Delete");
      const confirm = page.getByRole("alertdialog", { name: "Delete sick-policy.md?" });
      await expect(confirm).toContainText(
        "Expected sources in this Document are used by Leave helper (1 case) and Sickness helper (2 cases). Deleting it makes them Stale expectations, skipped by Runs until fixed.",
        { timeout: 15_000 },
      );
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      await confirm.getByRole("button", { name: "Delete sick-policy.md" }).click();
      await expect(page.getByText("Deleted sick-policy.md.")).toBeVisible({ timeout: 15_000 });
    });

    await test.step("uploading a new edition of a Document warns the same way before it replaces it", async () => {
      const chooser = page.waitForEvent("filechooser");
      await rowAction(page, "leave-policy.md", "New edition");
      await (await chooser).setFiles(markdown("leave-policy-2027.md", `Everyone gets 28 days of holiday from 2027. ${stamp}`));
      const confirm = page.getByRole("dialog", { name: "Upload a new edition of leave-policy.md?" });
      await expect(confirm).toContainText(
        "Expected sources in this Document are used by Leave helper (1 case). Any whose passage isn't in the new edition becomes a Stale expectation, skipped by Runs until fixed.",
        { timeout: 15_000 },
      );
      await expect(confirm).toContainText("leave-policy-2027.md replaces it once it is Ready.");
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      await confirm.getByRole("button", { name: "Upload new edition" }).click();
      const replaced = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /leave-policy-2027\.md/ });
      await expect(replaced).not.toContainText("New edition 2", { timeout: 60_000 });
      await expect(replaced.getByRole("cell", { name: "Ready" })).toBeVisible();
    });

    await test.step("the cases whose Expected source is gone are flagged with a Stale expectation", async () => {
      await openSection(page, "Project sections", "Agents");
      await page.getByRole("link", { name: "Leave helper", exact: true }).click();
      await openAgentView(page, "Evaluation");
      for (const question of ["How many days of leave do I get?", "Is sick leave paid?"]) {
        await expect(caseRow(page, question).getByText("Stale expectation")).toBeVisible({ timeout: 15_000 });
      }
      await expect(caseRow(page, "Is sick leave paid?").getByText("Stale expectation")).toHaveAttribute("title", "Its Document has been deleted.");
      await expect(caseRow(page, "How many days of leave do I get?").getByText("Stale expectation")).toHaveAttribute(
        "title",
        "No Chunk of its Document's current Edition holds this passage.",
      );
      for (const question of ["Who won the cup final?", "Can I carry leave over?"]) {
        await expect(caseRow(page, question).getByText("Stale expectation")).toHaveCount(0);
      }
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    await test.step("search and filter the set by Stale flag, expectation kind and latest result", async () => {
      const questions = caseTable(page).getByRole("row").locator("td:first-child");
      await page.getByLabel("Stale expectation", { exact: true }).selectOption({ label: "Stale expectation" });
      await expect(questions).toHaveText(["How many days of leave do I get?", "Is sick leave paid?"], { timeout: 15_000 });
      await page.getByLabel("Stale expectation", { exact: true }).selectOption({ label: "No Stale expectation" });
      await expect(questions).toHaveText(["Who won the cup final?", "Can I carry leave over?"], { timeout: 15_000 });
      await page.getByLabel("Expectation", { exact: true }).selectOption({ label: "Expect Fallback Text" });
      await expect(questions).toHaveText(["Who won the cup final?"], { timeout: 15_000 });
      await page.getByRole("button", { name: "Clear filters" }).click();
      await expect(questions).toHaveCount(4, { timeout: 15_000 });
      await page.getByLabel("Expectation", { exact: true }).selectOption({ label: "Reference answer" });
      await expect(questions).toHaveText(["Can I carry leave over?"], { timeout: 15_000 });
      await page.getByRole("button", { name: "Clear filters" }).click();
      await page.getByRole("searchbox", { name: "Search the questions" }).fill("SICK");
      await expect(questions).toHaveText(["Is sick leave paid?"], { timeout: 15_000 });
      await page.getByRole("button", { name: "Clear filters" }).click();
      await page.getByRole("radiogroup", { name: "Filter by latest result" }).getByRole("radio", { name: "Pass" }).click();
      await expect(page.getByRole("heading", { name: "No cases match" })).toBeVisible({ timeout: 15_000 });
      await page.getByRole("radiogroup", { name: "Filter by latest result" }).getByRole("radio", { name: "Not run" }).click();
      await expect(questions).toHaveCount(4, { timeout: 15_000 });
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });
  });

  test("an Editor copies chosen cases from another Agent of the Project, as independent copies", async ({ signedInPage: page, makeAxeBuilder }) => {
    const organisation = await useModel(page);
    const api = await newProject(page, organisation, "Shared cases", []);
    const source = await newAgent(page, api, "Billing helper");
    await newAgent(page, api, "Refunds helper");
    await addCase(page, source, { question: "How do I get a refund?", reference_answer: 'Says "within 30 days".' });
    await addCase(page, source, { question: "Where is my invoice?", reference_answer: 'Says "the Billing page".' });
    await openAgent(page, "Shared cases", "Refunds helper", "Evaluation");
    await expect(page.getByRole("heading", { name: "No Evaluation Cases yet" })).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Copy from another Agent" }).click();
    const dialog = page.getByRole("dialog", { name: "Copy from another Agent" });
    await dialog.getByRole("combobox", { name: /^Agent/ }).selectOption({ label: "Billing helper" });
    await expect(dialog.getByRole("checkbox", { name: "Select all (2)" })).toBeVisible({ timeout: 15_000 });
    await dialog.getByRole("checkbox", { name: "How do I get a refund?" }).check();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await dialog.getByRole("button", { name: "Copy 1 case" }).click();
    await expect(page.getByText("Copied 1 case.")).toBeVisible({ timeout: 15_000 });
    await expect(caseRow(page, "How do I get a refund?")).toContainText('Says "within 30 days".', { timeout: 15_000 });
    await expect(caseRow(page, "Where is my invoice?")).toHaveCount(0);

    // The copy is independent: editing it leaves the Billing helper's case as it was.
    await page.getByRole("button", { name: "More actions for How do I get a refund?" }).click();
    await page.getByRole("menu", { name: "Actions for How do I get a refund?" }).getByRole("menuitem", { name: "Edit" }).click();
    const editor = page.getByRole("dialog", { name: "Edit Evaluation Case" });
    await editor.getByLabel("Reference answer").fill('Says "within 14 days".');
    await editor.getByRole("button", { name: "Save case" }).click();
    await expect(caseRow(page, "How do I get a refund?")).toContainText('Says "within 14 days".', { timeout: 15_000 });
    const original = (await (await page.request.get(`${source}/evaluation/cases`)).json()) as { question: string; reference_answer: string }[];
    expect(original.map((each) => [each.question, each.reference_answer])).toEqual([
      ["How do I get a refund?", 'Says "within 30 days".'],
      ["Where is my invoice?", 'Says "the Billing page".'],
    ]);
  });

  test("an Editor evaluates the set and sees each case's latest result in it, then filters the set by that result", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    test.slow();
    const organisation = await useModel(page, "fake-claude");
    const api = await newProject(page, organisation, "Latest results", [markdown("models.md", `Our assistant runs on Claude. ${String(Date.now())}`)]);
    const agent = await newAgent(page, api, "Results helper");
    // The fake Claude answers "Fake reply from anthropic:claude-haiku-4-5. [C1]", citing the Chunk it found.
    await addCase(page, agent, { question: "Which model answers?", reference_answer: 'Names "claude-haiku-4-5".' });
    await addCase(page, agent, { question: "Which animal is striped?", reference_answer: 'Names "the zebra".' });
    await openAgent(page, "Latest results", "Results helper", "Evaluation");
    for (const question of ["Which model answers?", "Which animal is striped?"]) {
      await expect(caseRow(page, question)).toContainText("Not run yet", { timeout: 15_000 });
    }

    // Never Published: the Draft answers alone.
    await page.getByRole("button", { name: "Evaluate", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Evaluate" });
    await expect(dialog.getByRole("combobox", { name: /^First side/ })).toHaveValue("draft");
    await expect(dialog.getByRole("combobox", { name: /^Second side/ })).toHaveValue("");
    await dialog.getByRole("button", { name: "Start Run" }).click();
    await expect(dialog).toBeHidden({ timeout: 15_000 });

    const runs = page.getByRole("list", { name: "Evaluation Runs" });
    await expect(runs.getByRole("listitem").first()).toContainText("Completed", { timeout: 180_000 });
    // The set reads the latest results when the view opens again (it isn't re-read when the Run
    // ends: see the fixme below).
    await page.reload();
    const latest = (question: string) => caseRow(page, question).getByRole("cell").nth(2);
    // Every case is answered three times (the Organisation's Evaluation repeats).
    await expect(latest("Which model answers?")).toHaveText(/^Pass\s*3\/3$/, { timeout: 15_000 });
    await expect(latest("Which animal is striped?")).toHaveText(/^Fail\s*0\/3$/);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    const questions = caseTable(page).getByRole("row").locator("td:first-child");
    const results = page.getByRole("radiogroup", { name: "Filter by latest result" });
    await results.getByRole("radio", { name: "Pass" }).click();
    await expect(questions).toHaveText(["Which model answers?"], { timeout: 15_000 });
    await results.getByRole("radio", { name: "Fail" }).click();
    await expect(questions).toHaveText(["Which animal is striped?"], { timeout: 15_000 });
    // The demo stack's models are deterministic, so no case is Unsteady and none errors.
    for (const outcome of ["Unsteady", "Error", "Not run"]) {
      await results.getByRole("radio", { name: outcome }).click();
      await expect(page.getByRole("heading", { name: "No cases match" })).toBeVisible({ timeout: 15_000 });
    }
    await results.getByRole("radio", { name: "Any result" }).click();
    await expect(questions).toHaveCount(2, { timeout: 15_000 });
  });

  test("an Editor adds a Playground answer to the Evaluation Set: the question is copied in to edit, the cited passage is offered unticked, and the copy is an Audit Event", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    test.slow();
    const organisation = await useModel(page);
    const passage = `Everyone gets 25 days of annual leave. ${String(Date.now())}`;
    const api = await newProject(page, organisation, "Playground cases", [markdown("leave-policy.md", passage)]);
    const agent = await newAgent(page, api, "Leave helper");
    await openAgent(page, "Playground cases", "Leave helper", "Playground");

    const asked = "Hi, I'm Jo Bloggs from Payroll. How many days of annual leave do I get?";
    await page.getByLabel("Question", { exact: true }).fill(asked);
    await page.getByRole("button", { name: "Send" }).click();
    const answer = page.getByRole("list", { name: "Playground messages" }).getByRole("listitem", { name: "Leave helper" });
    await expect(answer).toContainText("from leave-policy.md [C1]", { timeout: 30_000 });
    await answer.getByRole("button", { name: "More actions for this answer" }).click();
    await page.getByRole("menu", { name: "Actions for this answer" }).getByRole("menuitem", { name: "Add to Evaluation Set" }).click();

    const editor = page.getByRole("dialog", { name: "Add to Evaluation Set" });
    await test.step("the question is copied in, and the cited passage is offered unticked", async () => {
      await expect(editor.getByLabel("Question")).toHaveValue(asked, { timeout: 15_000 });
      await expect(editor.getByText(/No link to the Conversation is kept/)).toBeVisible();
      const cited = editor.getByRole("group", { name: "Cited passages" });
      await expect(cited.getByRole("checkbox")).toHaveCount(1);
      await expect(cited.getByRole("listitem")).toContainText("leave-policy.md");
      await expect(cited.getByRole("listitem")).toContainText(passage);
      await expect(cited.getByRole("checkbox")).not.toBeChecked();
      // Unticked, the passage is no expectation yet.
      await editor.getByRole("button", { name: "Save case" }).click();
      await expect(editor.getByText(/a case needs at least one expectation/)).toBeVisible();
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    await test.step("the Editor rewrites the question without the personal details, keeps the cited passage and saves", async () => {
      await editor.getByLabel("Question").fill("How many days of annual leave do I get?");
      await editor.getByRole("group", { name: "Cited passages" }).getByRole("checkbox").check();
      await editor.getByRole("button", { name: "Save case" }).click();
      await expect(page.getByText("Added to the Evaluation Set.")).toBeVisible({ timeout: 15_000 });
    });

    await test.step("the set holds the edited question with the cited passage as its Expected source", async () => {
      await openAgentView(page, "Evaluation");
      const row = caseRow(page, "How many days of annual leave do I get?");
      await expect(row.getByRole("list", { name: "Expected sources" })).toContainText("leave-policy.md", { timeout: 15_000 });
      await expect(caseTable(page).getByText(/Jo Bloggs/)).toHaveCount(0);
      const cases = (await (await page.request.get(`${agent}/evaluation/cases`)).json()) as { id: string; source: string }[];
      expect(cases.map((each) => each.source)).toEqual(["from_message"]);
    });

    await test.step("the Audit tab records the case added from a Message", async () => {
      const rows = await auditEvents(page, "agent.evaluation_case_added_from_message");
      await expect(rows).toHaveCount(1, { timeout: 15_000 });
      const cases = (await (await page.request.get(`${agent}/evaluation/cases`)).json()) as { id: string }[];
      await expect(rows).toContainText(cases[0]?.id ?? "missing");
    });
  });

  test("an Editor publishing a Draft sees the hint to create a set, then notices for no Run, other Instructions and a changed Live Version, and Publishes anyway despite a Regression", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    test.setTimeout(420_000);
    const organisation = await useModel(page);
    const api = await newProject(page, organisation, "Publishing with evidence", [
      markdown("staff-handbook.md", `Everyone gets 25 days of annual leave. Leave rolls over until March. ${String(Date.now())}`),
    ]);
    expect((await page.request.put(`${api.project}/instructions`, { data: { markdown: "Be helpful." } })).ok()).toBe(true);
    expect((await page.request.post(`${api.project}/instructions/versions`, { data: { note: "First rules" } })).status()).toBe(201);
    const agent = await newAgent(page, api, "Handbook helper", { publish: true });
    const setPrompt = async (prompt: string) => {
      const current = (await (await page.request.get(agent)).json()) as { draft: { behaviour: Record<string, unknown> } };
      const draft = { ...current.draft, behaviour: { ...current.draft.behaviour, system_prompt: prompt } };
      expect((await page.request.put(`${agent}/draft`, { data: draft })).ok()).toBe(true);
    };
    await setPrompt("You answer staff questions about the handbook.");
    await openAgent(page, "Publishing with evidence", "Handbook helper");

    const publish = page.getByRole("form", { name: "Publish" });
    const evaluation = publish.getByRole("region", { name: "Evaluation" });
    const openPublish = async () => {
      await page.getByRole("banner").getByRole("button", { name: "Publish" }).click();
      await expect(evaluation).toBeVisible({ timeout: 15_000 });
    };
    const closePublish = async () => {
      await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();
      await expect(publish).toBeHidden();
    };

    await test.step("with no Evaluation Set, a one-line hint leads to the Evaluation tab", async () => {
      await openPublish();
      await expect(evaluation).toContainText(
        "No Evaluation Set yet. Add the questions that matter on the Evaluation tab to check a Draft before Publishing.",
        { timeout: 15_000 },
      );
      await expect(evaluation.getByRole("link", { name: "Evaluation tab" })).toHaveAttribute("href", /\/agents\/[0-9a-f-]+\/evaluation$/);
      await expect(evaluation.getByRole("button", { name: "Evaluate" })).toHaveCount(0);
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      await closePublish();
    });

    // The demo model quotes the handbook by name; its judge passes when the answer holds the name.
    await addCase(page, agent, { question: "How many days of annual leave do I get?", reference_answer: 'Quotes the "staff-handbook.md".' });

    await test.step("with a set but no Run, a notice says the Draft hasn't been evaluated against the Live Version", async () => {
      await page.reload();
      await openPublish();
      await expect(evaluation).toContainText("The Draft hasn't been evaluated against the Live Version (v1) yet.", { timeout: 15_000 });
      await evaluation.getByRole("button", { name: "Evaluate" }).click();
      await expect(evaluation).toContainText("No Regressions against the Live Version: Evaluation score 100% against 100%.", { timeout: 180_000 });
      await closePublish();
    });

    await test.step("after new Project Instructions, a notice says the Run used other Instructions than those being published", async () => {
      expect((await page.request.put(`${api.project}/instructions`, { data: { markdown: "Be helpful and kind." } })).ok()).toBe(true);
      expect((await page.request.post(`${api.project}/instructions/versions`, { data: { note: "Kinder rules" } })).status()).toBe(201);
      await page.reload();
      await openPublish();
      await expect(evaluation).toContainText("Evaluated with Instructions v1, publishing with v2.", { timeout: 15_000 });
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      // Publishing with the Instructions the Run used, the notice goes.
      await publish.getByLabel("Project Instructions").selectOption({ label: "v1 · First rules" });
      await expect(evaluation).toContainText("No Regressions against the Live Version", { timeout: 15_000 });
      await expect(evaluation).not.toContainText("Evaluated with");
      await closePublish();
    });

    await test.step("a Draft with a Regression can still be Published", async () => {
      await setPrompt("Answer staff questions in one short sentence. Don't quote the handbook.");
      await page.reload();
      await openPublish();
      await expect(evaluation.getByText(/The Draft has changed since it was evaluated/)).toBeVisible({ timeout: 15_000 });
      await evaluation.getByRole("button", { name: "Evaluate" }).click();
      await expect(evaluation.getByRole("list", { name: "Regressions" }).getByRole("listitem")).toHaveCount(1, { timeout: 180_000 });
      await expect(evaluation).toContainText("This Draft has 1 Regression: a case that passes on the Live Version fails on the Draft.");
      await expect(evaluation).toContainText("You can still Publish.");
      await publish.getByLabel("Note").fill("Shorter answers, knowingly");
      await publish.getByRole("button", { name: "Publish" }).click();
      await expect(publish.getByRole("status").getByText(/It is now Live\./)).toBeVisible({ timeout: 15_000 });
      await closePublish();
      const versions = (await (await page.request.get(`${agent}/versions`)).json()) as { live_version_id: string; versions: { id: string; number: number }[] };
      expect(versions.versions.find((version) => version.id === versions.live_version_id)?.number).toBe(2);
    });

    await test.step("once another Version is Live, a notice says the Run compared the Draft with the earlier one", async () => {
      await setPrompt("Answer staff questions in one sentence. Don't quote the handbook.");
      await page.reload();
      await openPublish();
      await expect(evaluation).toContainText(
        "The Live Version has changed since the Draft was evaluated: it was compared with v1, and v2 is Live now.",
        { timeout: 15_000 },
      );
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
      await closePublish();
    });
  });

  test("an Editor rolling out new Project Instructions evaluates the rollout, sees each Agent's Regressions or that it isn't evaluated, and rolls out anyway", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    test.setTimeout(420_000);
    const organisation = await useModel(page);
    const api = await newProject(page, organisation, "Rollout with evidence", [
      markdown("staff-handbook.md", `Everyone gets 25 days of annual leave. Leave rolls over until March. ${String(Date.now())}`),
    ]);
    expect((await page.request.put(`${api.project}/instructions`, { data: { markdown: "Be helpful." } })).ok()).toBe(true);
    expect((await page.request.post(`${api.project}/instructions/versions`, { data: { note: "First rules" } })).status()).toBe(201);
    const quoting = await newAgent(page, api, "Quoting helper", { publish: true });
    await newAgent(page, api, "Unevaluated helper", { publish: true });
    // The demo model quotes the handbook by name, unless its system text says not to quote.
    await addCase(page, quoting, { question: "How many days of annual leave do I get?", reference_answer: 'Quotes the "staff-handbook.md".' });

    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    await page.getByRole("link", { name: "Rollout with evidence", exact: true }).click();
    await openSection(page, "Project sections", "Instructions");
    await page.getByRole("button", { name: "Markdown" }).click();
    await page.getByRole("textbox", { name: "Project Instructions (Markdown)" }).fill("Be helpful. Don't quote the handbook.");
    const publishForm = page.getByRole("form", { name: "Publish Instructions" });
    await publishForm.getByRole("textbox", { name: "Note" }).fill("No quoting");
    await publishForm.getByRole("button", { name: "Publish Instructions" }).click();
    const dialog = page.getByRole("dialog", { name: "Roll out Instructions v2" });
    const row = (name: string) => dialog.getByRole("list", { name: "Agents" }).getByRole("listitem").filter({ hasText: name });

    await test.step("the rollout dialog offers Evaluate rollout for the selected Agents", async () => {
      await expect(dialog.getByRole("checkbox", { name: "Quoting helper" })).toBeChecked({ timeout: 15_000 });
      await expect(dialog.getByRole("checkbox", { name: "Unevaluated helper" })).toBeChecked();
      await expect(dialog).toContainText(
        "Evaluate rollout runs each selected Agent's Evaluation Set with its Live configuration and Instructions v2, against its Live Version as it is.",
      );
      await expect(row("Unevaluated helper")).toContainText("Not evaluated: no Evaluation Set");
      await expect(row("Quoting helper")).toContainText("Not evaluated");
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    await test.step("evaluating lists the Regressions of the Agent with a set, and marks the other not evaluated", async () => {
      await dialog.getByRole("button", { name: "Evaluate rollout" }).click();
      await expect(row("Quoting helper")).toContainText("1 Regression", { timeout: 180_000 });
      await expect(row("Quoting helper").getByRole("list", { name: "Regressions" }).getByRole("listitem")).toContainText(
        "How many days of annual leave do I get?",
      );
      await expect(row("Unevaluated helper")).toContainText("Not evaluated: no Evaluation Set");
      await expect(dialog).toContainText(
        "Quoting helper has Regressions with Instructions v2: cases that pass on the Live Version fail with the new Instructions. You can still publish.",
      );
      expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    });

    await test.step("the Regressions block nothing: both Agents stay selected and the rollout publishes", async () => {
      await expect(dialog.getByRole("checkbox", { name: "Quoting helper" })).toBeChecked();
      await dialog.getByRole("button", { name: "Publish to 2 Agents" }).click();
      const results = dialog.getByRole("list", { name: "Results" });
      await expect(results).toContainText("Quoting helper — Done: Published v2 with Instructions v2. It is now Live.", { timeout: 15_000 });
      await expect(results).toContainText("Unevaluated helper — Done: Published v2 with Instructions v2. It is now Live.");
      await dialog.getByRole("button", { name: "Done" }).click();
    });
  });

  test("the set shows each case's latest result as soon as the Run it watches ends, without reopening the view", async ({ signedInPage: page }) => {
    test.fixme(
      true,
      "14.13: the Evaluation Set's cases are not read again when a Run finishes (useEvaluationRuns polls only the Runs), so the Latest result column keeps saying \"Not run yet\" until the view is reopened. See findings-P7.md.",
    );
    test.slow();
    const organisation = await useModel(page, "fake-claude");
    const api = await newProject(page, organisation, "Live latest results", [markdown("models.md", `Our assistant runs on Claude. ${String(Date.now())}`)]);
    const agent = await newAgent(page, api, "Live results helper");
    await addCase(page, agent, { question: "Which model answers?", reference_answer: 'Names "claude-haiku-4-5".' });
    await openAgent(page, "Live latest results", "Live results helper", "Evaluation");
    await expect(caseRow(page, "Which model answers?")).toContainText("Not run yet", { timeout: 15_000 });
    await page.getByRole("button", { name: "Evaluate", exact: true }).click();
    await page.getByRole("dialog", { name: "Evaluate" }).getByRole("button", { name: "Start Run" }).click();
    await expect(page.getByRole("list", { name: "Evaluation Runs" }).getByRole("listitem").first()).toContainText("Completed", { timeout: 180_000 });
    await expect(caseRow(page, "Which model answers?").getByRole("cell").nth(2)).toHaveText(/^Pass\s*3\/3$/, { timeout: 15_000 });
  });
});
