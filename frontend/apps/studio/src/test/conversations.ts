import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { agentVersion, hrHelper, hrTrace, ranWithDraft } from "./agents";
import { server } from "./server";

type Summary = Schemas["ConversationSummaryOut"];
type Detail = Schemas["ConversationDetailOut"];
type Message = Schemas["ConversationMessageOut"];
type Trace = Schemas["TraceOut"];

export const VISITOR_CONVERSATION_ID = "c7000000-0000-4000-8000-000000000001";
export const PLAYGROUND_CONVERSATION_ID = "c7000000-0000-4000-8000-000000000002";
export const VISITOR_REPLY_ID = "e7000000-0000-4000-8000-000000000002";
export const PLAYGROUND_REPLY_ID = "e7000000-0000-4000-8000-000000000012";

/** A Visitor's Conversation with HR helper: v1 answered, then v2 after it went live. */
export const visitorConversation: Summary = {
  id: VISITOR_CONVERSATION_ID,
  agent_id: hrHelper.id,
  agent_name: "HR helper",
  is_playground: false,
  created_at: "2026-11-06T10:15:00Z",
  last_activity_at: "2026-11-06T10:20:00Z",
  message_count: 4,
  preview: "How much leave do I get?",
  version_numbers: [1, 2],
  thumbs_up: 1,
  thumbs_down: 1,
  rating: 4,
};

/** An Editor trying HR helper's Draft in the Playground. */
export const playgroundConversation: Summary = {
  id: PLAYGROUND_CONVERSATION_ID,
  agent_id: hrHelper.id,
  agent_name: "HR helper",
  is_playground: true,
  created_at: "2026-11-07T08:00:00Z",
  last_activity_at: "2026-11-07T08:01:00Z",
  message_count: 2,
  preview: "Testing leave",
  version_numbers: [],
  thumbs_up: 0,
  thumbs_down: 0,
  rating: null,
};

const unanswered = {
  config_source: null,
  instructions_source: null,
  instructions_version_id: null,
  instructions_version_number: null,
  agent_version_id: null,
  agent_version_number: null,
  model_provider: null,
  model_name: null,
  input_tokens: null,
  output_tokens: null,
  first_token_ms: null,
  latency_ms: null,
  cost_usd: null,
  fallback: false,
  feedback: null,
};

function question(id: string, content: string, created_at: string): Message {
  return { id, role: "user", content, created_at, ...unanswered };
}

function reply(id: string, content: string, created_at: string, version: number | null): Message {
  return {
    ...unanswered,
    id,
    role: "assistant",
    content,
    created_at,
    model_provider: "openai",
    model_name: "gpt-4.1-mini",
    input_tokens: 120,
    output_tokens: 6,
    first_token_ms: 40,
    latency_ms: 85,
    cost_usd: "0.000057600",
    ...(version === null
      ? { config_source: "draft", ...ranWithDraft }
      : { config_source: "version", agent_version_id: agentVersion(version).id, agent_version_number: version }),
  };
}

export const visitorDetail: Detail = {
  id: VISITOR_CONVERSATION_ID,
  agent_id: hrHelper.id,
  agent_name: "HR helper",
  is_playground: false,
  created_at: visitorConversation.created_at,
  last_activity_at: visitorConversation.last_activity_at,
  messages: [
    question("e7000000-0000-4000-8000-000000000001", "How much leave do I get?", "2026-11-06T10:15:00Z"),
    {
      ...reply(VISITOR_REPLY_ID, "Twenty-five days.", "2026-11-06T10:15:02Z", 1),
      feedback: { rating: "up", comment: null, agent_version_number: 1, updated_at: "2026-11-06T10:16:00Z" },
    },
    question("e7000000-0000-4000-8000-000000000003", "And part-time?", "2026-11-06T10:19:00Z"),
    {
      ...reply("e7000000-0000-4000-8000-000000000004", "Sorry, I don't know the answer to that.", "2026-11-06T10:19:01Z", 2),
      fallback: true,
      feedback: {
        rating: "down",
        comment: "It should know part-time leave.",
        agent_version_number: 2,
        updated_at: "2026-11-06T10:21:00Z",
      },
    },
  ],
  // Rated 2 after v1's reply, dismissed the prompt, then changed it to 4 after v2's.
  rating: {
    score: 4,
    agent_version_number: 2,
    rated_at: "2026-11-06T10:22:00Z",
    prompt_dismissed_at: "2026-11-06T10:17:00Z",
    changes: [
      { score: 2, previous_score: null, agent_version_number: 1, changed_at: "2026-11-06T10:16:30Z" },
      { score: 4, previous_score: 2, agent_version_number: 2, changed_at: "2026-11-06T10:22:00Z" },
    ],
  },
};

