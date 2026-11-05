import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { server } from "./server";

export type Agent = Schemas["AgentOut"];
type Draft = Agent["draft"];
type ModelOut = Schemas["ModelOut"];
type Credential = Schemas["CredentialOut"];
type Tag = Schemas["TagOut"];

/** A new Agent's Draft, as the API returns it: every group at its defaults. */
export const defaultDraft: Draft = {
  behaviour: {
    system_prompt: "",
    model: null,
    temperature: 0.7,
    max_output_tokens: 1024,
    remembered_turns: 5,
    fallback_text: "Sorry, I don't know the answer to that.",
  },
  retrieval: { top_k: 5, hybrid_weight: 0.5, min_score: 0, tag_ids: [], reranker: null, citations: true },
  experience: {
    display_name: "",
    avatar_url: null,
    greeting: "",
    starter_questions: [],
    ui_text: { send_button: null, rate_conversation: null, unavailable_message: null },
    rating_prompt_after: 3,
  },
  guardrails: { input_mode: "block", classifier: null, fail_mode: "closed", refusal_text: "Sorry, I can't help with that request." },
};

const credential = (id: string, name: string, provider: Credential["provider"], capabilities: Credential["capabilities"]): Credential => ({
  id,
  name,
  provider,
  auth_kind: "api_key",
  masked_suffix: "wxyz",
  role_arn: null,
  region: null,
  capabilities,
  check_status: "passed",
  check_failure: null,
  last_checked_at: "2026-11-05T09:00:00Z",
  created_at: "2026-11-05T09:00:00Z",
});

export const openAi = credential("c1000000-0000-4000-8000-000000000001", "OpenAI", "openai", ["chat", "embeddings"]);
export const claude = credential("c1000000-0000-4000-8000-000000000002", "Claude", "anthropic", ["chat"]);
export const voyage = credential("c1000000-0000-4000-8000-000000000003", "Voyage", "voyage", ["embeddings", "rerank"]);

/** Models per credential and capability, as `GET …/credentials/{id}/models/{capability}` answers. */
export const offeredModels: Record<string, ModelOut[]> = {
  [`${openAi.id}/chat`]: [
    { id: "gpt-4.1", name: "GPT-4.1" },
    { id: "gpt-4.1-mini", name: "GPT-4.1 mini" },
  ],
  [`${claude.id}/chat`]: [
    { id: "claude-sonnet-4-5", name: "Claude Sonnet 4.5" },
    { id: "claude-haiku-4-5", name: "Claude Haiku 4.5" },
  ],
  [`${voyage.id}/rerank`]: [
    { id: "rerank-2.5", name: "rerank-2.5" },
    { id: "rerank-2.5-lite", name: "rerank-2.5-lite" },
  ],
};

export const hrTag: Tag = { id: "d1000000-0000-4000-8000-000000000001", name: "HR", document_count: 2, created_at: "2026-11-05T09:00:00Z" };
export const payTag: Tag = { id: "d1000000-0000-4000-8000-000000000002", name: "Pay", document_count: 1, created_at: "2026-11-05T09:00:00Z" };

export const hrHelper: Agent = {
  id: "a9e00000-0000-4000-8000-000000000001",
  public_id: "agt_abcdefghijklmnopqrstuvwx",
  project_id: "7c2d1e69-1e7f-4d2c-8e2f-2a2b7d1a0b01",
  name: "HR helper",
  created_at: "2026-11-05T09:00:00Z",
  archived_at: null,
  draft: {
    ...defaultDraft,
    behaviour: { ...defaultDraft.behaviour, system_prompt: "Answer from the handbook.", fallback_text: "Ask HR, please." },
    retrieval: { ...defaultDraft.retrieval, hybrid_weight: 0.7, min_score: 0.25 },
  },
  draft_updated_at: "2026-11-05T09:00:00Z",
};

export const CONVERSATION_ID = "c0000000-0000-4000-8000-000000000001";

const done = {
  message_id: "e0000000-0000-4000-8000-000000000001",
  input_tokens: 120,
  output_tokens: 6,
  first_token_ms: 40,
  latency_ms: 85,
  fallback: false,
  chunks: [{ chunk_id: "f0000000-0000-4000-8000-000000000001", score: 0.92, relevance: 0.81, rank: 1 }],
  excluded: [],
};

