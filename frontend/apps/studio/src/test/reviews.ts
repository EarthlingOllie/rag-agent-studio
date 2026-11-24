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

/**
 * A stateful stand-in for the Review sample: serves the first item not yet reviewed (each GET counted as a
 * draw), records each review, and reveals the Evaluation Model's outcome and reason. Agreement is counted
 * from the reviews.
 */
export function fakeReviewSampleApi(options: { items?: Judged[]; reviewed?: number } = {}) {
  const items = options.items ?? [leaveReference, leaveGrounding];
  const reviews: Schemas["SampleReviewRequest"][] = [];
  const draws = { count: 0 };
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
    http.get("*/api/organisations/:organisationId/evaluation-agreement", () => {
      const agreed = items.filter((judged) => reviewed.get(keyOf(judged.item)) === judged.outcome).length;
      return HttpResponse.json({ current: { provider: "openai", model: "gpt-4.1-mini", reviews: before + reviewed.size, agreed: before + agreed } });
    }),
  );
  return { reviews, draws };
}
