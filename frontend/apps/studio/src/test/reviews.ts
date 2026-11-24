import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { server } from "./server";

type Item = Schemas["ReviewSampleItemOut"];
type Outcome = Schemas["SampleReviewRequest"]["outcome"];

/** A judged Verdict in the sample, with the Evaluation Model's outcome and reason the page must not show until reviewed. */
export interface Judged {
  item: Item;
  outcome: Outcome;
  reason: string;
}

export const leaveReference: Judged = {
  item: {
    verdict_id: "6a1f0c34-0000-4000-8000-000000000001",
    live_verdict_id: null,
    check: "reference_answer",
    agent_id: "6a1f0c34-0000-4000-8000-0000000000a1",
    agent_name: "HR helper",
    question: "How much leave do I get?",
    reference_answer: 'Everyone gets "twenty-five days" of annual leave.',
    answer: "Everyone gets twenty-five days of annual leave a year, see [C1].",
    chunks: [
      { label: "C1", document_name: "leave.txt", text: "Everyone gets 25 days of annual leave a year.", cited: true },
      { label: "C2", document_name: "sick.txt", text: "Sick days are paid in full.", cited: false },
    ],
    remembered_turns: [],
  },
  outcome: "pass",
  reason: "Fake judge: the answer contains “twenty-five days”.",
};

export const leaveGrounding: Judged = {
  item: {
    ...leaveReference.item,
    verdict_id: "6a1f0c34-0000-4000-8000-000000000002",
    check: "grounding",
    reference_answer: null,
    answer: "Everyone gets ten days of leave.",
    chunks: [],
  },
  outcome: "fail",
  reason: "Fake judge: the answer cites nothing to support it.",
};

/** One check of a Live Verdict: a Visitor's follow-up, shown with the turn its reply remembered. */
export const liveAnswers: Judged = {
  item: {
    verdict_id: null,
    live_verdict_id: "6a1f0c34-0000-4000-8000-0000000000b1",
    check: "answers_question",
    agent_id: "6a1f0c34-0000-4000-8000-0000000000a1",
    agent_name: "HR helper",
    question: "What about part-timers?",
    reference_answer: null,
    answer: "Everyone gets twenty-five days of annual leave a year, see [C1].",
    chunks: [
      { label: "C1", document_name: "leave.txt", text: "Everyone gets 25 days of annual leave a year.", cited: true },
      { label: "C2", document_name: "part-time.txt", text: "Part-timers get leave pro rata.", cited: false },
    ],
    remembered_turns: [{ question: "How much annual leave do I get?", answer: "Twenty-five days a year." }],
  },
  outcome: "fail",
  reason: "It answers for everyone, not for part-timers.",
};

/** The same Live Verdict's grounding check. */
export const liveGrounding: Judged = {
  item: { ...liveAnswers.item, check: "grounding" },
  outcome: "pass",
  reason: "Its claim is cited from the leave policy.",
};

/** What identifies an item: its Verdict, or its Live Verdict and check. */
function keyOf(target: { verdict_id?: string | null; live_verdict_id?: string | null; check?: string | null }) {
  return target.verdict_id ?? `${target.live_verdict_id ?? ""}:${target.check ?? ""}`;
}

type Agreement = Schemas["AgreementOut"];
type Check = Schemas["CheckAgreementOut"]["check"];

/** Agreement figures as the API sends them; the rate is worked out, the interval is given. */
function figures(reviews: number, agreed: number, falsePasses: number, falseFails: number, low: number, high: number) {
  return {
    reviews,
    agreed,
    false_passes: falsePasses,
    false_fails: falseFails,
    rate: agreed / reviews,
    low,
    high,
    low_sample: reviews < 30,
  };
}

const check = (name: Check, ...rest: Parameters<typeof figures>) => ({ check: name, ...figures(...rest) });

