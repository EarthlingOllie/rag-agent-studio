import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { server } from "./server";

type Suggestion = Schemas["SuggestionOut"];
type Evidence = Schemas["EvidenceOut"];

export const failedReply: Evidence = {
  id: "5e000000-0000-4000-8000-000000000001",
  label: "E1",
  kind: "live_verdict",
  conversation_id: "c0000000-0000-4000-8000-000000000011",
  message_id: "3e000000-0000-4000-8000-000000000011",
  replied_at: "2026-11-14T10:00:00Z",
  live_verdict: "fail",
  text_purged: false,
};

export const purgedReply: Evidence = {
  ...failedReply,
  id: "5e000000-0000-4000-8000-000000000002",
  label: "E2",
  conversation_id: "c0000000-0000-4000-8000-000000000012",
  message_id: "3e000000-0000-4000-8000-000000000012",
  replied_at: "2026-11-03T08:00:00Z",
  text_purged: true,
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
