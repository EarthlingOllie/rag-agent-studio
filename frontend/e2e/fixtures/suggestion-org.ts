import type { APIRequestContext, Browser, Page } from "@playwright/test";

import { expect } from "./index";
import { openAgentView } from "./agent";

/**
 * A fresh Organisation set up to make Suggestions, for the end-to-end tests of spec 16 that change
 * state (applying, deleting, archiving), so the seeded demo stays as it is.
 *
 * Its Default Model is the demo provider's model: deterministic, offline and free. It quotes the
 * first Chunk it retrieves and cites it; told "Don't quote" in its system prompt (as `CURT_PROMPT`
 * does), it gives that Chunk's first sentence alone and cites nothing. Its Evaluation Model is the fake gateway's Claude, which has
 * a price, so Live Verdicts, checks and proposing each have a Cost. The judge fails grounding for a
 * reply that cites nothing, and asked to propose a Suggestion the fake proposer adds
 * `CITE_LINE` to the system prompt when evidence failed grounding (unless the prompt already
 * has it), and names a Knowledge Base gap for each failed Live Verdict whose reply cited no Chunk.
 */
export const CITE_LINE = "Always cite the passage you used.";
export const GAP_TOPIC = "Fake proposer: a question no Chunk covered";
const DEMO_KEY = "demo-no-key-needed";
const FAKE_CLAUDE_KEY = "sk-ant-e2e-test-only-not-a-real-key-d16a";
export const EVALUATION_MODEL = "claude-haiku-4-5";
/** A system prompt the demo model answers with an uncited sentence, so its Live Verdicts fail grounding. */
export const CURT_PROMPT = "Answer staff questions in one short sentence. Don't quote the handbook.";
/** What the Project's one Document says. */
export const HANDBOOK = "Everyone gets 25 days of annual leave a year. Unused leave can be carried over until March.";
const BOOT = /<script id="widget-boot" type="application\/json">(.*?)<\/script>/;

export interface Draft {
  behaviour: Record<string, unknown>;
  retrieval: Record<string, unknown>;
  [section: string]: unknown;
}

export interface AgentOut {
  id: string;
  public_id: string;
  name: string;
  draft: Draft;
  draft_revision: number;
  live_version: { id: string; number: number } | null;
}

export interface SuggestionOut {
  id: string;
  status: string;
  outcome: string | null;
  range_start: string;
  range_end: string;
  base_version_number: number;
  evidence_total: number;
  stale: boolean;
  applied_by: { id: string; name: string } | null;
  applied_at: string | null;
  explanation: string | null;
  model_provider: string;
  model_name: string;
  cost: { estimated_proposing_usd: string | null; estimated_checking_usd: string | null; proposing_usd: string | null; checking_usd: string | null };
  check: { state: string; evaluation_run_id: string | null; live_score: number | null; suggestion_score: number | null; regressions: unknown[] } | null;
  changes: { id: string; path: string; base_value: string | number; suggested_value: string | number; explanation: string; evidence_ids: string[] }[];
  gaps: { id: string; topic: string; explanation: string; evidence_ids: string[] }[];
  evidence: {
    id: string;
    label: string;
    kind: string;
    kinds: string[];
    occurred_at: string;
    conversation_id: string | null;
    message_id: string | null;
    live_verdict: "pass" | "fail" | null;
    text_purged: boolean;
    evaluation_run_id: string | null;
    run_case_id: string | null;
    case_deleted: boolean;
  }[];
}

export interface SuggestionOrg {
  organisationId: string;
  /** `/api/organisations/<id>` */
  organisation: string;
  projectId: string;
  /** `/api/organisations/<id>/projects/<id>` */
  project: string;
  projectName: string;
  /** The fake Claude Provider Credential, the Evaluation Model's. */
  claudeCredentialId: string;
}

/** The Studio route of the Project. */
export function projectPath(org: SuggestionOrg): string {
  return org.project.replace(/^\/api/, "");
}

export interface PublishedAgent extends AgentOut {
  /** `/api/organisations/<id>/projects/<id>/agents/<id>` */
  api: string;
  /** The Studio route of the Agent. */
  path: string;
}

