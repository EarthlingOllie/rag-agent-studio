import { expect, type APIRequestContext, type Browser, type Page } from "@playwright/test";

import { openSection } from "./navigation";

/**
 * Builds Suggestion evidence in the signed-in Owner's own, freshly signed-up Organisation, so the
 * Suggestion specs never touch the demo Organisation.
 *
 * The Organisation answers with the demo provider's model: it quotes the first Chunk it retrieves
 * and cites it; told "Don't quote" in its system prompt, it gives that Chunk's first sentence alone,
 * uncited. The Evaluation Model is the fake gateway's Claude (priced, so Costs are not zero). Both
 * judge by rule: grounding passes when a reply cites a Chunk, a Reference answer when the answer
 * holds its quoted key phrase. Asked to propose a Suggestion they also answer by rule
 * (`backend/app/suggestions/fake_proposer.py`): the citing line below for evidence that failed
 * grounding, the Minimum Score lowered by 0.05 for evidence with a Chunk excluded within 0.05 under
 * it, and one Knowledge Base gap for each failed Live Verdict whose reply cited no Chunk.
 */
export const DEMO_KEY = "demo-no-key-needed";
export const FAKE_CLAUDE_KEY = "sk-ant-e2e-test-only-not-a-real-key-5c16";
export const CURT_PROMPT = "Answer staff questions in one short sentence. Don't quote the handbook.";
export const CITE_LINE = "Always cite the passage you used.";
export const GAP_TOPIC = "Fake proposer: a question no Chunk covered";
const BOOT = /<script id="widget-boot" type="application\/json">(.*?)<\/script>/;
const DONE = /event: done\ndata: (.*)\n/;

export const LEAVE_POLICY = {
  name: "leave-policy.md",
  mimeType: "text/markdown",
  buffer: Buffer.from(
    "# Leave policy\n\nEveryone gets 25 days of annual leave a year. Up to five unused days carry over to the next year. " +
      "Book leave in the HR portal at least two weeks ahead.\n",
  ),
};

export interface Draft {
  behaviour: Record<string, unknown>;
  retrieval: Record<string, unknown>;
  [section: string]: unknown;
}

export interface Built {
  organisation: string;
  organisationId: string;
  project: string;
  projectId: string;
}

export async function call<T>(request: APIRequestContext, method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE", url: string, data?: unknown): Promise<T> {
  const response = await request.fetch(url, { method, data });
  expect(response.ok(), `${method} ${url}: ${await response.text()}`).toBe(true);
  const body = await response.text();
  return (body === "" ? undefined : JSON.parse(body)) as T;
}

/**
 * Sets up the signed-in Owner's new Organisation: the demo model as the Default Model, the fake
 * Claude as the Evaluation Model, and a Project with the leave policy, uploaded in the Studio and
 * Ready.
 */
export async function buildOrganisation(page: Page, projectName: string): Promise<Built> {
  await page.goto("/");
  const me = await call<{ organisations: { id: string }[] }>(page.request, "GET", "/api/auth/me");
  const organisationId = me.organisations[0]?.id ?? "";
  const organisation = `/api/organisations/${organisationId}`;
  const demo = await call<{ id: string }>(page.request, "POST", `${organisation}/credentials`, { name: "Demo model", provider: "demo", api_key: DEMO_KEY });
  await call(page.request, "PUT", `${organisation}/default-model`, { credential_id: demo.id, model: "demo-chat" });
  const claude = await call<{ id: string }>(page.request, "POST", `${organisation}/credentials`, {
    name: "Support Claude",
    provider: "anthropic",
    api_key: FAKE_CLAUDE_KEY,
  });
  await call(page.request, "PUT", `${organisation}/evaluation-model`, { credential_id: claude.id, model: "claude-haiku-4-5" });
  // Live Verdicts need an Evaluation budget; Suggestion runs never count against it.
  await call(page.request, "PUT", `${organisation}/evaluation-budget`, { evaluation_budget_usd: "50.00" });

  await openSection(page, "Organisation sections", "Projects");
  await page.getByRole("button", { name: "New Project" }).click();
  const form = page.getByRole("form", { name: "New Project" });
  await form.getByLabel("Name").fill(projectName);
  await form.getByRole("button", { name: "Create Project" }).click();
  await expect(page.getByText(/No Documents yet/)).toBeVisible({ timeout: 15_000 });
  const projectId = /\/projects\/([0-9a-f-]+)/.exec(page.url())?.[1] ?? "";
  await page.getByLabel("Upload", { exact: true }).setInputFiles(LEAVE_POLICY);
  const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /leave-policy\.md/ });
  await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 90_000 });
  return { organisation, organisationId, project: `${organisation}/projects/${projectId}`, projectId };
}

