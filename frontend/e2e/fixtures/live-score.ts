import { execFileSync } from "node:child_process";

import { type APIRequestContext, expect, type Page } from "@playwright/test";

import { MAILPIT_URL } from "./env";

/**
 * Helpers for the Live score and Evaluation budget specs (`tests/live-score-*.spec.ts`,
 * `tests/evaluation-budget-*.spec.ts`). Each spec works in a freshly signed-up Organisation that
 * answers with the demo provider's model: it quotes and cites the first Chunk it retrieves, and
 * as the Evaluation Model it judges by rule (`backend/app/evaluation/fake_judge.py`): grounding
 * passes when the reply cites a Chunk, "answers the question" when the reply shares a key phrase
 * with the question (its phrases in double quotes, else its words of five letters or more).
 *
 * So a question about "annual leave" gets a reply quoting the handbook's leave Chunk, which passes
 * both checks, and the same question with a quoted phrase the handbook lacks fails "answers the
 * question": a test chooses exactly which replies pass.
 */
export const DEMO_KEY = "demo-no-key-needed";
/** The fake gateway's Claude: priced, unlike the demo model. Not a real key. */
export const FAKE_CLAUDE_KEY = "sk-ant-e2e-test-only-not-a-real-key-b15b";
export const PASSING_QUESTION = "How much annual leave do I get?";
export const FAILING_QUESTION = 'How much annual leave do I get? "zebra crossing"';
export const HANDBOOK = {
  name: "leave-handbook.md",
  mimeType: "text/markdown",
  buffer: Buffer.from("# Leave handbook\n\nEveryone gets 25 days of annual leave a year. Book annual leave in the HR portal.\n"),
};
const BOOT = /<script id="widget-boot" type="application\/json">(.*?)<\/script>/;

export interface Organisation {
  organisationId: string;
  /** The Organisation's API path, `/api/organisations/<id>`. */
  organisation: string;
}

export interface LiveAgent {
  id: string;
  publicId: string;
  /** The Agent's API path. */
  api: string;
  /** The Agent's Studio path. */
  path: string;
}

export interface LiveScore {
  n: number;
  passed: number;
  rate: number | null;
  low: number | null;
  high: number | null;
  low_confidence: boolean;
}

async function ok(response: Awaited<ReturnType<APIRequestContext["fetch"]>>, what: string) {
  expect(response.ok(), `${what}: ${String(response.status())} ${await response.text()}`).toBe(true);
  return response;
}

/** The signed-in Owner's (only) Organisation, now answering with the demo model by default. */
export async function demoOrganisation(page: Page): Promise<Organisation> {
  await page.goto("/");
  const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
  const organisationId = me.organisations[0]?.id ?? "";
  const organisation = `/api/organisations/${organisationId}`;
  const credential = await ok(
    await page.request.post(`${organisation}/credentials`, { data: { name: "Demo model", provider: "demo", api_key: DEMO_KEY } }),
    "add the demo credential",
  );
  const { id } = (await credential.json()) as { id: string };
  await ok(await page.request.put(`${organisation}/default-model`, { data: { credential_id: id, model: "demo-chat" } }), "default model");
  await ok(await page.request.put(`${organisation}/evaluation-model`, { data: { credential_id: id, model: "demo-chat" } }), "evaluation model");
  return { organisationId, organisation };
}

/** Sets (or with null removes) the Organisation's monthly Evaluation budget through the API. */
export async function setEvaluationBudget(request: APIRequestContext, organisation: string, usd: string | null) {
  await ok(await request.put(`${organisation}/evaluation-budget`, { data: { evaluation_budget_usd: usd } }), "set the Evaluation budget");
}

/** Creates a Project in the Studio and uploads the leave handbook, waiting until it is Ready. Returns its API path. */
export async function projectWithHandbook(page: Page, { organisationId, organisation }: Organisation, name: string): Promise<string> {
  const created = await ok(await page.request.post(`${organisation}/projects`, { data: { name } }), "create the Project");
  const { id } = (await created.json()) as { id: string };
  await page.goto(`/organisations/${organisationId}/projects/${id}`);
  await expect(page.getByText(/No Documents yet/)).toBeVisible({ timeout: 15_000 });
  await page.getByLabel("Upload", { exact: true }).setInputFiles(HANDBOOK);
  const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /leave-handbook\.md/ });
  await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 90_000 });
  return `${organisation}/projects/${id}`;
}