/** Answers `method url` with its JSON body, failing the test on any status but 2xx. */
export async function json<T>(request: APIRequestContext, method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE", url: string, data?: unknown): Promise<T> {
  const response = await request.fetch(url, { method, data });
  expect(response.ok(), `${method} ${url}: ${await response.text()}`).toBe(true);
  const body = await response.text();
  return (body === "" ? undefined : JSON.parse(body)) as T;
}

/**
 * Sets up the signed-in Owner's new Organisation to make Suggestions: the demo model answers, the
 * fake Claude judges and proposes, an Evaluation budget lets Live Verdicts be sampled, and a
 * Project holds the Agents, its one Document (`HANDBOOK`) uploaded in the Studio and Ready.
 */
export async function suggestionOrg(page: Page, projectName = "Suggestions HR"): Promise<SuggestionOrg> {
  await page.goto("/");
  const me = await json<{ organisations: { id: string }[] }>(page.request, "GET", "/api/auth/me");
  const organisationId = me.organisations[0]?.id ?? "";
  const organisation = `/api/organisations/${organisationId}`;
  const demo = await json<{ id: string }>(page.request, "POST", `${organisation}/credentials`, { name: "Demo model", provider: "demo", api_key: DEMO_KEY });
  await json(page.request, "PUT", `${organisation}/default-model`, { credential_id: demo.id, model: "demo-chat" });
  const claude = await json<{ id: string }>(page.request, "POST", `${organisation}/credentials`, {
    name: "Support Claude",
    provider: "anthropic",
    api_key: FAKE_CLAUDE_KEY,
  });
  await json(page.request, "PUT", `${organisation}/evaluation-model`, { credential_id: claude.id, model: EVALUATION_MODEL });
  await json(page.request, "PUT", `${organisation}/evaluation-budget`, { evaluation_budget_usd: "50.00" });
  const project = await json<{ id: string }>(page.request, "POST", `${organisation}/projects`, { name: projectName });
  const org = {
    organisationId,
    organisation,
    projectId: project.id,
    project: `${organisation}/projects/${project.id}`,
    projectName,
    claudeCredentialId: claude.id,
  };
  await page.goto(projectPath(org));
  await expect(page.getByText(/No Documents yet/)).toBeVisible({ timeout: 15_000 });
  const name = `handbook-${organisationId.slice(0, 8)}.md`;
  await page.getByLabel("Upload", { exact: true }).setInputFiles({ name, mimeType: "text/markdown", buffer: Buffer.from(`# Leave\n\n${HANDBOOK}\n`) });
  const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: new RegExp(name.replace(/\./g, "\\.")) });
  await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 90_000 });
  return org;
}

/** Reads the Agent. */
export async function readAgent(page: Page, agent: PublishedAgent): Promise<AgentOut> {
  return json<AgentOut>(page.request, "GET", agent.api);
}

/** Saves the Agent's Draft with `change` applied to it, on its current revision. */
export async function editDraft(request: APIRequestContext, agentApi: string, change: (draft: Draft) => Draft): Promise<AgentOut> {
  const current = await json<AgentOut>(request, "GET", agentApi);
  return json<AgentOut>(request, "PUT", `${agentApi}/draft`, change(current.draft));
}

/**
 * Creates an Agent with `systemPrompt` (and any other `edit` to its Draft), publishes it as
 * Version 1, and has every Visitor reply judged (a Live sample rate of 100%).
 */
export async function publishedAgent(
  page: Page,
  org: SuggestionOrg,
  name: string,
  { systemPrompt, edit = (draft) => draft }: { systemPrompt: string; edit?: (draft: Draft) => Draft },
): Promise<PublishedAgent> {
  const created = await json<AgentOut>(page.request, "POST", `${org.project}/agents`, { name });
  const api = `${org.project}/agents/${created.id}`;
  await editDraft(page.request, api, (draft) => edit({ ...draft, behaviour: { ...draft.behaviour, system_prompt: systemPrompt } }));
  await json(page.request, "POST", `${api}/versions`, { note: "First Version" });
  await json(page.request, "PATCH", `${api}/operational-settings`, { live_sample_rate: 100 });
  const agent = await json<AgentOut>(page.request, "GET", api);
  return { ...agent, api, path: api.replace(/^\/api/, "") };
}