export interface BuiltAgent {
  api: string;
  id: string;
  publicId: string;
  /** The Agent's page in the Studio. */
  path: string;
}

/** Creates an Agent with the curt prompt and Automatic retrieval, judging every Visitor reply and admitting plenty of messages. */
export async function newAgent(page: Page, built: Built, name: string, retrieval: Record<string, unknown> = {}): Promise<BuiltAgent> {
  const created = await call<{ id: string; public_id: string; draft: Draft }>(page.request, "POST", `${built.project}/agents`, { name });
  const api = `${built.project}/agents/${created.id}`;
  await saveDraft(page, api, { system_prompt: CURT_PROMPT }, { mode: "automatic", ...retrieval });
  await call(page.request, "PATCH", `${api}/operational-settings`, {
    live_sample_rate: 100,
    conversation_messages_per_minute: 120,
    ip_messages_per_minute: 600,
  });
  return { api, id: created.id, publicId: created.public_id, path: api.replace(/^\/api/, "") };
}

/** Merges changes into the Agent's Draft and saves it. */
export async function saveDraft(page: Page, agent: string, behaviour: Record<string, unknown>, retrieval: Record<string, unknown> = {}) {
  const { draft } = await call<{ draft: Draft }>(page.request, "GET", agent);
  await call(page.request, "PUT", `${agent}/draft`, {
    ...draft,
    behaviour: { ...draft.behaviour, ...behaviour },
    retrieval: { ...draft.retrieval, ...retrieval },
  });
}

export async function publish(page: Page, agent: string, note: string): Promise<{ id: string; number: number }> {
  return call<{ id: string; number: number }>(page.request, "POST", `${agent}/versions`, { note });
}

/** A Visitor's widget Conversation with the Agent, through the widget API. */
export interface Visitor {
  /** Sends a message; resolves to the reply's Message id. */
  ask: (content: string) => Promise<string>;
  /** Gives a reply a thumbs-up or -down, with an optional comment. */
  feedback: (messageId: string, rating: "up" | "down", comment?: string) => Promise<void>;
  /** Rates the Conversation, 1 to 5. */
  rate: (score: number) => Promise<void>;
  close: () => Promise<void>;
}

export async function visit(browser: Browser, publicId: string): Promise<Visitor> {
  const context = await browser.newContext();
  const shell = await (await context.request.get(`/widget/a/${publicId}`)).text();
  const boot = JSON.parse(BOOT.exec(shell)?.[1] ?? "{}") as { bootstrap_token: string };
  const started = await context.request.post(`/api/widget/agents/${publicId}/conversations`, { data: { bootstrap_token: boot.bootstrap_token } });
  expect(started.status(), await started.text()).toBe(201);
  const { conversation_token: token } = (await started.json()) as { conversation_token: string };
  const headers = { Authorization: `Bearer ${token}` };
  return {
    ask: async (content) => {
      const asked = await context.request.post(`/api/widget/agents/${publicId}/messages`, { data: { content }, headers });
      expect(asked.status(), await asked.text()).toBe(200);
      const done = DONE.exec(await asked.text());
      expect(done, "the reply finished").not.toBeNull();
      return (JSON.parse(done?.[1] ?? "{}") as { message_id: string }).message_id;
    },
    feedback: async (messageId, rating, comment) => {
      const given = await context.request.put(`/api/widget/agents/${publicId}/messages/${messageId}/feedback`, {
        data: comment === undefined ? { rating } : { rating, comment },
        headers,
      });
      expect(given.ok(), await given.text()).toBe(true);
    },
    rate: async (score) => {
      const rated = await context.request.put(`/api/widget/agents/${publicId}/conversation/rating`, { data: { score }, headers });
      expect(rated.ok(), await rated.text()).toBe(true);
    },
    close: () => context.close(),
  };
}

