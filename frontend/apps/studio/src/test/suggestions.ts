import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { hrHelper } from "./agents";
import { adaSession } from "./auth";
import { server } from "./server";

type Suggestion = Schemas["SuggestionOut"];
type Evidence = Schemas["EvidenceOut"];
type EvidenceCount = Schemas["EvidenceCountOut"];
type Estimate = Schemas["SuggestionEstimateOut"];
type Diff = Schemas["SuggestionDiffOut"];
type Applied = Schemas["AppliedSuggestionOut"];

export const STALE_NOTICE = "This Suggestion was made from v1, which is no longer Live: its check was against the old Live Version.";

/** The Agent a successful apply returns: the HR helper with the suggested system prompt. */
const appliedAgent = {
  ...hrHelper,
  live_version: { id: "a1e00000-0000-4000-8000-000000000001", number: 1 },
  has_unpublished_changes: true,
};

/** The Suggestion against a Draft that hasn't touched any setting it changes, on revision 3. */
export function cleanDiff(found: Suggestion, overrides: Partial<Diff> = {}): Diff {
  return {
    suggestion_id: found.id,
    draft_revision: 3,
    stale: found.stale,
    stale_notice: found.stale ? STALE_NOTICE : null,
    changes: found.changes.map((change) => ({
      id: change.id,
      path: change.path,
      base_value: change.base_value,
      draft_value: change.base_value,
      suggested_value: change.suggested_value,
      state: "clean",
      explanation: change.explanation,
    })),
    clashes: 0,
    ...overrides,
  };
}

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
    cost: {
      estimated_proposing_usd: "0.0028",
      estimated_checking_usd: null,
      proposing_usd: finished ? "0.00056" : null,
      checking_usd: null,
    },
    changes: [],
    gaps: [],
    evidence: [],
    stale: false,
    applied_by: null,
    applied_at: null,
    check: null,
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

/** The check Run of a checked Suggestion. */
export const CHECK_RUN_ID = "e1000000-0000-4000-8000-0000000000c1";

/** The citing Suggestion, checked against the Evaluation Set: one Regression, a warning. */
export const checkedSuggestion: Suggestion = {
  ...citingSuggestion,
  id: "5a000000-0000-4000-8000-000000000006",
  cost: { estimated_proposing_usd: "0.0028", estimated_checking_usd: "0.00448", proposing_usd: "0.00056", checking_usd: "0.0042" },
  check: {
    state: "regressions",
    evaluation_run_id: CHECK_RUN_ID,
    live_score: 1,
    suggestion_score: 0.5,
    regressions: [
      {
        case_id: "ca000000-0000-4000-8000-000000000001",
        question: "How much leave do I get?",
        reasons: [{ kind: "grounding", reason: "The answer cites no passage." }],
      },
    ],
  },
};

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
  "cost",
  "stale",
  "applied_by",
  "applied_at",
] as const;

/** A Suggestion as the list has it: its check without the Regressions. */
function summary(found: Suggestion): Schemas["SuggestionSummaryOut"] {
  const listed = Object.fromEntries(SUMMARY_FIELDS.map((key) => [key, found[key]])) as Schemas["SuggestionSummaryOut"];
  if (found.check === null) return { ...listed, check: null };
  const { state, evaluation_run_id, live_score, suggestion_score } = found.check;
  return { ...listed, check: { state, evaluation_run_id, live_score, suggestion_score } };
}

/** What a range holds, by kind: by default 3 pieces, too few to be more than noise. */
export function evidenceCount(range: { range_start: string; range_end: string }, overrides: Partial<EvidenceCount> = {}): EvidenceCount {
  return {
    ...range,
    total: 3,
    live_verdict: 2,
    thumbs_down: 1,
    low_rating: 1,
    evaluation_case: 0,
    likely_noise: true,
    ...overrides,
  };
}

