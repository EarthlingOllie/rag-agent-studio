import type { Schemas } from "@studio/api-client";
import type { QueryKey } from "@tanstack/react-query";
import { useId } from "react";

import { Badge, text as type } from "../design";
import { formatTime } from "../settings/AuditPage";
import { VerdictReviewControls } from "../reviews/VerdictReview";
import { dollars } from "./format";

type LiveVerdict = Schemas["LiveVerdictOut"];
type LiveCheck = NonNullable<LiveVerdict["grounded"]>;

function Outcome({ passed }: { passed: boolean }) {
  return <Badge kind={passed ? "evaluationPass" : "evaluationFail"} />;
}

/** "Judged by anthropic · claude-haiku-4-5 for $0.0011 on 2026-11-06 10:15 UTC." */
function judgedBy(verdict: LiveVerdict): string {
  const cost =
    verdict.cost_usd === null ? "an unknown cost" : dollars(verdict.cost_usd);
  return `Judged by ${String(verdict.judge_provider)} · ${String(verdict.judge_model)} for ${cost} on ${formatTime(String(verdict.judged_at))}.`;
}

/** Where a review of the Live Verdict's checks goes: the Organisation, and what shows the Live Verdict to read again. */
export interface ReviewPlace {
  organisationId: string;
  shownKey: QueryKey;
}

function Judged({ verdict, place }: { verdict: LiveVerdict; place: ReviewPlace }) {
  const checks: [string, "grounding" | "answers_question", LiveCheck][] = [
    ["Grounded", "grounding", verdict.grounded as LiveCheck],
    ["Answers the question", "answers_question", verdict.answers_question as LiveCheck],
  ];
  return (
    <>
      <p className="flex items-center gap-2">
        <Outcome passed={verdict.passed === true} />
        <span className={type.muted}>
          A reply passes when it is grounded and answers the question.
        </span>
      </p>
      <ul aria-label="Live Verdict checks" className="space-y-3">
        {checks.map(([name, key, check]) => (
          <li key={key} className="flex flex-col gap-2">
            <p className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-medium">{name}</span>
              <Outcome passed={check.outcome === "pass"} />
              {verdict.purged_at === null ? (
                <span>{check.reason}</span>
              ) : (
                <span className={type.muted}>Text purged</span>
              )}
            </p>
            <VerdictReviewControls
              organisationId={place.organisationId}
              target={{ live_verdict_id: verdict.id, check: key }}
              judged={check.outcome}
              review={check.review}
              shownKey={place.shownKey}
              label={`the ${name} check`}
              reviewable={verdict.purged_at === null}
            />
          </li>
        ))}
      </ul>
      {verdict.purged_at !== null && (
        <p className={type.small}>
          The reasons were purged with the reply&apos;s text on{" "}
          {formatTime(verdict.purged_at)}.
        </p>
      )}
      <p className={type.small}>{judgedBy(verdict)}</p>
    </>
  );
}

function Body({ verdict, place }: { verdict: LiveVerdict | null; place: ReviewPlace }) {
  if (verdict === null)
    return (
      <p className={type.muted}>
        Not judged: the Live sample rate didn&apos;t choose this reply.
      </p>
    );
  switch (verdict.status) {
    case "pending":
      return (
        <p className={type.muted}>
          Pending: the Evaluation Model is judging this reply.
        </p>
      );
    case "skipped":
      return (
        <p className={type.muted}>
          Skipped: the text of the reply, its question or a turn it remembered
          was purged before it was judged.
        </p>
      );
    case "error":
      return (
        <p className="flex flex-wrap items-center gap-2">
          <Badge kind="evaluationError" />
          <span>
            The Evaluation Model couldn&apos;t judge this reply, so it is left
            out of the Live score: {verdict.error_reason}
          </span>
        </p>
      );
    case "judged":
      return <Judged verdict={verdict} place={place} />;
  }
}

/**
 * A Visitor reply's Live Verdict in its Trace: the Evaluation Model's two checks with their reasons (or "Text purged" once the Purge
 * cleared them) and an Editor's review of each, or why there are none.
 */
export function LiveVerdictSection({
  verdict,
  place,
}: {
  verdict: LiveVerdict | null;
  place: ReviewPlace;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="space-y-2 text-sm">
      <h3 id={headingId} className="font-medium">
        Live Verdict
      </h3>
      <Body verdict={verdict} place={place} />
    </section>
  );
}