/** A Visitor asks the Agent `question` in the widget, in a browser of their own. */
export async function askAsVisitor(browser: Browser, publicId: string, question: string): Promise<void> {
  const visitor = await browser.newContext();
  try {
    const shell = await (await visitor.request.get(`/widget/a/${publicId}`)).text();
    const boot = JSON.parse(BOOT.exec(shell)?.[1] ?? "{}") as { bootstrap_token: string };
    const started = await visitor.request.post(`/api/widget/agents/${publicId}/conversations`, { data: { bootstrap_token: boot.bootstrap_token } });
    expect(started.status()).toBe(201);
    const { conversation_token: token } = (await started.json()) as { conversation_token: string };
    const asked = await visitor.request.post(`/api/widget/agents/${publicId}/messages`, {
      data: { content: question },
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(asked.status()).toBe(200);
    expect(await asked.text()).toContain("event: done");
  } finally {
    await visitor.close();
  }
}

/** Waits until the worker has judged the Agent's Visitor replies: `failed` failed Live Verdicts are evidence. */
export async function waitForFailedVerdicts(page: Page, agent: PublishedAgent, failed: number): Promise<void> {
  await expect
    .poll(async () => (await json<{ live_verdict: number }>(page.request, "GET", `${agent.api}/suggestions/evidence`)).live_verdict, {
      timeout: 90_000,
      intervals: [500, 1000, 2000],
    })
    .toBe(failed);
}

/** Adds a case to the Agent's Evaluation Set; returns its id. */
export async function addCase(page: Page, agent: PublishedAgent, question: string, referenceAnswer: string): Promise<string> {
  const created = await json<{ id: string }>(page.request, "POST", `${agent.api}/evaluation/cases`, {
    question,
    reference_answer: referenceAnswer,
    expected_sources: [],
    expect_fallback: false,
    source: "written",
  });
  return created.id;
}

/** Starts a Suggestion run of the default range through the API; returns its id. */
export async function startSuggestion(request: APIRequestContext, agent: PublishedAgent): Promise<string> {
  const response = await request.post(`${agent.api}/suggestions`, { data: {} });
  expect(response.status(), await response.text()).toBe(202);
  return ((await response.json()) as { id: string }).id;
}

/** Reads a Suggestion. */
export async function readSuggestion(request: APIRequestContext, agent: PublishedAgent, id: string): Promise<SuggestionOut> {
  return json<SuggestionOut>(request, "GET", `${agent.api}/suggestions/${id}`);
}

/** Waits until the Suggestion run, and its check if it has one, have finished; returns it. */
export async function finishedSuggestion(request: APIRequestContext, agent: PublishedAgent, id: string): Promise<SuggestionOut> {
  await expect
    .poll(
      async () => {
        const read = await readSuggestion(request, agent, id);
        return ["completed", "failed", "cancelled"].includes(read.status) && read.check?.state !== "running";
      },
      { timeout: 240_000, intervals: [500, 1000, 2000] },
    )
    .toBe(true);
  return readSuggestion(request, agent, id);
}

/** Opens the Agent's Evaluation view, then its Suggestions tab. */
export async function openSuggestions(page: Page, agent: PublishedAgent): Promise<void> {
  await page.goto(agent.path);
  await expect(page.getByRole("heading", { level: 1, name: agent.name })).toBeVisible({ timeout: 15_000 });
  await openAgentView(page, "Evaluation");
  await page.getByRole("radiogroup", { name: "Evaluation view" }).getByRole("radio", { name: "Suggestions" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Suggestions" })).toBeVisible({ timeout: 15_000 });
}

/** The Suggestions tab's list of runs. */
export function suggestionList(page: Page) {
  return page.getByRole("list", { name: "Suggestion runs" });
}

/** Waits until the Agent's latest Evaluation Run has finished. */
export async function finishedRun(request: APIRequestContext, agent: PublishedAgent, runId: string): Promise<{ status: string }> {
  await expect
    .poll(async () => (await json<{ status: string }>(request, "GET", `${agent.api}/evaluation/runs/${runId}`)).status, { timeout: 180_000 })
    .toMatch(/completed|failed|cancelled/);
  return json<{ status: string }>(request, "GET", `${agent.api}/evaluation/runs/${runId}`);
}