/** A run's estimate: 3 pieces, checked against an Evaluation Set. */
export function estimateOf(evidence: EvidenceCount, overrides: Partial<Estimate> = {}): Estimate {
  return {
    evidence,
    evidence_used: Math.min(evidence.total, 50),
    proposing_usd: "0.0028",
    has_evaluation_set: true,
    checking_usd: "0.00448",
    total_usd: "0.00728",
    ...overrides,
  };
}

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
    /** The evidence a range holds; by default `evidenceCount`'s. */
    evidence?: (range: { range_start: string; range_end: string }) => EvidenceCount;
    /** The estimate for that evidence; by default `estimateOf`'s. */
    estimate?: (evidence: EvidenceCount) => Estimate;
    /** The dialog's reads are refused, as for an archived Agent. */
    refuseReads?: boolean;
    cancelStatus?: number;
    /** Each Diff read of a Suggestion against the Draft, in turn (the last repeats); by default every change clean on revision 3. */
    diffs?: Diff[];
    /** Answers each apply instead of accepting it on any revision. */
    apply?: (baseRevision: number) => Response | undefined;
    deleteStatus?: number;
  } = {},
) {
  const requests: unknown[] = [];
  const applies: number[] = [];
  const deletes: string[] = [];
  let diffRead = 0;
  const evidenceReads: string[] = [];
  const cancels: string[] = [];
  const countOf = options.evidence ?? ((range) => evidenceCount(range));
  const entries = (options.suggestions ?? []).map((states) => ({ states, read: 0 }));
  const current = (entry: { states: Suggestion[]; read: number }) =>
    entry.states[Math.min(entry.read, entry.states.length - 1)] as Suggestion;
  const base = "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/suggestions";

  server.use(
    http.get(base, () => {
      if (options.failList) return HttpResponse.json({ detail: "Down" }, { status: 500 });
      return HttpResponse.json(entries.map((entry) => summary(current(entry))));
    }),
    http.get(`${base}/evidence`, ({ request }) => {
      const query = new URL(request.url).searchParams;
      const range = { range_start: query.get("range_start") ?? "", range_end: query.get("range_end") ?? "" };
      evidenceReads.push(`${range.range_start}..${range.range_end}`);
      if (options.refuseReads) return HttpResponse.json({ detail: "This Agent is archived. An Owner can restore it." }, { status: 409 });
      return HttpResponse.json(countOf(range));
    }),
    http.post(`${base}/estimate`, async ({ request }) => {
      if (options.refuseReads) return HttpResponse.json({ detail: "This Agent is archived. An Owner can restore it." }, { status: 409 });
      const range = (await request.json()) as { range_start: string; range_end: string };
      const counted = countOf(range);
      return HttpResponse.json((options.estimate ?? ((evidence) => estimateOf(evidence)))(counted));
    }),
    http.post(`${base}/:suggestionId/cancel`, ({ params }) => {
      cancels.push(params.suggestionId as string);
      if (options.cancelStatus) {
        return HttpResponse.json({ detail: "This Suggestion run has already finished." }, { status: options.cancelStatus });
      }
      const entry = entries.find((each) => current(each).id === params.suggestionId) as { states: Suggestion[]; read: number };
      const cancelled: Suggestion = { ...current(entry), status: "cancelled", finished_at: "2026-11-16T09:00:30Z" };
      entry.states = [cancelled];
      entry.read = 0;
      return HttpResponse.json(cancelled);
    }),
    http.get(`${base}/:suggestionId/diff`, ({ params }) => {
      const found = current(entries.find((each) => current(each).id === params.suggestionId) as { states: Suggestion[]; read: number });
      const diffs = options.diffs ?? [cleanDiff(found)];
      const diff = diffs[Math.min(diffRead, diffs.length - 1)] as Diff;
      diffRead += 1;
      return HttpResponse.json(diff);
    }),
    http.post(`${base}/:suggestionId/apply`, async ({ params, request }) => {
      const { base_revision: baseRevision } = (await request.json()) as { base_revision: number };
      applies.push(baseRevision);
      const answered = options.apply?.(baseRevision);
      if (answered) return answered;
      const entry = entries.find((each) => current(each).id === params.suggestionId) as { states: Suggestion[]; read: number };
      const applied: Suggestion = {
        ...current(entry),
        applied_at: "2026-11-16T10:00:00Z",
        applied_by: { id: adaSession.member.id, name: adaSession.member.name },
      };
      entry.states = [applied];
      entry.read = 0;
      const body: Applied = {
        agent: { ...appliedAgent, draft_revision: baseRevision + 1 },
        suggestion: applied,
        paths: applied.changes.map((change) => change.path),
        stale_notice: applied.stale ? STALE_NOTICE : null,
      };
      return HttpResponse.json(body);
    }),
    http.delete(`${base}/:suggestionId`, ({ params }) => {
      deletes.push(params.suggestionId as string);
      if (options.deleteStatus) {
        return HttpResponse.json({ detail: "This Agent is archived. An Owner can restore it." }, { status: options.deleteStatus });
      }
      const index = entries.findIndex((each) => current(each).id === params.suggestionId);
      entries.splice(index, 1);
      return new HttpResponse(null, { status: 204 });
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
  return { requests, evidenceReads, cancels, applies, deletes };
}
