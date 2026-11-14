import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { hrTrace } from "./agents";
import { server } from "./server";

type Case = Schemas["CaseOut"];
type Run = Schemas["RunOut"];
type RunResults = Schemas["RunResultsOut"];
type CaseResult = Schemas["CaseResultOut"];

export const leaveCase: Case = {
  id: "e1000000-0000-4000-8000-000000000001",
  question: "How much leave do I get?",
  reference_answer: 'Everyone gets "25 days" of annual leave.',
  source: "written",
  created_at: "2026-11-10T09:00:00Z",
  updated_at: "2026-11-10T09:00:00Z",
  latest_result: null,
};

export const parkingCase: Case = {
  id: "e1000000-0000-4000-8000-000000000002",
  question: "Where do visitors park?",
  reference_answer: "In the north car park.",
  source: "written",
  created_at: "2026-11-10T09:05:00Z",
  updated_at: "2026-11-10T09:05:00Z",
  latest_result: null,
};

/** A Run of the Draft alone, at a status and progress. */
export function run(id: string, status: Run["status"], done: number, total: number, overrides: Partial<Run> = {}): Run {
  return {
    id,
    status,
    created_at: "2026-11-12T10:00:00Z",
    finished_at: status === "completed" || status === "failed" ? "2026-11-12T10:01:00Z" : null,
    progress: { done, total },
    judge_provider: "openai",
    judge_model: "gpt-4.1-mini",
    repeats: 1,
    error_message: null,
    stale: false,
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
    { kind: "reference_answer", outcome: "pass", reason: "The answer gives the 25 days the reference names." },
    { kind: "grounding", outcome: "pass", reason: "Every claim is in the cited excerpt." },
  ],
  trace: { ...hrTrace, instructions_source: "version", instructions_version_number: 2 },
};

export const failedResult: CaseResult = {
  ...passed,
  answer: "Visitors can park anywhere.",
  passed: false,
  verdicts: [
    { kind: "reference_answer", outcome: "fail", reason: "The answer doesn't name the north car park." },
    { kind: "grounding", outcome: "fail", reason: "Nothing cited supports it." },
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
export function caseSide(outcome: "pass" | "fail" | "error", passed: number, answered: number, repeats = 1) {
  return { position: "first", outcome, passed, answered, repeats };
}

/** A case's answer at a repeat. */
export const repeat = (result: CaseResult, number: number): CaseResult => ({ ...result, repeat: number });

/**
 * A Run's results: each case as copied, with its answers (one, or one per repeat) and, unless
 * given, its result on the first side as one answer gives it.
 */
export function results(
  of: Run,
  answers: [Case, CaseResult | CaseResult[], ReturnType<typeof caseSide>?, boolean?][],
): RunResults {
  return {
    run: of,
    cases: answers.map(([evaluationCase, answered, side, unsteady]) => {
      const each = Array.isArray(answered) ? answered : [answered];
      const [only] = each;
      const single =
        only?.status === "error" ? caseSide("error", 0, 0) : only?.passed ? caseSide("pass", 1, 1) : caseSide("fail", 0, 1);
      return {
        case_id: evaluationCase.id,
        question: evaluationCase.question,
        reference_answer: evaluationCase.reference_answer,
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
  } = {},
) {
  const requests: EvaluationRequest[] = [];
  let cases = [...(options.cases ?? [])];
  const runs: { states: RunResults[]; read: number }[] = (options.runs ?? []).map((state) => ({ states: [state], read: 0 }));
  const current = (entry: { states: RunResults[]; read: number }) =>
    entry.states[Math.min(entry.read, entry.states.length - 1)] as RunResults;
  const base = "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/evaluation";
  let added = 0;

  server.use(
    http.get(`${base}/cases`, () =>
      options.failCases ? HttpResponse.json({ detail: "Down" }, { status: 500 }) : HttpResponse.json(cases),
    ),
    http.post(`${base}/cases`, async ({ request }) => {
      const body = (await request.json()) as Schemas["CaseIn"];
      requests.push({ route: "create", body });
      if (options.saveStatus) {
        return HttpResponse.json(options.saveDetail ? { detail: options.saveDetail } : {}, { status: options.saveStatus });
      }
      added += 1;
      const created: Case = {
        id: `e2000000-0000-4000-8000-00000000000${String(added)}`,
        question: body.question.trim(),
        reference_answer: body.reference_answer ?? null,
        source: "written",
        created_at: "2026-11-12T09:00:00Z",
        updated_at: "2026-11-12T09:00:00Z",
        latest_result: null,
      };
      cases = [...cases, created];
      return HttpResponse.json(created, { status: 201 });
    }),
    http.put(`${base}/cases/:caseId`, async ({ request, params }) => {
      const body = (await request.json()) as Schemas["CaseIn"];
      requests.push({ route: "update", body: { ...body, caseId: params.caseId } });
      if (options.saveStatus) {
        return HttpResponse.json({ detail: options.saveDetail }, { status: options.saveStatus });
      }
      cases = cases.map((c) =>
        c.id === params.caseId ? { ...c, question: body.question, reference_answer: body.reference_answer ?? null } : c,
      );
      return HttpResponse.json(cases.find((c) => c.id === params.caseId));
    }),
    http.delete(`${base}/cases/:caseId`, ({ params }) => {
      requests.push({ route: "delete", body: { caseId: params.caseId } });
      if (options.deleteStatus) {
        return HttpResponse.json({ detail: options.deleteDetail }, { status: options.deleteStatus });
      }
      cases = cases.filter((c) => c.id !== params.caseId);
      return new HttpResponse(null, { status: 204 });
    }),
    http.get(`${base}/runs`, () =>
      options.failRuns
        ? HttpResponse.json({ detail: "Down" }, { status: 500 })
        : HttpResponse.json(runs.map((entry) => current(entry).run)),
    ),
    http.post(`${base}/runs`, async ({ request }) => {
      requests.push({ route: "start", body: await request.json() });
      if (options.startStatus) {
        return HttpResponse.json({ detail: options.startDetail }, { status: options.startStatus });
      }
      const entry = { states: options.started ?? [], read: 0 };
      runs.unshift(entry);
      return HttpResponse.json(current(entry).run, { status: 202 });
    }),
    http.post(`${base}/runs/:runId/cancel`, ({ params }) => {
      requests.push({ route: "cancel", body: { runId: params.runId } });
      if (options.cancelStatus) {
        return HttpResponse.json({ detail: options.cancelDetail }, { status: options.cancelStatus });
      }
      const entry = runs.find((candidate) => current(candidate).run.id === params.runId) as (typeof runs)[number];
      const state = current(entry);
      const cancelled = { ...state, run: { ...state.run, status: "cancelled", finished_at: "2026-11-12T10:00:30Z" } };
      entry.states = [cancelled];
      entry.read = 0;
      return HttpResponse.json(cancelled.run);
    }),
    http.get(`${base}/runs/:runId/results`, ({ params }) => {
      if (options.failResults) return HttpResponse.json({ detail: "Down" }, { status: 500 });
      const entry = runs.find((candidate) => current(candidate).run.id === params.runId) as (typeof runs)[number];
      const state = current(entry);
      entry.read += 1;
      return HttpResponse.json(state);
    }),
  );
  return { requests };
}
