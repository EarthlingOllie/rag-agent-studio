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
  draft: { behaviour: { system_prompt: "Answer from the handbook." }, retrieval: { top_k: 5 } },
  draft_updated_at: "2026-11-05T09:00:00Z",
};

export const CONVERSATION_ID = "c0000000-0000-4000-8000-000000000001";

const done = {
  message_id: "e0000000-0000-4000-8000-000000000001",
  input_tokens: 120,
  output_tokens: 6,
  first_token_ms: 40,
  latency_ms: 85,
  chunks: [{ chunk_id: "f0000000-0000-4000-8000-000000000001", score: 0.92, rank: 1 }],
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
  options: { agents?: Agent[]; answer?: (question: string) => Response; startStatus?: number } = {},
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
        draft: { behaviour: { system_prompt: "" }, retrieval: { top_k: 5 } },
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
  );
  return { requests };
}
