import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { server } from "./server";

type Suggestion = Schemas["SuggestionOut"];
type Evidence = Schemas["EvidenceOut"];

export const failedReply: Evidence = {
  id: "5e000000-0000-4000-8000-000000000001",
  label: "E1",
  kind: "live_verdict",
  kinds: ["live_verdict"],
  occurred_at: "2026-11-14T10:00:00Z",
  conversation_id: "c0000000-0000-4000-8000-000000000011",
  message_id: "3e000000-0000-4000-8000-000000000011",
  live_verdict: "fail",
  text_purged: false,
  evaluation_run_id: null,
  run_case_id: null,
  case_deleted: false,
};

export const purgedReply: Evidence = {
  ...failedReply,
  id: "5e000000-0000-4000-8000-000000000002",
  label: "E2",
  conversation_id: "c0000000-0000-4000-8000-000000000012",
  message_id: "3e000000-0000-4000-8000-000000000012",
  occurred_at: "2026-11-03T08:00:00Z",
  text_purged: true,
};

/** A reply that failed its Live Verdict, has a thumbs-down and is in a Conversation rated 1 or 2. */
export const unhappyReply: Evidence = {
  ...failedReply,
  id: "5e000000-0000-4000-8000-000000000003",
  label: "E3",
  kind: "live_verdict",
  kinds: ["live_verdict", "thumbs_down", "low_rating"],
  conversation_id: "c0000000-0000-4000-8000-000000000013",
  message_id: "3e000000-0000-4000-8000-000000000013",
  occurred_at: "2026-11-12T08:00:00Z",
};

/** An Evaluation Case that failed on the Live Version, and one whose case was since deleted. */
export const failedCase: Evidence = {
  id: "5e000000-0000-4000-8000-000000000004",
  label: "E4",
  kind: "evaluation_case",
  kinds: ["evaluation_case"],
  occurred_at: "2026-11-10T12:00:00Z",
  conversation_id: null,
  message_id: null,
  live_verdict: null,
  text_purged: false,
  evaluation_run_id: "e1000000-0000-4000-8000-000000000001",
  run_case_id: "e2000000-0000-4000-8000-000000000001",
  case_deleted: false,
};

export const deletedCase: Evidence = {
  ...failedCase,
  id: "5e000000-0000-4000-8000-000000000005",
  label: "E5",
  run_case_id: "e2000000-0000-4000-8000-000000000002",
  case_deleted: true,
};

/** A Suggestion of the HR helper's Version 1, at a status. */
export function suggestion(id: string, status: Suggestion["status"], overrides: Partial<Suggestion> = {}): Suggestion {
  const finished = status === "completed" || status === "failed";
  return {
    id,
    status,
    range_start: "2026-11-03",
    range_end: "2026-11-16",
    base_version_id: "a1e00000-0000-4000-8000-000000000001",
    base_version_number: 1,
    outcome: null,
    evidence_total: 0,
    error_message: null,
    created_at: "2026-11-16T09:00:00Z",
    finished_at: finished ? "2026-11-16T09:01:00Z" : null,
    explanation: null,
    model_provider: "openai",
    model_name: "gpt-4.1-mini",
    changes: [],
    gaps: [],
    evidence: [],
    ...overrides,
  };
}

/** A finished Suggestion adding a line to the system prompt, from a failed and a purged reply. */
export const citingSuggestion = suggestion("5a000000-0000-4000-8000-000000000001", "completed", {
  outcome: "changes",
  evidence_total: 3,
  explanation: "Replies made claims without citing the handbook.",
  changes: [
    {
      id: "5c000000-0000-4000-8000-000000000001",
      path: "behaviour.system_prompt",
      base_value: "Answer from the handbook.",
      suggested_value: "Answer from the handbook.\nAlways cite the passage you used.",
      explanation: "Replies failed grounding, so ask for citations.",
      evidence_ids: [failedReply.id],
    },
  ],
  evidence: [failedReply, purgedReply],
});

/** A finished Suggestion from every kind of evidence: a retrieval change and a Knowledge Base gap. */
export const retrievalSuggestion = suggestion("5a000000-0000-4000-8000-000000000004", "completed", {
  outcome: "changes",
  evidence_total: 3,
  explanation: "The right passages were excluded just under the Minimum Score.",
  changes: [
    {
      id: "5c000000-0000-4000-8000-000000000002",
      path: "retrieval.minimum_score",
      base_value: 0.5,
      suggested_value: 0.45,
      explanation: "Chunks were excluded just under the Minimum Score.",
      evidence_ids: [unhappyReply.id, failedCase.id],
    },
  ],
  gaps: [
    {
      id: "5d000000-0000-4000-8000-000000000001",
      topic: "Parental leave",
      explanation: "Visitors asked about parental leave and no Chunk covered it.",
      evidence_ids: [deletedCase.id],
    },
  ],
  evidence: [unhappyReply, failedCase, deletedCase],
});

const SUMMARY_FIELDS = [
  "id",
  "status",
  "range_start",
  "range_end",
  "base_version_id",
  "base_version_number",
  "outcome",
  "evidence_total",
  "error_message",
  "created_at",
  "finished_at",
] as const;

const summary = (found: Suggestion): Schemas["SuggestionSummaryOut"] =>
  Object.fromEntries(SUMMARY_FIELDS.map((key) => [key, found[key]])) as Schemas["SuggestionSummaryOut"];

/**
 * The Suggestions API: each Suggestion's states, one per read (the last repeats). Starting returns
 * the `started` states' first and lists it first.
 */
export function fakeSuggestionsApi(
  options: {
    suggestions?: Suggestion[][];
    started?: Suggestion[];
    startStatus?: number;
    startDetail?: string;
    failList?: boolean;
    failRead?: boolean;
  } = {},
) {
  const requests: unknown[] = [];
  const entries = (options.suggestions ?? []).map((states) => ({ states, read: 0 }));
  const current = (entry: { states: Suggestion[]; read: number }) =>
    entry.states[Math.min(entry.read, entry.states.length - 1)] as Suggestion;
  const base = "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/suggestions";

  server.use(
    http.get(base, () => {
      if (options.failList) return HttpResponse.json({ detail: "Down" }, { status: 500 });
      return HttpResponse.json(entries.map((entry) => summary(current(entry))));
    }),
    http.get(`${base}/:suggestionId`, ({ params }) => {
      const entry = entries.find((each) => current(each).id === params.suggestionId);
      if (options.failRead || entry === undefined) return HttpResponse.json({ detail: "Not found" }, { status: 404 });
      const found = current(entry);
      entry.read += 1;
      return HttpResponse.json(found);
    }),
    http.post(base, async ({ request }) => {
      requests.push(await request.json());
      if (options.startStatus) {
        return HttpResponse.json({ detail: options.startDetail }, { status: options.startStatus });
      }
      const states = options.started ?? [];
      entries.unshift({ states, read: 0 });
      return HttpResponse.json(states[0], { status: 202 });
    }),
  );
  return { requests };
}