/** The current Evaluation Model's agreement: 34 of 40, a few false passes, every check below 30 reviews. */
export const gptAgreement: Agreement = {
  provider: "openai",
  model: "gpt-4.1-mini",
  ...figures(40, 34, 4, 2, 0.709, 0.929),
  checks: [
    check("grounding", 20, 18, 1, 1, 0.699, 0.972),
    check("answers_question", 8, 6, 2, 0, 0.409, 0.929),
    check("reference_answer", 12, 10, 1, 1, 0.552, 0.953),
  ],
};

/** An earlier Evaluation Model with a handful of reviews. */
export const claudeAgreement: Agreement = {
  provider: "anthropic",
  model: "claude-haiku-4-5",
  ...figures(6, 3, 3, 0, 0.188, 0.812),
  checks: [check("grounding", 6, 3, 3, 0, 0.188, 0.812)],
};

/** An Evaluation Model nobody has reviewed yet. */
export function unreviewed(provider: Agreement["provider"], model: string): Agreement {
  return { provider, model, reviews: 0, agreed: 0, false_passes: 0, false_fails: 0, rate: null, low: null, high: null, low_sample: true, checks: [] };
}

/** Serves Evaluation Model agreement as given. */
export function fakeAgreementApi(agreement: Partial<Schemas["EvaluationAgreementOut"]>) {
  server.use(
    http.get("*/api/organisations/:organisationId/evaluation-agreement", () =>
      HttpResponse.json({ current: null, earlier: [], reviewed: 0, reviewed_by_you: 0, skipped: 0, ...agreement }),
    ),
  );
}

/**
 * A stateful stand-in for the Review sample: serves the first item not yet reviewed (each GET counted as a
 * draw), records each review and each skip, and reveals the Evaluation Model's outcome and reason. Agreement
 * is counted from the reviews.
 */
export function fakeReviewSampleApi(options: { items?: Judged[]; reviewed?: number } = {}) {
  const items = options.items ?? [leaveReference, leaveGrounding];
  const reviews: Schemas["SampleReviewRequest"][] = [];
  const draws = { count: 0 };
  const skips = { count: 0 };
  const reviewed = new Map<string, Outcome>();
  const before = options.reviewed ?? 0;
  server.use(
    http.get("*/api/organisations/:organisationId/review-sample/next", () => {
      draws.count += 1;
      const next = items.find((judged) => !reviewed.has(keyOf(judged.item)));
      return HttpResponse.json({ item: next?.item ?? null, reviewed: before + reviewed.size, reviewed_by_you: reviewed.size });
    }),
    http.post("*/api/organisations/:organisationId/review-sample/reviews", async ({ request }) => {
      const body = (await request.json()) as Schemas["SampleReviewRequest"];
      reviews.push(body);
      const judged = items.find((candidate) => keyOf(candidate.item) === keyOf(body)) as Judged;
      reviewed.set(keyOf(body), body.outcome);
      return HttpResponse.json({
        outcome: body.outcome,
        evaluation_model_outcome: judged.outcome,
        evaluation_model_reason: judged.reason,
        agreed: body.outcome === judged.outcome,
      });
    }),
    http.post("*/api/organisations/:organisationId/review-sample/skips", () => {
      skips.count += 1;
      return new HttpResponse(null, { status: 204 });
    }),
    http.get("*/api/organisations/:organisationId/evaluation-agreement", () => {
      const judged = items.filter((candidate) => reviewed.has(keyOf(candidate.item)));
      const agreed = judged.filter((candidate) => reviewed.get(keyOf(candidate.item)) === candidate.outcome).length;
      const falsePasses = judged.filter((candidate) => candidate.outcome === "pass" && reviewed.get(keyOf(candidate.item)) === "fail").length;
      const total = before + reviewed.size;
      return HttpResponse.json({
        current: {
          ...unreviewed("openai", "gpt-4.1-mini"),
          reviews: total,
          agreed: before + agreed,
          false_passes: falsePasses,
          false_fails: judged.length - agreed - falsePasses,
          low_sample: total < 30,
        },
        earlier: [],
        reviewed: total,
        reviewed_by_you: reviewed.size,
        skipped: skips.count,
      });
    }),
  );
  return { reviews, draws, skips };
}
