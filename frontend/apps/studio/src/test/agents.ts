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
  retrieval: {
    top_k: 5,
    hybrid_weight: 0.5,
    min_score: 0,
    tag_ids: [],
    reranker: null,
    citations: true,
  },
  experience: {
    display_name: "",
    avatar_url: null,
    greeting: "",
    starter_questions: [],
    ui_text: {
      send_button: null,
      rate_conversation: null,
      unavailable_message: null,
    },
    rating_prompt_after: 3,
  },
  guardrails: {
    input_mode: "block",
    classifier: null,
    fail_mode: "closed",
    refusal_text: "Sorry, I can't help with that request.",
  },
};

const credential = (
  id: string,
  name: string,
  provider: Credential["provider"],
  capabilities: Credential["capabilities"],
): Credential => ({
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

export const openAi = credential(
  "c1000000-0000-4000-8000-000000000001",
  "OpenAI",
  "openai",
  ["chat", "embeddings"],
);
export const claude = credential(
  "c1000000-0000-4000-8000-000000000002",
  "Claude",
  "anthropic",
  ["chat"],
);
export const voyage = credential(
  "c1000000-0000-4000-8000-000000000003",
  "Voyage",
  "voyage",
  ["embeddings", "rerank"],
);

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

export const hrTag: Tag = {
  id: "d1000000-0000-4000-8000-000000000001",
  name: "HR",
  document_count: 2,
  agents: [],
  created_at: "2026-11-05T09:00:00Z",
};
export const payTag: Tag = {
  id: "d1000000-0000-4000-8000-000000000002",
  name: "Pay",
  document_count: 1,
  agents: [],
  created_at: "2026-11-05T09:00:00Z",
};

export const hrHelper: Agent = {
  id: "a9e00000-0000-4000-8000-000000000001",
  public_id: "agt_abcdefghijklmnopqrstuvwx",
  project_id: "7c2d1e69-1e7f-4d2c-8e2f-2a2b7d1a0b01",
  name: "HR helper",
  created_at: "2026-11-05T09:00:00Z",
  archived_at: null,
  draft: {
    ...defaultDraft,
    behaviour: {
      ...defaultDraft.behaviour,
      system_prompt: "Answer from the handbook.",
    },
  },
  draft_updated_at: "2026-11-05T09:00:00Z",
  live_version: null,
};

/** An archived Agent of the same Project. */
export const oldHelper: Agent = {
  ...hrHelper,
  id: "a9e00000-0000-4000-8000-000000000003",
  public_id: "agt_zyxwvutsrqponmlkjihgfedc",
  name: "Old helper",
  archived_at: "2026-11-06T08:00:00Z",
};

export const CONVERSATION_ID = "c0000000-0000-4000-8000-000000000001";
/** The Conversation a reset starts: each later start gets the next ID. */
export const RESET_CONVERSATION_ID = "c0000000-0000-4000-8000-000000000002";

/** What a `done` event says an answer ran with: the Instructions Draft, or a Version. */
export type InstructionsUsed = {
  instructions_source: "draft" | "version";
  instructions_version_id: string | null;
  instructions_version_number: number | null;
};

export const ranWithDraft: InstructionsUsed = {
  instructions_source: "draft",
  instructions_version_id: null,
  instructions_version_number: null,
};

/** What an answer asked with this Version ID ran with. The fake Versions' IDs end in their
 * number (see `instructionsVersion` in ./projects). */
function ranWith(versionId: string | null | undefined): InstructionsUsed {
  if (!versionId) return ranWithDraft;
  return {
    instructions_source: "version",
    instructions_version_id: versionId,
    instructions_version_number: Number(versionId.slice(-12)),
  };
}

const done = {
  message_id: "e0000000-0000-4000-8000-000000000001",
  ...ranWithDraft,
  input_tokens: 120,
  output_tokens: 6,
  first_token_ms: 40,
  latency_ms: 85,
  fallback: false,
  chunks: [
    {
      chunk_id: "f0000000-0000-4000-8000-000000000001",
      score: 0.92,
      relevance: 0.81,
      rank: 1,
    },
  ],
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
  agent_version_id: null,
  ...ranWithDraft,
  model_provider: "openai",
  model_name: "gpt-4.1-mini",
  input_tokens: 120,
  output_tokens: 6,
  cost_usd: "0.000057600",
  first_token_ms: 40,
  latency_ms: 85,
  fallback: false,
  guardrail_outcomes: [],
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
    {
      chunk_id: "f0000000-0000-4000-8000-000000000005",
      document_id: "d0000000-0000-4000-8000-000000000005",
      document_name: "price-list.md",
      text: "Model SKU-4471 ships with a two-year warranty.",
      score: 0.15,
      relevance: 0.6,
      rank: null,
      cited: false,
      excluded_reason: "outside_tags",
    },
  ],
};

function sse(event: string, data: unknown) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** A Server-Sent Events body that arrives in pieces, splitting events across reads. */
export function streamedAnswer(
  tokens: string[],
  options: {
    end?: boolean;
    citations?: (typeof leaveCitation)[];
    replace?: string;
    /** Ends the stream with a provider `error` event instead of `done`. */
    error?: { code: string; message: string };
    /** What the `done` event says the answer ran with; the Instructions Draft by default. */
    instructions?: InstructionsUsed;
  } = {},
) {
  const body =
    tokens.map((text) => sse("token", { text })).join("") +
    (options.replace === undefined
      ? ""
      : sse("replace", { text: options.replace })) +
    (options.citations ?? [])
      .map((citation) => sse("citation", citation))
      .join("") +
    (options.error ? sse("error", options.error) : "") +
    (options.end === false || options.error
      ? ""
      : sse("done", { ...done, ...options.instructions }));
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
    answer?: (
      question: string,
      instructionsVersionId: string | null,
    ) => Response | Promise<Response>;
    startStatus?: number;
    startDetail?: string;
    /** Decides the status of each start after the first (a reset) instead of 201. */
    restartStatus?: number;
    trace?: () => Response;
    /** Decides each Draft save's response instead of accepting it. */
    saveDraft?: (
      draft: Draft,
    ) => Response | undefined | Promise<Response | undefined>;
    credentials?: Credential[];
    tags?: Tag[];
    /** Refuses `archive` or `restore` with a 409 carrying this detail. */
    refuse?: Record<string, string>;
    /** The Project's Current Instructions Version, which a publish pins by default. */
    currentInstructions?: { id: string; number: number } | null;
    /** Decides each publish's response instead of accepting it. */
    publish?: (
      body: Schemas["PublishAgentRequest"],
    ) => Response | undefined | Promise<Response | undefined>;
    /** The Allowed Origins every Agent starts with. */
    allowedOrigins?: string[];
    /** Each Agent's Live History, newest first; empty when left out. */
    liveHistory?: Record<string, Schemas["LiveHistoryEntryOut"][]>;
    /** Answers each Live History read instead of the stored history. */
    liveHistoryResponse?: () => Response | undefined;
    /** Decides each revert's response instead of following the Live History. */
    revert?: () => Response | undefined | Promise<Response | undefined>;
  } = {},
) {
  let agents = [...(options.agents ?? [])];
  const requests: { route: string; body?: unknown }[] = [];
  // By default the answer runs with the Instructions it was asked with.
  const answer =
    options.answer ??
    ((_question: string, instructionsVersionId: string | null) =>
      streamedAnswer(["Twenty-five ", "days."], {
        instructions: ranWith(instructionsVersionId),
      }));
  const published: Record<string, number> = {};
  const history: Record<string, Schemas["LiveHistoryEntryOut"][]> = {
    ...options.liveHistory,
  };
  const ada = { id: "6a1b0c58-0d6e-4c1b-9d1e-1f1a6c0f0a01", name: "Ada Lovelace" };
  const versionId = (number: number) =>
    `a1e00000-0000-4000-8000-${String(number).padStart(12, "0")}`;
  let allowedOrigins = [...(options.allowedOrigins ?? [])];
  server.use(
    http.get(
      "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/allowed-origins",
      () => HttpResponse.json({ origins: allowedOrigins }),
    ),
    http.put(
      "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/allowed-origins",
      async ({ request }) => {
        const body = (await request.json()) as Schemas["AllowedOriginsIn"];
        requests.push({ route: "allowed-origins", body });
        // Like the API: lower-cased, without a trailing slash; a non-origin is a 422.
        const origins = body.origins.map((origin) =>
          origin.trim().toLowerCase().replace(/\/$/, ""),
        );
        const invalid = origins.findIndex(
          (origin) => !/^https?:\/\/[a-z0-9.-]+(:[0-9]+)?$/.test(origin),
        );
        if (invalid >= 0)
          return HttpResponse.json(
            {
              detail: [
                {
                  loc: ["body", "origins", invalid],
                  msg: `'${String(body.origins[invalid])}' isn't a site address. Use a scheme, host and optional port, such as https://www.example.com or http://localhost:8080.`,
                  type: "value_error",
                },
              ],
            },
            { status: 422 },
          );
        allowedOrigins = origins;
        return HttpResponse.json({ origins });
      },
    ),
    http.get(
      "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/live-history",
      ({ params }) =>
        options.liveHistoryResponse?.() ??
        HttpResponse.json(history[params.agentId as string] ?? []),
    ),
    http.post(
      "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/revert",
      async ({ params }) => {
        requests.push({ route: "revert" });
        const refused = await options.revert?.();
        if (refused) return refused;
        const agent = agents.find(
          (candidate) => candidate.id === params.agentId,
        ) as Agent;
        const entries = history[agent.id] ?? [];
        const live = agent.live_version as { id: string; number: number };
        // The same rule as the API: back to the Version Live when this one was published.
        const target = entries.find(
          (entry) =>
            entry.to_version.id === live.id &&
            entry.action.endsWith("publish"),
        )?.from_version;
        if (!target)
          return HttpResponse.json(
            { detail: "There's no earlier Live Version to revert to." },
            { status: 409 },
          );
        history[agent.id] = [
          {
            from_version: live,
            to_version: target,
            action: "revert",
            actor: ada,
            occurred_at: "2026-11-06T12:00:00Z",
            bulk_operation_id: null,
          },
          ...entries,
        ];
        agents = agents.map((candidate) =>
          candidate.id === agent.id
            ? { ...agent, live_version: target }
            : candidate,
        );
        const version: Schemas["AgentVersionOut"] = {
          ...target,
          note: `Release ${String(target.number)}`,
          author: ada,
          created_at: "2026-11-06T11:00:00Z",
          config: agent.draft,
          instructions_version: options.currentInstructions ?? null,
        };
        return HttpResponse.json(version);
      },
    ),
    http.post(
      "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/versions",
      async ({ request, params }) => {
        const body = (await request.json()) as Schemas["PublishAgentRequest"];
        requests.push({ route: "publish", body });
        const refused = await options.publish?.(body);
        if (refused) return refused;
        const agent = agents.find(
          (candidate) => candidate.id === params.agentId,
        ) as Agent;
        const number =
          (published[agent.id] ?? agent.live_version?.number ?? 0) + 1;
        published[agent.id] = number;
        const version: Schemas["AgentVersionOut"] = {
          id: versionId(number),
          number,
          note: body.note.trim(),
          author: ada,
          created_at: "2026-11-06T11:00:00Z",
          config: agent.draft,
          // Instructions Version IDs end in their number (see `instructionsVersion`).
          instructions_version: body.instructions_version_id
            ? {
                id: body.instructions_version_id,
                number: Number(body.instructions_version_id.slice(-12)),
              }
            : (options.currentInstructions ?? null),
        };
        history[agent.id] = [
          {
            from_version: agent.live_version,
            to_version: { id: version.id, number },
            action: "publish",
            actor: ada,
            occurred_at: "2026-11-06T11:00:00Z",
            bulk_operation_id: null,
          },
          ...(history[agent.id] ?? []),
        ];
        agents = agents.map((candidate) =>
          candidate.id === agent.id
            ? { ...agent, live_version: { id: version.id, number } }
            : candidate,
        );
        return HttpResponse.json(version, { status: 201 });
      },
    ),
    http.get(
      "*/api/organisations/:organisationId/projects/:projectId/agents",
      ({ request }) => {
        const archived =
          new URL(request.url).searchParams.get("archived") === "true";
        return HttpResponse.json(
          agents.filter(
            (agent) => (agent.archived_at !== null) === archived,
          ),
        );
      },
    ),
    http.post(
      "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/:action",
      ({ params }) => {
        const action = params.action as string;
        requests.push({ route: action });
        const agent = agents.find(
          (candidate) => candidate.id === params.agentId,
        ) as Agent;
        if (options.refuse?.[action])
          return HttpResponse.json(
            { detail: options.refuse[action] },
            { status: 409 },
          );
        const changed: Agent = {
          ...agent,
          archived_at: action === "archive" ? "2026-11-06T09:00:00Z" : null,
        };
        agents = agents.map((candidate) =>
          candidate.id === changed.id ? changed : candidate,
        );
        return HttpResponse.json(changed);
      },
    ),
    http.delete(
      "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId",
      async ({ request, params }) => {
        const body = (await request.json()) as Schemas["DeleteAgentRequest"];
        requests.push({ route: "delete", body });
        const agent = agents.find(
          (candidate) => candidate.id === params.agentId,
        ) as Agent;
        if (body.confirm_name !== agent.name)
          return HttpResponse.json(
            { detail: "Type the Agent's name exactly to delete it." },
            { status: 400 },
          );
        agents = agents.filter((candidate) => candidate.id !== agent.id);
        return new HttpResponse(null, { status: 204 });
      },
    ),
    http.post(
      "*/api/organisations/:organisationId/projects/:projectId/agents",
      async ({ request, params }) => {
        const body = (await request.json()) as Schemas["CreateAgentRequest"];
        requests.push({ route: "create", body });
        if (body.name.length > 10)
          return HttpResponse.json({ detail: [] }, { status: 422 });
        const created: Agent = {
          ...hrHelper,
          id: `a9e00000-0000-4000-8000-0000000001${String(agents.length).padStart(2, "0")}`,
          project_id: params.projectId as string,
          name: body.name,
          draft: defaultDraft,
        };
        agents.push(created);
        return HttpResponse.json(created, { status: 201 });
      },
    ),
    http.get(
      "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId",
      ({ params }) => {
        const agent = agents.find(
          (candidate) => candidate.id === params.agentId,
        );
        return agent
          ? HttpResponse.json(agent)
          : HttpResponse.json({ detail: "Not found" }, { status: 404 });
      },
    ),
    http.put(
      "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/draft",
      async ({ request, params }) => {
        const body = (await request.json()) as Draft;
        requests.push({ route: "draft", body });
        const refused = await options.saveDraft?.(body);
        if (refused) return refused;
        const agent = {
          ...(agents.find(
            (candidate) => candidate.id === params.agentId,
          ) as Agent),
          draft: body,
        };
        agents = agents.map((candidate) =>
          candidate.id === agent.id ? agent : candidate,
        );
        return HttpResponse.json(agent);
      },
    ),
    http.get("*/api/organisations/:organisationId/credentials", () =>
      HttpResponse.json(options.credentials ?? [openAi, claude, voyage]),
    ),
    http.get(
      "*/api/organisations/:organisationId/credentials/:credentialId/models/:capability",
      ({ params }) => {
        const offered =
          offeredModels[
            `${params.credentialId as string}/${params.capability as string}`
          ];
        return offered
          ? HttpResponse.json(offered)
          : HttpResponse.json({ detail: "Not found" }, { status: 404 });
      },
    ),
    http.get(
      "*/api/organisations/:organisationId/projects/:projectId/tags",
      () => HttpResponse.json(options.tags ?? [hrTag, payTag]),
    ),
    http.post(
      "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/playground/conversations",
      ({ params }) => {
        const starts = requests.filter(
          (request) => request.route === "start",
        ).length;
        requests.push({ route: "start" });
        if (starts > 0 && options.restartStatus)
          return HttpResponse.json(
            { detail: "This Agent is archived." },
            { status: options.restartStatus },
          );
        if (options.startStatus)
          return HttpResponse.json(
            {
              detail:
                options.startDetail ??
                "This Project is archived. An Owner can restore it.",
            },
            { status: options.startStatus },
          );
        return HttpResponse.json(
          {
            id: `c0000000-0000-4000-8000-00000000000${String(starts + 1)}`,
            agent_id: params.agentId as string,
            is_playground: true,
            created_at: "2026-11-05T09:00:00Z",
            last_activity_at: "2026-11-05T09:00:00Z",
            messages: [],
          },
          { status: 201 },
        );
      },
    ),
    http.post(
      "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/playground/conversations/:conversationId/messages",
      async ({ request, params }) => {
        const body =
          (await request.json()) as Schemas["SendMessageRequest"];
        requests.push({
          route: "ask",
          body: { ...body, conversationId: params.conversationId },
        });
        return answer(body.content, body.instructions_version_id ?? null);
      },
    ),
    http.get(
      "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/playground/conversations/:conversationId/messages/:messageId/trace",
      ({ params }) => {
        requests.push({
          route: "trace",
          body: {
            conversationId: params.conversationId,
            messageId: params.messageId,
          },
        });
        return options.trace ? options.trace() : HttpResponse.json(hrTrace);
      },
    ),
  );
  return { requests };
}