/**
 * Creates an Automatic Agent with `prompt`, lets Visitors send as fast as a test needs, and
 * publishes v1. The Live sample rate is left at its default (0%).
 */
export async function liveAgent(page: Page, project: string, name: string, prompt = "Answer from the handbook."): Promise<LiveAgent> {
  const created = await ok(await page.request.post(`${project}/agents`, { data: { name } }), "create the Agent");
  const { id, public_id: publicId } = (await created.json()) as { id: string; public_id: string };
  const api = `${project}/agents/${id}`;
  await ok(
    await page.request.patch(`${api}/operational-settings`, {
      data: { conversation_messages_per_minute: 1000, ip_messages_per_minute: 10000 },
    }),
    "raise the rate limits",
  );
  await publishWith(page, api, prompt, "First release", { mode: "automatic" });
  return { id, publicId, api, path: api.replace(/^\/api/, "") };
}

/** Saves `prompt` in the Draft and publishes it as the next Version. */
export async function publishWith(page: Page, api: string, prompt: string, note: string, retrieval: Record<string, unknown> = {}) {
  const { draft } = (await (await page.request.get(api)).json()) as {
    draft: { behaviour: Record<string, unknown>; retrieval: Record<string, unknown> };
  };
  await ok(
    await page.request.put(`${api}/draft`, {
      data: { ...draft, behaviour: { ...draft.behaviour, system_prompt: prompt }, retrieval: { ...draft.retrieval, ...retrieval } },
    }),
    "save the Draft",
  );
  await ok(await page.request.post(`${api}/versions`, { data: { note } }), "publish");
}

/** Sets the Agent's Live sample rate through the API. */
export async function setSampleRate(request: APIRequestContext, agent: LiveAgent, rate: number) {
  await ok(await request.patch(`${agent.api}/operational-settings`, { data: { live_sample_rate: rate } }), "set the Live sample rate");
}

/**
 * A Visitor's Conversation through the widget's API: each question in turn, each reply streamed
 * to its end. `visitor` is a request context of a browser context with no Studio session.
 * Returns the replies' Message ids.
 */
