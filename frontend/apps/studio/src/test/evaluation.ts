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
};

export const parkingCase: Case = {
  id: "e1000000-0000-4000-8000-000000000002",
  question: "Where do visitors park?",
  reference_answer: "In the north car park.",
  source: "written",
  created_at: "2026-11-10T09:05:00Z",
  updated_at: "2026-11-10T09:05:00Z",
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
    error_message: null,
    sides: [
      {
        position: "first",
        kind: "draft",
        draft_revision: 3,
        instructions_version_number: 2,
        model_provider: "openai",
        model_name: "gpt-4.1-mini",
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

/** A Run's results: each case as copied, with one answer each. */
export function results(of: Run, answers: [Case, CaseResult][]): RunResults {
  return {
    run: of,
    cases: answers.map(([evaluationCase, result]) => ({
      case_id: evaluationCase.id,
      question: evaluationCase.question,
      reference_answer: evaluationCase.reference_answer,
      results: [result],
    })),
  };
}

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
    http.post(`${base}/runs`, () => {
      requests.push({ route: "start" });
      if (options.startStatus) {
        return HttpResponse.json({ detail: options.startDetail }, { status: options.startStatus });
      }
      const entry = { states: options.started ?? [], read: 0 };
      runs.unshift(entry);
      return HttpResponse.json(current(entry).run, { status: 202 });
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