export const playgroundDetail: Detail = {
  ...visitorDetail,
  id: PLAYGROUND_CONVERSATION_ID,
  is_playground: true,
  created_at: playgroundConversation.created_at,
  last_activity_at: playgroundConversation.last_activity_at,
  messages: [
    question("e7000000-0000-4000-8000-000000000011", "Testing leave", "2026-11-07T08:00:00Z"),
    reply(PLAYGROUND_REPLY_ID, "Twenty-five days.", "2026-11-07T08:00:02Z", null),
  ],
  rating: null,
};

/** The Trace of the Visitor's first reply: answered by Agent Version v1. */
export const visitorTrace: Trace = {
  ...hrTrace,
  message_id: VISITOR_REPLY_ID,
  config_source: "version",
  agent_version_id: agentVersion(1).id,
  agent_version_number: 1,
  instructions_source: null,
  instructions_version_id: null,
  instructions_version_number: null,
};

/**
 * Serves the Conversations viewer's routes from these Conversations. The list keeps those of the
 * Agent asked for and the Playground, feedback and rating filters, like the API; other filters are only
 * recorded. Every
 * list query is recorded, as are Trace reads.
 */
export function fakeConversationsApi(
  options: {
    conversations?: Summary[];
    details?: Detail[];
    traces?: Trace[];
    /** Answers every list request with this status instead. */
    listStatus?: number;
    /** The total the list reports, when more than the items given (paging). */
    total?: number;
  } = {},
) {
  const conversations = options.conversations ?? [playgroundConversation, visitorConversation];
  const details = options.details ?? [visitorDetail, playgroundDetail];
  const traces = options.traces ?? [visitorTrace, { ...hrTrace, message_id: PLAYGROUND_REPLY_ID, agent_version_number: null }];
  const queries: URLSearchParams[] = [];
  const traceReads: string[] = [];
  const notFound = () => HttpResponse.json({ detail: "Not found" }, { status: 404 });
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/conversations", ({ request }) => {
      const query = new URL(request.url).searchParams;
      queries.push(query);
      if (options.listStatus) return HttpResponse.json({ detail: "Not found" }, { status: options.listStatus });
      const agentId = query.get("agent_id");
      const playground = query.get("playground");
      const feedback = query.get("feedback");
      const rating = query.get("rating");
      const rated = ({ rating: score }: Summary) => {
        if (rating === null) return true;
        if (rating === "any") return score !== null;
        if (rating === "none") return score === null;
        return String(score) === rating;
      };
      const given = (conversation: Summary) => {
        const { thumbs_up: up, thumbs_down: down } = conversation;
        if (feedback === "up") return up > 0;
        if (feedback === "down") return down > 0;
        if (feedback === "any") return up + down > 0;
        return feedback === null || up + down === 0;
      };
      const items = conversations.filter(
        (conversation) =>
          (agentId === null || conversation.agent_id === agentId) &&
          (playground === null || String(conversation.is_playground) === playground) &&
          given(conversation) &&
          rated(conversation),
      );
      return HttpResponse.json({
        items,
        page: Number(query.get("page") ?? 1),
        page_size: Number(query.get("page_size") ?? 25),
        total: options.total ?? items.length,
      });
    }),
    http.get("*/api/organisations/:organisationId/projects/:projectId/conversations/:conversationId", ({ params }) => {
      const found = details.find((detail) => detail.id === params.conversationId);
      return found ? HttpResponse.json(found) : notFound();
    }),
    http.get(
      "*/api/organisations/:organisationId/projects/:projectId/conversations/:conversationId/messages/:messageId/trace",
      ({ params }) => {
        traceReads.push(`${String(params.conversationId)}/${String(params.messageId)}`);
        const found = traces.find((trace) => trace.message_id === params.messageId);
        return found ? HttpResponse.json(found) : notFound();
      },
    ),
  );
  return { queries, traceReads };
}
