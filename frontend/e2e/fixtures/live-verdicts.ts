import { type Browser, expect, type Page } from "@playwright/test";

/**
 * Live Verdict set-up for a freshly signed-up Organisation (spec 15): the demo provider's model,
 * a Project with a Document, a Published Agent, an Evaluation budget and a Live sample rate, and
 * a Visitor talking to the Agent through the widget API.
 *
 * The demo model quotes the first Chunk it is given and cites it ("from <document> [C1]: ...");
 * told "Don't quote" in its system prompt, it gives that Chunk's first sentence alone, uncited.
 * Its judge (and the fake gateway's) judges by rule: grounding passes when the reply cites a
 * Chunk; answering the question passes when the reply shares a word of five letters or more (or
 * a phrase in double quotes) with the question.
 */
export const DEMO_KEY = "demo-no-key-needed";
// The fake gateway's chat model stands in for Claude; nothing real is called.
export const FAKE_CLAUDE_KEY = "sk-ant-e2e-test-only-not-a-real-key-l15a";

const BOOT = /<script id="widget-boot" type="application\/json">(.*?)<\/script>/;

export interface LiveOrganisation {
  organisationId: string;
  /** `/api/organisations/<id>` */
  organisation: string;
  /** The demo credential's id. */
  credentialId: string;
}

/** The signed-in Owner's new Organisation, with a demo credential, the Default Model unless `defaultModel` is false. */
export async function demoOrganisation(page: Page, { defaultModel = true } = {}): Promise<LiveOrganisation> {
  await page.goto("/");
  const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
  const organisationId = me.organisations[0]?.id ?? "";
  const organisation = `/api/organisations/${organisationId}`;
  const credential = await page.request.post(`${organisation}/credentials`, {
    data: { name: "Demo model", provider: "demo", api_key: DEMO_KEY },
  });
  expect(credential.status()).toBe(201);
  const { id: credentialId } = (await credential.json()) as { id: string };
  if (defaultModel) {
    const chosen = await page.request.put(`${organisation}/default-model`, { data: { credential_id: credentialId, model: "demo-chat" } });
    expect(chosen.status()).toBe(200);
  }
  return { organisationId, organisation, credentialId };
}

/** Sets the Organisation's monthly Evaluation budget through the API. */
export async function setEvaluationBudget(page: Page, org: LiveOrganisation, usd: string) {
  const response = await page.request.put(`${org.organisation}/evaluation-budget`, { data: { evaluation_budget_usd: usd } });
  expect(response.status()).toBe(200);
}

export interface LiveProject {
  projectId: string;
  /** `/api/organisations/<id>/projects/<id>` */
  project: string;
  /** The Studio's path to the Project. */
  projectPage: string;
}

/** A Project with one Markdown Document, uploaded in the Studio and Ready. */
export async function projectWithDocument(page: Page, org: LiveOrganisation, name: string, document: { name: string; body: string }): Promise<LiveProject> {
  const created = await page.request.post(`${org.organisation}/projects`, { data: { name } });
  expect(created.status()).toBe(201);
  const { id: projectId } = (await created.json()) as { id: string };
  const projectPage = `/organisations/${org.organisationId}/projects/${projectId}`;
  await page.goto(projectPage);
  await page.getByLabel("Upload", { exact: true }).setInputFiles({
    name: document.name,
    mimeType: "text/markdown",
    buffer: Buffer.from(`# ${document.name}\n\n${document.body}\n`),
  });
  const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: new RegExp(document.name.replace(/\./g, "\\.")) });
  await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
  return { projectId, project: `${org.organisation}/projects/${projectId}`, projectPage };
}

export interface LiveAgent {
  agentId: string;
  publicId: string;
  /** `/api/organisations/<id>/projects/<id>/agents/<id>` */
  agentApi: string;
  /** The Studio's path to the Agent. */
  agentPage: string;
}

/** An Agent in Automatic Retrieval Mode with `draft` merged into its Draft, Published as v1. */
export async function publishedAgent(page: Page, project: LiveProject, name: string, draft: Record<string, unknown> = {}): Promise<LiveAgent> {
  const created = await page.request.post(`${project.project}/agents`, { data: { name } });
  expect(created.status()).toBe(201);
  const { id: agentId, public_id: publicId } = (await created.json()) as { id: string; public_id: string };
  const agentApi = `${project.project}/agents/${agentId}`;
  const { retrieval, ...rest } = draft as { retrieval?: Record<string, unknown> };
  const saved = await page.request.put(`${agentApi}/draft`, { data: { ...rest, retrieval: { mode: "automatic", ...retrieval } } });
  expect(saved.ok(), await saved.text()).toBe(true);
  const published = await page.request.post(`${agentApi}/versions`, { data: { note: "First release" } });
  expect(published.status(), await published.text()).toBe(201);
  // Tests send many Visitor messages a minute, from one address shared with other tests.
  const limits = await page.request.patch(`${agentApi}/operational-settings`, {
    data: { conversation_messages_per_minute: 1000, ip_messages_per_minute: 10000 },
  });
  expect(limits.status(), await limits.text()).toBe(200);
  return { agentId, publicId, agentApi, agentPage: `${project.projectPage}/agents/${agentId}` };
}