export interface EvidenceCount {
  range_start: string;
  range_end: string;
  total: number;
  live_verdict: number;
  thumbs_down: number;
  low_rating: number;
  evaluation_case: number;
  likely_noise: boolean;
}

/** The evidence the run dialog would count for the range (the last 14 UTC days by default). */
export async function evidence(page: Page, agent: string, range?: { range_start: string; range_end: string }): Promise<EvidenceCount> {
  const query = range === undefined ? "" : `?range_start=${range.range_start}&range_end=${range.range_end}`;
  return call<EvidenceCount>(page.request, "GET", `${agent}/suggestions/evidence${query}`);
}

/** Waits until the worker has judged as many replies as failed their Live Verdict. */
export async function waitForFailedVerdicts(page: Page, agent: string, count: number) {
  await expect.poll(async () => (await evidence(page, agent)).live_verdict, { timeout: 90_000 }).toBe(count);
}

/** Adds an Evaluation Case; the curt reply never holds `"purple elephants"`, so a case expecting it fails. */
export async function addCase(page: Page, agent: string, question: string, reference: string): Promise<{ id: string }> {
  return call<{ id: string }>(page.request, "POST", `${agent}/evaluation/cases`, {
    question,
    reference_answer: reference,
    expected_sources: [],
    expect_fallback: false,
    source: "written",
  });
}

/** Starts an Evaluation Run of the Live Version and waits for it to finish. */
export async function evaluate(page: Page, agent: string): Promise<string> {
  const run = await call<{ id: string }>(page.request, "POST", `${agent}/evaluation/runs`, { sides: null });
  await expect
    .poll(async () => (await call<{ status: string }>(page.request, "GET", `${agent}/evaluation/runs/${run.id}`)).status, { timeout: 180_000 })
    .toBe("completed");
  return run.id;
}

export interface SuggestionOut {
  id: string;
  status: string;
  outcome: "changes" | "gaps_only" | "no_change" | null;
  range_start: string;
  range_end: string;
  base_version_number: number;
  evidence_total: number;
  explanation: string | null;
  cost: { estimated_proposing_usd: string | null; estimated_checking_usd: string | null; proposing_usd: string | null; checking_usd: string | null };
  check: { state: string; evaluation_run_id: string | null } | null;
  changes: { path: string; base_value: string | number; suggested_value: string | number; explanation: string; evidence_ids: string[] }[];
  gaps: { topic: string; explanation: string; evidence_ids: string[] }[];
  evidence: {
    id: string;
    label: string;
    kind: string;
    kinds: string[];
    message_id: string | null;
    run_case_id: string | null;
    live_verdict: "pass" | "fail" | null;
    text_purged: boolean;
  }[];
}

export async function readSuggestion(page: Page, agent: string, id: string): Promise<SuggestionOut> {
  return call<SuggestionOut>(page.request, "GET", `${agent}/suggestions/${id}`);
}

/** Waits for a Suggestion run to stop (completed, failed or cancelled); returns it. */
export async function finished(page: Page, agent: string, id: string): Promise<SuggestionOut> {
  await expect
    .poll(async () => (await readSuggestion(page, agent, id)).status, { timeout: 240_000 })
    .toMatch(/^(completed|failed|cancelled)$/);
  return readSuggestion(page, agent, id);
}

/** Opens the Agent's Evaluation view, Suggestions tab. */
export async function openSuggestions(page: Page, agentPath: string) {
  await page.goto(`${agentPath}/evaluation`);
  await page.getByRole("radiogroup", { name: "Evaluation view" }).getByRole("radio", { name: "Suggestions" }).click({ timeout: 15_000 });
  await expect(page.getByRole("heading", { level: 2, name: "Suggestions" })).toBeVisible({ timeout: 15_000 });
}