export async function visitorAsks(visitor: APIRequestContext, agent: LiveAgent, questions: string[]): Promise<string[]> {
  const shell = await (await visitor.get(`/widget/a/${agent.publicId}`)).text();
  const boot = JSON.parse(BOOT.exec(shell)?.[1] ?? "{}") as { bootstrap_token: string };
  const started = await visitor.post(`/api/widget/agents/${agent.publicId}/conversations`, { data: { bootstrap_token: boot.bootstrap_token } });
  expect(started.status(), await started.text()).toBe(201);
  const { conversation_token: token } = (await started.json()) as { conversation_token: string };
  const replies: string[] = [];
  for (const question of questions) {
    const asked = await visitor.post(`/api/widget/agents/${agent.publicId}/messages`, {
      data: { content: question },
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(asked.status()).toBe(200);
    const done = /event: done\ndata: (.*)\n/.exec(await asked.text());
    expect(done, "the reply finished").not.toBeNull();
    replies.push((JSON.parse(done?.[1] ?? "{}") as { message_id: string }).message_id);
  }
  return replies;
}

/** `count` Visitor Conversations of one question each, a few at a time. */
export async function visitorsAsk(visitor: APIRequestContext, agent: LiveAgent, question: string, count: number) {
  for (let sent = 0; sent < count; sent += 5) {
    await Promise.all(Array.from({ length: Math.min(5, count - sent) }, () => visitorAsks(visitor, agent, [question])));
  }
}

/** Each Version's Live score from the Version KPIs (today's partial day included), by Version number. */
export async function liveScores(request: APIRequestContext, agent: LiveAgent): Promise<Map<number, LiveScore>> {
  const response = await ok(await request.get(`${agent.api}/metrics`), "read the Version KPIs");
  const { versions } = (await response.json()) as { versions: { number: number; live_score: LiveScore }[] };
  return new Map(versions.map((each) => [each.number, each.live_score]));
}

/** Waits until Version `version` has `judged` judged Live Verdicts (the worker judges in the background). */
export async function waitForJudged(request: APIRequestContext, agent: LiveAgent, version: number, judged: number) {
  await expect
    .poll(async () => (await liveScores(request, agent)).get(version)?.n ?? 0, { timeout: 120_000, message: `v${String(version)} judged` })
    .toBe(judged);
}

function container(service: string): string {
  const id = execFileSync("docker", ["ps", "-q", "--filter", `label=com.docker.compose.service=${service}`], { encoding: "utf8" })
    .trim()
    .split("\n")[0];
  if (!id) throw new Error(`The stack's ${service} container is not running`);
  return id;
}

/**
 * Runs the hourly usage rollup now, with its alerts step (the Block rate check and the Live score
 * drop check), as an operator re-running it by hand would. Beat runs it hourly; the stack has no
 * clock a test can move.
 */
export function runHourlyRollup() {
  execFileSync("docker", ["exec", container("worker"), "python", "-c", "from app.analytics.tasks import roll_up_usage; roll_up_usage()"], {
    stdio: "pipe",
  });
}

/** Runs one SQL statement in the stack's database and returns psql's output. */
export function psql(sql: string): string {
  return execFileSync("docker", ["exec", container("postgres"), "psql", "-U", "studio", "-d", "studio", "-v", "ON_ERROR_STOP=1", "-tAc", sql], {
    encoding: "utf8",
  }).trim();
}

/** The emails Mailpit holds for `address` whose subject contains `subject`. */
export async function emailsTo(request: APIRequestContext, address: string, subject: string): Promise<{ ID: string; Subject: string }[]> {
  const search = new URL("/api/v1/search", MAILPIT_URL);
  search.searchParams.set("query", `to:"${address}" subject:"${subject}"`);
  const response = await request.get(search.toString());
  expect(response.ok()).toBe(true);
  return ((await response.json()) as { messages: { ID: string; Subject: string }[] }).messages;
}

/** The text of the Mailpit email with `id`. */
export async function emailText(request: APIRequestContext, id: string): Promise<string> {
  const response = await request.get(new URL(`/api/v1/message/${id}`, MAILPIT_URL).toString());
  return ((await response.json()) as { Text: string }).Text;
}

/** The Studio path and query of the first link in `text` that contains `part`. */
export function studioLink(text: string, part: string): string {
  const found = text.match(/https?:\/\/\S+/g)?.find((link) => link.includes(part));
  if (found === undefined) throw new Error(`No link with ${part} in:\n${text}`);
  const url = new URL(found);
  return `${url.pathname}${url.search}`;
}

/** The id of the Visitor Conversation in `project` that holds the reply `messageId`. */
export async function conversationOf(request: APIRequestContext, project: string, agent: LiveAgent, messageId: string): Promise<string> {
  const listed = (await (await request.get(`${project}/conversations?agent_id=${agent.id}&page_size=100`)).json()) as { items: { id: string }[] };
  for (const { id } of listed.items) {
    const detail = (await (await request.get(`${project}/conversations/${id}`)).json()) as { messages: { id: string }[] };
    if (detail.messages.some((message) => message.id === messageId)) return id;
  }
  throw new Error(`No Conversation holds ${messageId}`);
}

/** The Live Verdict of a reply, as its Trace has it (null when the reply wasn't sampled). */
export async function liveVerdictOf(
  request: APIRequestContext,
  project: string,
  agent: LiveAgent,
  messageId: string,
): Promise<{ status: string; passed: boolean | null } | null> {
  const conversation = await conversationOf(request, project, agent, messageId);
  const trace = await ok(await request.get(`${project}/conversations/${conversation}/messages/${messageId}/trace`), "read the Trace");
  return ((await trace.json()) as { live_verdict: { status: string; passed: boolean | null } | null }).live_verdict;
}