/** Sets the Agent's Live sample rate through the API. */
export async function setSampleRate(page: Page, agent: LiveAgent, rate: number) {
  const response = await page.request.patch(`${agent.agentApi}/operational-settings`, { data: { live_sample_rate: rate } });
  expect(response.status(), await response.text()).toBe(200);
}

export interface VisitorChat {
  /** Sends a message and returns the stored reply's id, once the reply has streamed to the end. */
  ask: (question: string) => Promise<string>;
  close: () => Promise<void>;
}

/** A Visitor (another browser context, no Studio session) starting a widget Conversation with the Agent. */
export async function visitorChat(browser: Browser, agent: LiveAgent): Promise<VisitorChat> {
  const visitor = await browser.newContext();
  const shell = await (await visitor.request.get(`/widget/a/${agent.publicId}`)).text();
  const boot = JSON.parse(BOOT.exec(shell)?.[1] ?? "{}") as { bootstrap_token: string };
  const started = await visitor.request.post(`/api/widget/agents/${agent.publicId}/conversations`, {
    data: { bootstrap_token: boot.bootstrap_token },
  });
  expect(started.status()).toBe(201);
  const { conversation_token: token } = (await started.json()) as { conversation_token: string };
  return {
    ask: async (question: string) => {
      const asked = await visitor.request.post(`/api/widget/agents/${agent.publicId}/messages`, {
        data: { content: question },
        headers: { Authorization: `Bearer ${token}` },
      });
      expect(asked.status()).toBe(200);
      const body = await asked.text();
      const done = /event: done\ndata: (\{.*\})/.exec(body);
      expect(done, body).not.toBeNull();
      return (JSON.parse(done?.[1] ?? "{}") as { message_id: string }).message_id;
    },
    close: () => visitor.close(),
  };
}

export interface LiveCheck {
  outcome: "pass" | "fail";
  reason: string | null;
}

export interface LiveVerdictRead {
  status: "pending" | "judged" | "error" | "skipped";
  grounded: LiveCheck | null;
  answers_question: LiveCheck | null;
  passed: boolean | null;
  error_reason: string | null;
  judge_provider: string | null;
  judge_model: string | null;
  judged_at: string | null;
  purged_at: string | null;
}

interface ConversationSummary {
  id: string;
  failed_live_verdicts: number;
}

/** The Agent's Conversations through the API, newest first, optionally filtered by Live Verdict. */
export async function conversationsOf(page: Page, project: LiveProject, agent: LiveAgent, live?: string): Promise<ConversationSummary[]> {
  const params: Record<string, string> = { agent_id: agent.agentId, page_size: "100" };
  if (live !== undefined) params.live_verdict = live;
  const response = await page.request.get(`${project.project}/conversations`, { params });
  expect(response.status()).toBe(200);
  return ((await response.json()) as { items: ConversationSummary[] }).items;
}

/** The Conversation (of the Agent's) holding the reply. */
export async function conversationOfReply(page: Page, project: LiveProject, agent: LiveAgent, replyId: string): Promise<string> {
  for (const conversation of await conversationsOf(page, project, agent)) {
    const read = (await (await page.request.get(`${project.project}/conversations/${conversation.id}`)).json()) as {
      messages: { id: string }[];
    };
    if (read.messages.some((message) => message.id === replyId)) return conversation.id;
  }
  throw new Error(`No Conversation holds the reply ${replyId}`);
}

/** The reply's Live Verdict as its Trace returns it (null when it wasn't chosen). */
export async function liveVerdictOf(page: Page, project: LiveProject, conversationId: string, replyId: string): Promise<LiveVerdictRead | null> {
  const response = await page.request.get(`${project.project}/conversations/${conversationId}/messages/${replyId}/trace`);
  expect(response.status()).toBe(200);
  return ((await response.json()) as { live_verdict: LiveVerdictRead | null }).live_verdict;
}

/** Waits for the worker to finish judging the reply, and returns its Live Verdict. */
export async function settledVerdict(page: Page, project: LiveProject, conversationId: string, replyId: string): Promise<LiveVerdictRead> {
  let verdict: LiveVerdictRead | null = null;
  await expect
    .poll(
      async () => {
        verdict = await liveVerdictOf(page, project, conversationId, replyId);
        return verdict?.status ?? "not chosen";
      },
      { timeout: 60_000 },
    )
    .not.toBe("pending");
  // Assigned in the poll's callback, which TypeScript can't follow.
  const settled = verdict as LiveVerdictRead | null;
  if (settled === null) throw new Error(`The reply ${replyId} wasn't chosen for a Live Verdict`);
  return settled;
}

/** In an open Conversation: a reply (by position among the Agent's replies), with its Trace unfolded. */
export async function openReplyTrace(page: Page, agentName: string, index: number) {
  const reply = page.getByRole("list", { name: "Messages" }).getByRole("listitem", { name: agentName }).nth(index);
  await reply.getByText("Trace", { exact: true }).click();
  return reply;
}
