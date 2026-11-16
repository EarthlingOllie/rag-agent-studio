import type { Schemas } from "@studio/api-client";
import { useId } from "react";

import { Badge, text as type } from "../design";
import { formatTime } from "../settings/AuditPage";
import { dollars } from "./format";

type LiveVerdict = Schemas["LiveVerdictOut"];
type LiveCheck = NonNullable<LiveVerdict["grounded"]>;

function Outcome({ passed }: { passed: boolean }) {
  return <Badge kind={passed ? "evaluationPass" : "evaluationFail"} />;
}

/** "Judged by anthropic · claude-haiku-4-5 for $0.0011 on 2026-11-06 10:15 UTC." */
function judgedBy(verdict: LiveVerdict): string {
  const cost = verdict.cost_usd === null ? "an unknown cost" : dollars(verdict.cost_usd);
  return `Judged by ${String(verdict.judge_provider)} · ${String(verdict.judge_model)} for ${cost} on ${formatTime(String(verdict.judged_at))}.`;
}

function Judged({ verdict }: { verdict: LiveVerdict }) {
  const checks: [string, LiveCheck][] = [
    ["Grounded", verdict.grounded as LiveCheck],
    ["Answers the question", verdict.answers_question as LiveCheck],
  ];
  return (
    <>
      <p className="flex items-center gap-2">
        <Outcome passed={verdict.passed === true} />
        <span className={type.muted}>A reply passes when it is grounded and answers the question.</span>
      </p>
      <ul aria-label="Live Verdict checks" className="space-y-1">
        {checks.map(([name, check]) => (
          <li key={name} className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-medium">{name}</span>
            <Outcome passed={check.outcome === "pass"} />
            <span>{check.reason}</span>
          </li>
        ))}
      </ul>
      <p className={type.small}>{judgedBy(verdict)}</p>
    </>
  );
}

function Body({ verdict }: { verdict: LiveVerdict | null }) {
  if (verdict === null)
    return <p className={type.muted}>Not judged: the Live sample rate didn&apos;t choose this reply.</p>;
  switch (verdict.status) {
    case "pending":
      return <p className={type.muted}>Pending: the Evaluation Model is judging this reply.</p>;
    case "skipped":
      return <p className={type.muted}>Skipped: the reply&apos;s text was purged before it was judged.</p>;
    case "error":
      return (
        <p className="flex flex-wrap items-center gap-2">
          <Badge kind="evaluationError" />
          <span>
            The Evaluation Model couldn&apos;t judge this reply, so it is left out of the Live score: {verdict.error_reason}
          </span>
        </p>
      );
    case "judged":
      return <Judged verdict={verdict} />;
  }
}

/** A Visitor reply's Live Verdict in its Trace: the Evaluation Model's two checks with their reasons, or why there are none. */
export function LiveVerdictSection({ verdict }: { verdict: LiveVerdict | null }) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="space-y-2 text-sm">
      <h3 id={headingId} className="font-medium">
        Live Verdict
      </h3>
      <Body verdict={verdict} />
    </section>
  );
}
