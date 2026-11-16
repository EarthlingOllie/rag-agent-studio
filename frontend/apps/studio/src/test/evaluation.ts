import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { hrTrace } from "./agents";
import { server } from "./server";

type Case = Schemas["CaseOut"];
type Run = Schemas["RunOut"];
type RunResults = Schemas["RunResultsOut"];
type CaseResult = Schemas["CaseResultOut"];
type PublishSummary = Schemas["PublishSummaryOut"];

export const leaveCase: Case = {
  id: "e1000000-0000-4000-8000-000000000001",
  question: "How much leave do I get?",
  reference_answer: 'Everyone gets "25 days" of annual leave.',
  expected_sources: [],
  expect_fallback: false,
  stale: false,
  source: "written",
  created_at: "2026-11-10T09:00:00Z",
  updated_at: "2026-11-10T09:00:00Z",
  latest_result: null,
};

export const parkingCase: Case = {
  id: "e1000000-0000-4000-8000-000000000002",
  question: "Where do visitors park?",
  reference_answer: "In the north car park.",
  expected_sources: [],
  expect_fallback: false,
  stale: false,
  source: "written",
  created_at: "2026-11-10T09:05:00Z",
  updated_at: "2026-11-10T09:05:00Z",
  latest_result: null,
};

/** A Run of the Draft alone, at a status and progress. */
export function run(
  id: string,
  status: Run["status"],
  done: number,
  total: number,
  overrides: Partial<Run> = {},
): Run {
  return {
    id,
    kind: "agent",
    status,
    created_at: "2026-11-12T10:00:00Z",
    finished_at:
      status === "completed" || status === "failed"
        ? "2026-11-12T10:01:00Z"
        : null,
    progress: { done, total },
    judge_provider: "openai",
    judge_model: "gpt-4.1-mini",
    repeats: 1,
    error_message: null,
    stale: false,
    cost: {
      estimated_usd: "0.006000000",
      answers_usd: "0.004200000",
      judging_usd: "0.001800000",
      total_usd: "0.006000000",
    },
    sides: [
      {
        position: "first",
        kind: "draft",
        agent_version_id: null,
        version_number: null,
        draft_revision: 3,
        instructions_version_number: 2,
        instructions_draft: false,
        model_provider: "openai",
        model_name: "gpt-4.1-mini",
        cases_passed: 1,
        cases_failed: 1,
        cases_errored: 0,
        score: 0.5,
      },
    ],
    ...overrides,
  };
}

export const passed: CaseResult = {
  position: "first",
  repeat: 1,
  status: "answered",
  error_reason: null,
  answer: "Everyone gets 25 days of annual leave a year [C1].",
  passed: true,
  verdicts: [
    {
      kind: "reference_answer",
      outcome: "pass",
      reason: "The answer gives the 25 days the reference names.",
    },
    {
      kind: "grounding",
      outcome: "pass",
      reason: "Every claim is in the cited excerpt.",
    },
  ],
  trace: {
    ...hrTrace,
    instructions_source: "version",
    instructions_version_number: 2,
  },
};

export const failedResult: CaseResult = {
  ...passed,
  answer: "Visitors can park anywhere.",
  passed: false,
  verdicts: [
    {
      kind: "reference_answer",
      outcome: "fail",
      reason: "The answer doesn't name the north car park.",
    },
    {
      kind: "grounding",
      outcome: "fail",
      reason: "Nothing cited supports it.",
    },
  ],
};

export const erroredResult: CaseResult = {
  ...passed,
  status: "error",
  error_reason: "The provider says this key is over its rate limit or quota.",
  answer: null,
  passed: null,
  verdicts: [],
  trace: null,
};

/** A case's result on the first side: its outcome and how many of its answered repeats passed. */
export function caseSide(
  outcome: "pass" | "fail" | "error",
  passed: number,
  answered: number,
  repeats = 1,
) {
  return { position: "first", outcome, passed, answered, repeats };
}

