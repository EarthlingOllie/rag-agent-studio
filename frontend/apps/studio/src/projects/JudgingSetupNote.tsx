import { Icon, notice } from "../design";

import type { JudgingSetupChange } from "./analytics";

const changedDay = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

/** How a Judging setup change reads: "Judging guidance v2 saved", "Evaluation Model changed to gpt-4.1". */
export function judgingChange(change: JudgingSetupChange): string {
  if (change.kind === "guidance") {
    const version = `v${String(change.guidance_version)}`;
    return change.guidance_removed ? `Judging guidance removed (${version})` : `Judging guidance ${version} saved`;
  }
  return change.evaluation_model === null
    ? "Evaluation Model back to the Default Model"
    : `Evaluation Model changed to ${change.evaluation_model}`;
}

/**
 * The note, in the Confounder note's style, that the Live Verdicts of a range were judged under more than one Judging
 * setup, with the changes made during the range: their Live scores don't compare like with like.
 */
export function JudgingSetupNote({ mixed, changes }: { mixed: boolean; changes: JudgingSetupChange[] }) {
  if (!mixed) return null;
  const listed = changes.map((change) => `${changedDay.format(new Date(change.occurred_at))}: ${judgingChange(change)}`);
  return (
    <p role="note" className={`${notice.warning} flex items-start gap-2`}>
      <Icon name="warning" className="mt-0.5 shrink-0" />
      <span>
        {`Live Verdicts in this period were judged under more than one Judging setup${listed.length > 0 ? ` (${listed.join("; ")})` : ""}. A difference in the Live score across a change may come from how replies were judged rather than the Version.`}
      </span>
    </p>
  );
}
