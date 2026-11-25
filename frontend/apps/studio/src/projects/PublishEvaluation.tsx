import { Link } from "@tanstack/react-router";
import { useId, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { Meter, Notice, button, text } from "../design";
import type { Agent } from "./agents";
import {
  type EvaluationPublishSummary,
  type EvaluationRegression,
  type EvaluationRunSide,
  evaluationFailure,
  inProgress,
  useEvaluationRun,
  useEvaluationRuns,
  usePublishSummary,
  useStartEvaluationRun,
} from "./evaluation";

const VERDICTS = {
  expected_source: "Expected source",
  fallback: "Expect Fallback Text",
  reference_answer: "Reference answer",
  grounding: "Grounding",
} as const;

/** A side's Evaluation score; none when every case was an Error. */
const percent = (score: number | null) =>
  score === null
    ? "none, every case was an Error"
    : `${String(Math.round(score * 100))}%`;

function instructionsWords(number: number | null, draft: boolean): string {
  if (draft) return "the Instructions Draft";
  return number === null
    ? "no Project Instructions"
    : `Instructions v${String(number)}`;
}

export function RegressionList({
  regressions,
}: {
  regressions: EvaluationRegression[];
}) {
  return (
    <ul aria-label="Regressions" className="flex flex-col gap-2">
      {regressions.map((regression, index) => (
        <li
          key={regression.case_id ?? index}
          className="flex flex-col gap-0.5 text-sm"
        >
          <span className="font-medium text-ink">{regression.question}</span>
          {regression.reasons.map((reason) => (
            <span key={reason.kind} className="text-ink-2">
              {`${VERDICTS[reason.kind as keyof typeof VERDICTS]}: ${reason.reason ?? "failed"}`}
            </span>
          ))}
        </li>
      ))}
    </ul>
  );
}

/** The warning about Regressions or a lower Evaluation score, with each Regression and why it failed. */
function RegressionWarning({
  summary,
  sides,
}: {
  summary: EvaluationPublishSummary;
  sides: EvaluationRunSide[];
}) {
  const count = summary.regressions.length;
  const parts: string[] = [];
  if (count === 1)
    parts.push(
      "This Draft has 1 Regression: a case that passes on the Live Version fails on the Draft.",
    );
  if (count > 1)
    parts.push(
      `This Draft has ${String(count)} Regressions: cases that pass on the Live Version fail on the Draft.`,
    );
  const [live, draft] = sides as [EvaluationRunSide, EvaluationRunSide];
  if (summary.lower_score) {
    parts.push(
      `Its Evaluation score is lower: ${percent(draft.score)} against ${percent(live.score)} on the Live Version.`,
    );
  }
  return (
    <>
      <Notice tone="warning">{parts.join(" ")} You can still Publish.</Notice>
      {count > 0 && <RegressionList regressions={summary.regressions} />}
    </>
  );
}

/** What the summary says, as a warning, a notice, the line for a clear Run, or the hint to create a set. */
function SummaryBody({
  agent,
  organisationId,
  summary,
}: {
  agent: Agent;
  organisationId: string;
  summary: EvaluationPublishSummary;
}) {
  const sides = summary.run?.sides ?? [];
  const draft = sides.at(-1);
  switch (summary.state) {
    case "no_set":
      return (
        <p className={text.muted}>
          No Evaluation Set yet. Add the questions that matter on the{" "}
          <Link
            to="/organisations/$organisationId/projects/$projectId/agents/$agentId/evaluation"
            params={{
              organisationId,
              projectId: agent.project_id,
              agentId: agent.id,
            }}
            className="font-medium text-accent-ink underline"
          >
            Evaluation tab
          </Link>{" "}
          to check a Draft before Publishing.
        </p>
      );
    case "no_run":
      return (
        <Notice tone="info">
          {agent.live_version
            ? `The Draft hasn't been evaluated against the Live Version (v${String(agent.live_version.number)}) yet.`
            : "The Draft hasn't been evaluated yet."}
        </Notice>
      );
    case "live_changed":
      return (
        <Notice tone="warning">
          {`The Live Version has changed since the Draft was evaluated: it was compared with v${String(summary.evaluated_live_version_number)}, and v${String(agent.live_version?.number)} is Live now.`}
        </Notice>
      );
    case "stale":
      return (
        <Notice tone="warning">
          The Draft has changed since it was evaluated: the latest Run describes
          an earlier Draft revision.
        </Notice>
      );
    case "instructions_differ": {
      const evaluated = draft as EvaluationRunSide;
      const used = instructionsWords(
        evaluated.instructions_version_number,
        evaluated.instructions_draft,
      );
      const number = summary.publishing_instructions_version_number;
      const publishing =
        number === null ? "no Project Instructions" : `v${String(number)}`;
      return (
        <Notice tone="warning">{`Evaluated with ${used}, publishing with ${publishing}.`}</Notice>
      );
    }
    case "regressions":
      return <RegressionWarning summary={summary} sides={sides} />;
    case "clear": {
      const [first, second] = sides as [
        EvaluationRunSide,
        EvaluationRunSide | undefined,
      ];
      return (
        <Notice tone="success">
          {second
            ? `No Regressions against the Live Version: Evaluation score ${percent(second.score)} against ${percent(first.score)}.`
            : `Evaluated: the Draft's Evaluation score is ${percent(first.score)}.`}
        </Notice>
      );
    }
  }
}

/** The Run started from the dialog: its progress, or how it ended when it didn't complete. */
function StartedRun({
  path,
  runId,
}: {
  path: { organisation_id: string; project_id: string; agent_id: string };
  runId: string;
}) {
  const started = useEvaluationRun(path, runId);
  if (started.isError)
    return (
      <p className={text.muted}>The Run&apos;s progress could not be loaded.</p>
    );
  const run = started.data;
  if (run === undefined) return null;
  if (inProgress(run)) {
    return (
      <Meter
        label="Answers given"
        value={run.progress.done}
        max={Math.max(run.progress.total, 1)}
        unit="answers"
        progress
      />
    );
  }
  if (run.status === "failed")
    return <p className={text.muted}>{run.error_message}</p>;
  if (run.status === "cancelled")
    return (
      <p className={text.muted}>The Run was cancelled before it finished.</p>
    );
  return null;
}

/**
 * The Publish dialog's Evaluation section: whether the Draft has been evaluated against the current
 * Live Version with the Instructions being published, a warning about Regressions or a lower
 * Evaluation score, and an Evaluate action. It never blocks Publishing.
 */
export function PublishEvaluation({
  agent,
  organisationId,
  instructionsVersionId,
}: {
  agent: Agent;
  organisationId: string;
  /** The Instructions Version chosen in the dialog; `null` for the Current one. */
  instructionsVersionId: string | null;
}) {
  const headingId = useId();
  const path = {
    organisation_id: organisationId,
    project_id: agent.project_id,
    agent_id: agent.id,
  };
  const summary = usePublishSummary(path, instructionsVersionId, [
    agent.live_version?.id ?? null,
    agent.draft_revision,
  ]);
  const start = useStartEvaluationRun(path);
  const [runId, setRunId] = useState<string | null>(null);
  // The server's Runs, not only the one started here: a Run started from the Evaluation view
  // holds the Agent's single active Run just the same.
  const runs = useEvaluationRuns(path);
  const evaluating = start.isPending || (runs.data ?? []).some(inProgress);

  let body;
  if (summary.isError) {
    body = (
      <p className={text.muted}>The evaluation summary could not be loaded.</p>
    );
  } else if (summary.data === undefined) {
    body = <p className={text.muted}>Checking the Draft&apos;s evaluation…</p>;
  } else {
    body = (
      <SummaryBody
        agent={agent}
        organisationId={organisationId}
        summary={summary.data}
      />
    );
  }

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h3 id={headingId} className="text-sm font-semibold text-ink">
        Evaluation
      </h3>
      {body}
      {summary.data?.earlier_judging_setup === true && (
        <Notice tone="info">
          The Draft&apos;s latest Run was judged under an earlier Judging setup (another Evaluation Model or Judging guidance
          version), so its scores may read differently now. You can still Publish.
        </Notice>
      )}
      {summary.data !== undefined && summary.data.state !== "no_set" && (
        <>
          <div>
            <button
              type="button"
              className={button.secondary}
              disabled={evaluating}
              onClick={() => {
                start.mutate(
                  {
                    instructions_draft: false,
                    ...(instructionsVersionId !== null && {
                      instructions_version_id: instructionsVersionId,
                    }),
                  },
                  {
                    onSuccess: (run) => {
                      setRunId(run.id);
                    },
                  },
                );
              }}
            >
              {evaluating ? "Evaluating…" : "Evaluate"}
            </button>
          </div>
          {runId !== null && <StartedRun path={path} runId={runId} />}
          <FormError message={evaluationFailure(start.error)} />
        </>
      )}
    </section>
  );
}