/** A case's answer at a repeat. */
export const repeat = (result: CaseResult, number: number): CaseResult => ({
  ...result,
  repeat: number,
});

/**
 * A Run's results: each case as copied, with its answers (one, or one per repeat) and, unless
 * given, its result on the first side as one answer gives it.
 */
export function results(
  of: Run,
  answers: [
    Case,
    CaseResult | CaseResult[],
    ReturnType<typeof caseSide>?,
    boolean?,
  ][],
): RunResults {
  return {
    run: of,
    cases: answers.map(([evaluationCase, answered, side, unsteady]) => {
      const each = Array.isArray(answered) ? answered : [answered];
      const [only] = each;
      const single =
        only?.status === "error"
          ? caseSide("error", 0, 0)
          : only?.passed
            ? caseSide("pass", 1, 1)
            : caseSide("fail", 0, 1);
      return {
        case_id: evaluationCase.id,
        question: evaluationCase.question,
        reference_answer: evaluationCase.reference_answer,
        expected_sources: evaluationCase.expected_sources.map(
          ({ document_name, passage }) => ({ document_name, passage }),
        ),
        expect_fallback: evaluationCase.expect_fallback,
        stale_expectation: evaluationCase.stale,
        sides: [side ?? single],
        unsteady: unsteady ?? false,
        change: null,
        results: each,
      };
    }),
  };
}

/** A Run's side that is Version 1 of `hrHelper`, as its first side. */
export const liveSide: Run["sides"][number] = {
  position: "first",
  kind: "version",
  agent_version_id: "a1e00000-0000-4000-8000-000000000001",
  version_number: 1,
  draft_revision: null,
  instructions_version_number: 1,
  instructions_draft: false,
  model_provider: "openai",
  model_name: "gpt-4.1-mini",
  cases_passed: 2,
  cases_failed: 1,
  cases_errored: 0,
  score: 2 / 3,
};

/** A Run's Draft side, as its second side. */
export const draftSide: Run["sides"][number] = {
  position: "second",
  kind: "draft",
  agent_version_id: null,
  version_number: null,
  draft_revision: 4,
  instructions_version_number: null,
  instructions_draft: true,
  model_provider: "openai",
  model_name: "gpt-4.1-mini",
  cases_passed: 1,
  cases_failed: 2,
  cases_errored: 0,
  score: 1 / 3,
};

export type EvaluationRequest = { route: string; body?: unknown };

/** An Evaluation summary for Publish in `state`, with no Run unless given. */
export function publishSummary(
  state: PublishSummary["state"],
  overrides: Partial<PublishSummary> = {},
): PublishSummary {
  return {
    state,
    run: null,
    regressions: [],
    lower_score: false,
    evaluated_live_version_number: null,
    publishing_instructions_version_number: 2,
    ...overrides,
  };
}

/** The Evaluate dialog's default estimate: two cases on one side, once each. */
export const anEstimate: Schemas["EstimateOut"] = {
  cases: 2,
  sides: 1,
  repeats: 1,
  answers_usd: "0.004000000",
  judging_usd: "0.002000000",
  total_usd: "0.006000000",
};

/** The latest result a case's filter reads: Unsteady over its majority outcome, or "not_run". */
function latestKind(c: Case): string {
  if (c.latest_result === null) return "not_run";
  return c.latest_result.unsteady ? "unsteady" : c.latest_result.outcome;
}

/** Whether a case matches the set's filters, as the API applies them. */
function matches(c: Case, query: URLSearchParams): boolean {
  const q = query.get("q");
  const kind = query.get("kind");
  const stale = query.get("stale");
  const result = query.get("result");
  const kinds = [
    ...(c.expected_sources.length > 0 ? ["expected_source"] : []),
    ...(c.reference_answer !== null ? ["reference_answer"] : []),
    ...(c.expect_fallback ? ["fallback"] : []),
  ];
  return (
    (q === null || c.question.toLowerCase().includes(q.toLowerCase())) &&
    (kind === null || kinds.includes(kind)) &&
    (stale === null || String(c.stale) === stale) &&
    (result === null || latestKind(c) === result)
  );
}