function sse(event: string, data: unknown) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** A Server-Sent Events body that arrives in pieces, splitting events across reads. */
export function streamedAnswer(tokens: string[], options: { end?: boolean } = {}) {
  const body = tokens.map((text) => sse("token", { text })).join("") + (options.end === false ? "" : sse("done", done));
  const encoder = new TextEncoder();
  const pieces = [body.slice(0, 7), body.slice(7, 40), body.slice(40)];
  return new HttpResponse(
    new ReadableStream({
      start(controller) {
        for (const piece of pieces) controller.enqueue(encoder.encode(piece));
        controller.close();
      },
    }),
    { headers: { "content-type": "text/event-stream" } },
  );
}

/**
 * A stateful stand-in for the Agents and Playground APIs. Records the requests it receives;
 * `answer` decides each streamed reply.
 */
export function fakeAgentsApi(
  options: {
    agents?: Agent[];
    answer?: (question: string) => Response;
    startStatus?: number;
    /** Decides each Draft save's response instead of accepting it. */
    saveDraft?: (draft: Draft) => Response | undefined | Promise<Response | undefined>;
    credentials?: Credential[];
    tags?: Tag[];
  } = {},
) {
  let agents = [...(options.agents ?? [])];
  const requests: { route: string; body?: unknown }[] = [];
  const answer = options.answer ?? (() => streamedAnswer(["Twenty-five ", "days."]));
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/agents", () => HttpResponse.json(agents)),
    http.post("*/api/organisations/:organisationId/projects/:projectId/agents", async ({ request, params }) => {
      const body = (await request.json()) as Schemas["CreateAgentRequest"];
      requests.push({ route: "create", body });
      if (body.name.length > 10) return HttpResponse.json({ detail: [] }, { status: 422 });
      const created: Agent = {
        ...hrHelper,
        id: `a9e00000-0000-4000-8000-0000000001${String(agents.length).padStart(2, "0")}`,
        project_id: params.projectId as string,
        name: body.name,
        draft: defaultDraft,
      };
      agents.push(created);
      return HttpResponse.json(created, { status: 201 });
    }),
    http.get("*/api/organisations/:organisationId/projects/:projectId/agents/:agentId", ({ params }) => {
      const agent = agents.find((candidate) => candidate.id === params.agentId);
      return agent ? HttpResponse.json(agent) : HttpResponse.json({ detail: "Not found" }, { status: 404 });
    }),
    http.put("*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/draft", async ({ request, params }) => {
      const body = (await request.json()) as Draft;
      requests.push({ route: "draft", body });
      const refused = await options.saveDraft?.(body);
      if (refused) return refused;
      const agent = { ...(agents.find((candidate) => candidate.id === params.agentId) as Agent), draft: body };
      agents = agents.map((candidate) => (candidate.id === agent.id ? agent : candidate));
      return HttpResponse.json(agent);
    }),
    http.get("*/api/organisations/:organisationId/credentials", () => HttpResponse.json(options.credentials ?? [openAi, claude, voyage])),
    http.get("*/api/organisations/:organisationId/credentials/:credentialId/models/:capability", ({ params }) => {
      const offered = offeredModels[`${params.credentialId as string}/${params.capability as string}`];
      return offered ? HttpResponse.json(offered) : HttpResponse.json({ detail: "Not found" }, { status: 404 });
    }),
    http.get("*/api/organisations/:organisationId/projects/:projectId/tags", () => HttpResponse.json(options.tags ?? [hrTag, payTag])),
    http.post("*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/playground/conversations", ({ params }) => {
      requests.push({ route: "start" });
      if (options.startStatus) return HttpResponse.json({ detail: "This Project is archived. An Owner can restore it." }, { status: options.startStatus });
      return HttpResponse.json(
        {
          id: CONVERSATION_ID,
          agent_id: params.agentId as string,
          is_playground: true,
          created_at: "2026-11-05T09:00:00Z",
          last_activity_at: "2026-11-05T09:00:00Z",
          messages: [],
        },
        { status: 201 },
      );
    }),
    http.post(
      "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/playground/conversations/:conversationId/messages",
      async ({ request, params }) => {
        const body = (await request.json()) as { content: string };
        requests.push({ route: "ask", body: { ...body, conversationId: params.conversationId } });
        return answer(body.content);
      },
    ),
  );
  return { requests };
}
