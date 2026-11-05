import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { server } from "./server";

export type Agent = Schemas["AgentOut"];

export const hrHelper: Agent = {
  id: "a9e00000-0000-4000-8000-000000000001",
  public_id: "agt_abcdefghijklmnopqrstuvwx",
  project_id: "7c2d1e69-1e7f-4d2c-8e2f-2a2b7d1a0b01",
  name: "HR helper",
  created_at: "2026-11-05T09:00:00Z",
  archived_at: null,
  draft: {
    behaviour: { system_prompt: "Answer from the handbook.", fallback_text: "Ask HR, please." },
    retrieval: { top_k: 5, hybrid_weight: 0.7, min_score: 0.25 },
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

export const leaveCitation = {
  label: "C1",
  chunk_id: "f0000000-0000-4000-8000-000000000001",
  document_id: "d0000000-0000-4000-8000-000000000001",
  document_name: "leave-policy.md",
  rank: 1,
};

export const hrTrace: Schemas["TraceOut"] = {
  message_id: done.message_id,
  config_source: "draft",
  model_provider: "openai",
  model_name: "gpt-4.1-mini",
  input_tokens: 120,
  output_tokens: 6,
  cost_usd: "0.000057600",
  first_token_ms: 40,
  latency_ms: 85,
  fallback: false,
  chunks: [
    {
      chunk_id: leaveCitation.chunk_id,
      document_id: leaveCitation.document_id,
      document_name: "leave-policy.md",
      text: "Everyone gets 25 days of annual leave a year.",
      score: 0.92,
      relevance: 0.81,
      rank: 1,
      cited: true,
      excluded_reason: null,
    },
    {
      chunk_id: "f0000000-0000-4000-8000-000000000002",
      document_id: "d0000000-0000-4000-8000-000000000002",
      document_name: "expenses.md",
      text: "Claim expenses within 30 days.",
      score: 0.51,
      relevance: 0.4,
      rank: 2,
      cited: false,
      excluded_reason: null,
    },
    {
      chunk_id: "f0000000-0000-4000-8000-000000000003",
      document_id: "d0000000-0000-4000-8000-000000000003",
      document_name: "parking.md",
      text: "Visitors park in the north car park.",
      score: 0.3,
      relevance: 0.1,
      rank: null,
      cited: false,
      excluded_reason: "below_min_score",
    },
    {
      chunk_id: "f0000000-0000-4000-8000-000000000004",
      document_id: "d0000000-0000-4000-8000-000000000004",
      document_name: null,
      text: null,
      score: 0.2,
      relevance: 0.5,
      rank: null,
      cited: false,
      excluded_reason: "outside_top_k",
    },
  ],
};

function sse(event: string, data: unknown) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** A Server-Sent Events body that arrives in pieces, splitting events across reads. */
export function streamedAnswer(tokens: string[], options: { end?: boolean; citations?: (typeof leaveCitation)[] } = {}) {
  const body =
    tokens.map((text) => sse("token", { text })).join("") +
    (options.citations ?? []).map((citation) => sse("citation", citation)).join("") +
    (options.end === false ? "" : sse("done", done));
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
    trace?: () => Response;
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
        draft: {
          behaviour: { system_prompt: "", fallback_text: "Sorry, I don't know the answer to that." },
          retrieval: { top_k: 5, hybrid_weight: 0.5, min_score: 0 },
        },
      };
      agents.push(created);
      return HttpResponse.json(created, { status: 201 });
    }),
    http.get("*/api/organisations/:organisationId/projects/:projectId/agents/:agentId", ({ params }) => {
      const agent = agents.find((candidate) => candidate.id === params.agentId);
      return agent ? HttpResponse.json(agent) : HttpResponse.json({ detail: "Not found" }, { status: 404 });
    }),
    http.put("*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/draft", async ({ request, params }) => {
      const body = (await request.json()) as Agent["draft"];
      requests.push({ route: "draft", body });
      if (body.retrieval.top_k > 20) return HttpResponse.json({ detail: [] }, { status: 422 });
      const agent = { ...(agents.find((candidate) => candidate.id === params.agentId) as Agent), draft: body };
      agents = agents.map((candidate) => (candidate.id === agent.id ? agent : candidate));
      return HttpResponse.json(agent);
    }),
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
    http.get(
      "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/playground/conversations/:conversationId/messages/:messageId/trace",
      ({ params }) => {
        requests.push({ route: "trace", body: { conversationId: params.conversationId, messageId: params.messageId } });
        return options.trace ? options.trace() : HttpResponse.json(hrTrace);
      },
    ),
  );
  return { requests };
}