/**
 * The Agent's evaluation routes, in memory. Cases are listed, added, replaced and deleted; Runs are
 * listed newest first, each read as its next state on every read of its results, so a Run started
 * with `started` moves through those states as the Studio polls it.
 */
export function fakeEvaluationApi(
  options: {
    cases?: Case[];
    runs?: RunResults[];
    /** The states a started Run goes through, one per read of its results. */
    started?: RunResults[];
    /** Each case's latest result (by case ID) once a started Run has finished, as the API reads it then. */
    latestAfterRun?: Record<string, NonNullable<Case["latest_result"]>>;
    startStatus?: number;
    startDetail?: string;
    /** Refuses cancelling with this status and detail. */
    cancelStatus?: number;
    cancelDetail?: string;
    /** Refuses saving a case with this status (and detail, when given). */
    saveStatus?: number;
    saveDetail?: string;
    deleteStatus?: number;
    deleteDetail?: string;
    failCases?: boolean;
    failRuns?: boolean;
    failResults?: boolean;
    /** Each Document's name by ID, for the Expected sources of a saved case. */
    documentNames?: Record<string, string>;
    /** Other Agents' Evaluation Sets, by Agent ID, to copy from. */
    otherCases?: Record<string, Case[]>;
    /** Refuses copying with this status and detail. */
    copyStatus?: number;
    copyDetail?: string;
    /** What "Add to Evaluation Set" reads for a Message, or the status and detail it is refused with. */
    prefill?: Schemas["PrefillOut"] | { status: number; detail: string };
    /** What the Evaluate dialog's estimate reads (`anEstimate` by default), or the status and detail it is refused with. */
    estimate?: Schemas["EstimateOut"] | { status: number; detail: string };
    /** What the Publish dialog's Evaluation summary reads, one per read (the last repeats), or the status it fails with. */
    summaries?: PublishSummary[] | { status: number };
  } = {},
) {
  const requests: EvaluationRequest[] = [];
  /** Each choice the estimate was asked about. */
  const estimates: unknown[] = [];
  let cases = [...(options.cases ?? [])];
  const runs: { states: RunResults[]; read: number }[] = (
    options.runs ?? []
  ).map((state) => ({ states: [state], read: 0 }));
  const current = (entry: { states: RunResults[]; read: number }) =>
    entry.states[Math.min(entry.read, entry.states.length - 1)] as RunResults;
  const base =
    "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/evaluation";
  let added = 0;
  let summaryReads = 0;
  const expectedSources = (body: Schemas["CaseIn"]): Case["expected_sources"] =>
    (body.expected_sources ?? []).map((source, index) => ({
      id: `e3000000-0000-4000-8000-00000000000${String(index)}`,
      document_id: source.document_id,
      document_name:
        options.documentNames?.[source.document_id] ?? source.document_id,
      passage: source.passage,
      stale: false,
      stale_reason: null,
    }));

  server.use(
    http.get(`${base}/cases`, ({ request, params }) => {
      if (options.failCases)
        return HttpResponse.json({ detail: "Down" }, { status: 500 });
      const other = options.otherCases?.[params.agentId as string];
      if (other) return HttpResponse.json(other);
      const startedRun = options.started === undefined ? undefined : runs[0];
      const finished = startedRun !== undefined && !["queued", "running"].includes(current(startedRun).run.status);
      const latest = finished ? (options.latestAfterRun ?? {}) : {};
      return HttpResponse.json(
        cases
          .map((c) => ({ ...c, latest_result: latest[c.id] ?? c.latest_result }))
          .filter((c) => matches(c, new URL(request.url).searchParams)),
      );
    }),
    http.post(`${base}/cases/copy`, async ({ request }) => {
      const body = (await request.json()) as Schemas["CopyIn"];
      requests.push({ route: "copy", body });
      if (options.copyStatus)
        return HttpResponse.json(
          { detail: options.copyDetail },
          { status: options.copyStatus },
        );
      const chosen = (options.otherCases?.[body.agent_id] ?? []).filter((c) =>
        body.case_ids.includes(c.id),
      );
      const copies = chosen.map((c, index) => ({
        ...c,
        id: `e4000000-0000-4000-8000-00000000000${String(index)}`,
        latest_result: null,
      }));
      cases = [...cases, ...copies];
      return HttpResponse.json(copies, { status: 201 });
    }),
    http.get(`${base}/messages/:messageId/prefill`, ({ params }) => {
      requests.push({
        route: "prefill",
        body: { messageId: params.messageId, agentId: params.agentId },
      });
      const prefill = options.prefill;
      if (prefill === undefined || "status" in prefill) {
        return HttpResponse.json(
          { detail: prefill?.detail ?? "Not Found" },
          { status: prefill?.status ?? 404 },
        );
      }
      return HttpResponse.json(prefill);
    }),
    http.post(`${base}/cases`, async ({ request }) => {
      const body = (await request.json()) as Schemas["NewCaseIn"];
      requests.push({ route: "create", body });
      if (options.saveStatus) {
        return HttpResponse.json(
          options.saveDetail ? { detail: options.saveDetail } : {},
          { status: options.saveStatus },
        );
      }
      added += 1;
      const created: Case = {
        id: `e2000000-0000-4000-8000-00000000000${String(added)}`,
        question: body.question.trim(),
        reference_answer: body.reference_answer ?? null,
        expected_sources: expectedSources(body),
        expect_fallback: body.expect_fallback,
        stale: false,
        source: body.source,
        created_at: "2026-11-12T09:00:00Z",
        updated_at: "2026-11-12T09:00:00Z",
        latest_result: null,
      };
      cases = [...cases, created];
      return HttpResponse.json(created, { status: 201 });
    }),
    http.put(`${base}/cases/:caseId`, async ({ request, params }) => {
      const body = (await request.json()) as Schemas["CaseIn"];
      requests.push({
        route: "update",
        body: { ...body, caseId: params.caseId },
      });
      if (options.saveStatus) {
        return HttpResponse.json(
          { detail: options.saveDetail },
          { status: options.saveStatus },
        );
      }
      cases = cases.map((c) =>
        c.id === params.caseId
          ? {
              ...c,
              question: body.question,
              reference_answer: body.reference_answer ?? null,
              expected_sources: expectedSources(body),
              expect_fallback: body.expect_fallback,
              stale: false,
            }
          : c,
      );
      return HttpResponse.json(cases.find((c) => c.id === params.caseId));
    }),
    http.delete(`${base}/cases/:caseId`, ({ params }) => {
      requests.push({ route: "delete", body: { caseId: params.caseId } });
      if (options.deleteStatus) {
        return HttpResponse.json(
          { detail: options.deleteDetail },
          { status: options.deleteStatus },
        );
      }
      cases = cases.filter((c) => c.id !== params.caseId);
      return new HttpResponse(null, { status: 204 });
    }),
    http.get(`${base}/publish-summary`, ({ request }) => {
      requests.push({
        route: "summary",
        body: {
          instructions_version_id: new URL(request.url).searchParams.get(
            "instructions_version_id",
          ),
        },
      });
      const summaries = options.summaries ?? [publishSummary("no_set")];
      if ("status" in summaries)
        return HttpResponse.json(
          { detail: "Down" },
          { status: summaries.status },
        );
      const found = summaries[Math.min(summaryReads, summaries.length - 1)];
      summaryReads += 1;
      return HttpResponse.json(found);
    }),
    http.get(`${base}/runs/:runId`, ({ params }) => {
      const entry = runs.find(
        (candidate) => current(candidate).run.id === params.runId,
      ) as (typeof runs)[number];
      const state = current(entry);
      entry.read += 1;
      return HttpResponse.json(state.run);
    }),
    http.get(`${base}/runs`, () =>
      options.failRuns
        ? HttpResponse.json({ detail: "Down" }, { status: 500 })
        : HttpResponse.json(runs.map((entry) => current(entry).run)),
    ),
    http.post(`${base}/estimate`, async ({ request }) => {
      estimates.push(await request.json());
      const estimate = options.estimate ?? anEstimate;
      if ("status" in estimate)
        return HttpResponse.json(
          { detail: estimate.detail },
          { status: estimate.status },
        );
      return HttpResponse.json(estimate);
    }),
    http.post(`${base}/runs`, async ({ request }) => {
      requests.push({ route: "start", body: await request.json() });
      if (options.startStatus) {
        return HttpResponse.json(
          { detail: options.startDetail },
          { status: options.startStatus },
        );
      }
      const entry = { states: options.started ?? [], read: 0 };
      runs.unshift(entry);
      return HttpResponse.json(current(entry).run, { status: 202 });
    }),
    http.post(`${base}/runs/:runId/cancel`, ({ params }) => {
      requests.push({ route: "cancel", body: { runId: params.runId } });
      if (options.cancelStatus) {
        return HttpResponse.json(
          { detail: options.cancelDetail },
          { status: options.cancelStatus },
        );
      }
      const entry = runs.find(
        (candidate) => current(candidate).run.id === params.runId,
      ) as (typeof runs)[number];
      const state = current(entry);
      const cancelled = {
        ...state,
        run: {
          ...state.run,
          status: "cancelled",
          finished_at: "2026-11-12T10:00:30Z",
        },
      };
      entry.states = [cancelled];
      entry.read = 0;
      return HttpResponse.json(cancelled.run);
    }),
    http.get(`${base}/runs/:runId/results`, ({ params }) => {
      if (options.failResults)
        return HttpResponse.json({ detail: "Down" }, { status: 500 });
      const entry = runs.find(
        (candidate) => current(candidate).run.id === params.runId,
      ) as (typeof runs)[number];
      const state = current(entry);
      entry.read += 1;
      return HttpResponse.json(state);
    }),
  );
  return { requests, estimates };
}

