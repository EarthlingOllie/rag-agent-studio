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
      const next = items.find((judged) => !reviewed.has(judged.item.verdict_id));
      return HttpResponse.json({ item: next?.item ?? null, reviewed: before + reviewed.size, reviewed_by_you: reviewed.size });
    }),
    http.post("*/api/organisations/:organisationId/review-sample/reviews", async ({ request }) => {
      const body = (await request.json()) as Schemas["SampleReviewRequest"];
      reviews.push(body);
      const judged = items.find((candidate) => candidate.item.verdict_id === body.verdict_id) as Judged;
      reviewed.set(body.verdict_id, body.outcome);
      return HttpResponse.json({
        outcome: body.outcome,
        evaluation_model_outcome: judged.outcome,
        evaluation_model_reason: judged.reason,
        agreed: body.outcome === judged.outcome,
      });
    }),
    http.get("*/api/organisations/:organisationId/evaluation-agreement", () => {
      const agreed = items.filter((judged) => reviewed.get(judged.item.verdict_id) === judged.outcome).length;
      return HttpResponse.json({ current: { provider: "openai", model: "gpt-4.1-mini", reviews: before + reviewed.size, agreed: before + agreed } });
    }),
  );
  return { reviews, draws };
}