type RolloutEvaluation = Schemas["RolloutEvaluationOut"];
type RolloutAgentEvaluation = Schemas["RolloutAgentEvaluationOut"];

/** An Agent's Rollout evaluation state, with no Run or Regressions unless given. */
export function rolloutAgentEvaluation(
  agentId: string,
  name: string,
  state: RolloutAgentEvaluation["state"],
  overrides: Partial<RolloutAgentEvaluation> = {},
): RolloutAgentEvaluation {
  return {
    agent_id: agentId,
    name,
    state,
    has_set: true,
    run: null,
    regressions: [],
    ...overrides,
  };
}

/**
 * Fakes the Rollout evaluation routes: each read answers the next of `reads` (the last one
 * repeating), and starting answers `startStatus` with `startDetail` when given. Records the
 * requests it receives.
 */
export function fakeRolloutEvaluationApi(options: {
  reads: RolloutEvaluation[] | { status: number };
  startStatus?: number;
  startDetail?: string;
}) {
  const requests: EvaluationRequest[] = [];
  let read = 0;
  const path =
    "*/api/organisations/:organisationId/projects/:projectId/instructions/versions/:versionId/evaluation";
  const answer = () => {
    const { reads } = options;
    if ("status" in reads)
      return HttpResponse.json({ detail: "Down" }, { status: reads.status });
    const found = reads[Math.min(read, reads.length - 1)];
    read += 1;
    return HttpResponse.json(found);
  };
  server.use(
    http.get(path, answer),
    http.post(path, async ({ request }) => {
      requests.push({ route: "start-rollout", body: await request.json() });
      if (options.startStatus)
        return HttpResponse.json(
          { detail: options.startDetail },
          { status: options.startStatus },
        );
      return answer();
    }),
  );
  return { requests };
}
