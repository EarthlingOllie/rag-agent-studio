import { type SubmitEvent, useEffect, useId, useRef, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import {
  Badge,
  ConfirmDialog,
  Segmented,
  layout,
  Dialog,
  EmptyState,
  Icon,
  Menu,
  Meter,
  Notice,
  PageHeader,
  Skeleton,
  Status,
  button,
  useToast,
  field,
  surface,
  table,
  text,
} from "../design";
import { formatTime } from "../settings/AuditPage";
import { type Agent, useAgents, useAgentVersions } from "./agents";
import {
  CASES_MAX,
  type EvaluationCase,
  type EvaluationCaseFilters,
  type EvaluationCaseResult,
  type EvaluationCaseSide,
  type EvaluationRun,
  type EvaluationRunChoice,
  type EvaluationRunSide,
  useEvaluationEstimate,
  evaluationFailure,
  inProgress,
  NO_CASE_FILTERS,
  useCancelEvaluationRun,
  useCopyEvaluationCases,
  useDeleteEvaluationCase,
  useEvaluationCases,
  useEvaluationRunResults,
  useEvaluationRuns,
  useStartEvaluationRun,
} from "./evaluation";
import { dollars } from "./format";
import { useInstructionsVersions } from "./instructions";
import { type AgentPath, CaseEditor } from "./EvaluationCaseEditor";
import { ExpectationSummary, StaleBadge } from "./EvaluationExpectations";
import { AgentSuggestions } from "./AgentSuggestions";
import { TraceBody, TraceFold } from "./Trace";

const OUTCOME_BADGES = {
  pass: "evaluationPass",
  fail: "evaluationFail",
  error: "evaluationError",
} as const;

/** A case's result on a side, or its latest result: Pass or Fail with its count (Unsteady when its repeats disagreed), or Error. */
function ResultBadges({
  result,
  unsteady,
  count,
}: {
  result: Pick<EvaluationCaseSide, "outcome">;
  unsteady: boolean;
  count: string;
}) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <Badge
        kind={OUTCOME_BADGES[result.outcome as keyof typeof OUTCOME_BADGES]}
      />
      {unsteady && <Badge kind="unsteady" />}
      {result.outcome !== "error" && (
        <span className="font-mono text-xs text-muted">{count}</span>
      )}
    </span>
  );
}

function LatestResult({ evaluationCase }: { evaluationCase: EvaluationCase }) {
  const latest = evaluationCase.latest_result;
  if (latest === null) return <span className="text-muted">Not run yet</span>;
  return (
    <ResultBadges
      result={latest}
      unsteady={latest.unsteady}
      count={`${String(latest.passed)}/${String(latest.answered)}`}
    />
  );
}

/** The Evaluation Set as a table: each case's question, Reference answer and latest result, Edit and Delete in its ⋯ menu. */
function CaseTable({
  cases,
  readOnly,
  onEdit,
  onDelete,
}: {
  cases: EvaluationCase[];
  readOnly: boolean;
  onEdit: (evaluationCase: EvaluationCase) => void;
  onDelete: (evaluationCase: EvaluationCase) => void;
}) {
  return (
    <div className={table.wrap}>
      <table className={table.table}>
        <caption className="sr-only">Evaluation Cases</caption>
        <thead>
          <tr>
            <th scope="col" className={table.th}>
              Question
            </th>
            <th scope="col" className={table.th}>
              Expectations
            </th>
            <th scope="col" className={table.th}>
              Latest result
            </th>
            {!readOnly && (
              <th scope="col" className={table.th}>
                <span className="sr-only">Actions</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {cases.map((evaluationCase) => (
            <tr key={evaluationCase.id} className={`${table.row} align-top`}>
              <td className={`${table.td} whitespace-pre-wrap`}>
                {evaluationCase.question}
              </td>
              <td className={`${table.tdMuted} whitespace-pre-wrap`}>
                <ExpectationSummary
                  sources={evaluationCase.expected_sources}
                  referenceAnswer={evaluationCase.reference_answer}
                  expectFallback={evaluationCase.expect_fallback}
                />
              </td>
              <td className={`${table.td} whitespace-nowrap`}>
                <LatestResult evaluationCase={evaluationCase} />
              </td>
              {!readOnly && (
                <td className={`${table.td} w-12 text-right`}>
                  <Menu
                    label={<Icon name="more" />}
                    triggerLabel={`More actions for ${evaluationCase.question}`}
                    menuLabel={`Actions for ${evaluationCase.question}`}
                    align="end"
                    triggerClassName={button.iconBare}
                    items={[
                      {
                        label: "Edit",
                        onSelect: () => {
                          onEdit(evaluationCase);
                        },
                      },
                      {
                        label: "Delete",
                        danger: true,
                        onSelect: () => {
                          onDelete(evaluationCase);
                        },
                      },
                    ]}
                  />
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const STATUS = {
  queued: { tone: "working", label: "Queued" },
  running: { tone: "working", label: "Running" },
  completed: { tone: "ready", label: "Completed" },
  failed: { tone: "failed", label: "Failed" },
  cancelled: { tone: "flagged", label: "Cancelled" },
} as const;

function RunStatus({ run }: { run: EvaluationRun }) {
  const status = STATUS[run.status as keyof typeof STATUS];
  return <Status tone={status.tone}>{status.label}</Status>;
}

/** A side's name: "Version 2", "Draft revision 3", a Rollout evaluation's "Rollout of Version 2", or a Suggestion's check's "Suggestion on Version 2". */
function sideName(side: EvaluationRunSide): string {
  if (side.kind === "rollout")
    return `Rollout of Version ${String(side.version_number)}`;
  if (side.kind === "suggestion")
    return `Suggestion on Version ${String(side.version_number)}`;
  return side.kind === "version"
    ? `Version ${String(side.version_number)}`
    : `Draft revision ${String(side.draft_revision)}`;
}

function instructionsName(side: EvaluationRunSide): string {
  if (side.instructions_draft) return "Instructions Draft";
  return side.instructions_version_number === null
    ? "no Project Instructions"
    : `Instructions v${String(side.instructions_version_number)}`;
}

/** What the Run answered with: "Version 1 · Instructions v1 · openai gpt-4.1-mini against Draft revision 3 · …". */
function sideSummary(run: EvaluationRun): string {
  return run.sides
    .map(
      (side) =>
        `${sideName(side)} · ${instructionsName(side)} · ${side.model_provider} ${side.model_name}`,
    )
    .join(" against ");
}

const percent = (score: number | null) =>
  score === null ? "no score" : `${String(Math.round(score * 100))}%`;

const VERDICTS = {
  expected_source: "Expected source",
  fallback: "Expect Fallback Text",
  reference_answer: "Reference answer",
  grounding: "Grounding",
} as const;

const VERDICT_OUTCOMES = {
  pass: { word: "Pass", className: "text-accent" },
  fail: { word: "Fail", className: "text-danger" },
  stale: { word: "Stale, skipped", className: "text-flag" },
} as const;

function outcomeWord(result: EvaluationCaseResult): string {
  if (result.status === "error") return "Error";
  return result.passed ? "Pass" : "Fail";
}

const repeatsWord = (repeats: number) =>
  repeats === 1 ? "1 repeat" : `${String(repeats)} repeats`;
const casesWord = (cases: number) =>
  cases === 1 ? "1 case" : `${String(cases)} cases`;
const sidesWord = (sides: number) =>
  sides === 1 ? "1 side" : `${String(sides)} sides`;

/** What a Run actually cost, split into answers and judging, and what it was estimated at. */
function costSummary(run: EvaluationRun): string {
  const { cost } = run;
  const estimate =
    cost.estimated_usd === null
      ? "no estimate"
      : `estimated ${dollars(cost.estimated_usd)}`;
  return `Cost ${dollars(cost.total_usd)}: answers ${dollars(cost.answers_usd)}, judging ${dollars(cost.judging_usd)} (${estimate})`;
}

/** A side's Evaluation score, and the cases behind it, Errors left out. */
function Score({ side, named }: { side: EvaluationRunSide; named: boolean }) {
  const counted = `${String(side.cases_passed)} passed, ${String(side.cases_failed)} failed`;
  const errors =
    side.cases_errored === 0
      ? ""
      : `, ${String(side.cases_errored)} Error${side.cases_errored === 1 ? "" : "s"} left out of the score`;
  return (
    <div
      role="group"
      aria-label={sideName(side)}
      className="flex flex-col gap-0.5"
    >
      {named && (
        <p
          className={field.label}
        >{`${side.position === "first" ? "First" : "Second"} side: ${sideName(side)}`}</p>
      )}
      <p className="font-medium text-ink">
        {side.score === null
          ? "Evaluation score: none, every case was an Error"
          : `Evaluation score: ${String(Math.round(side.score * 100))}%`}
      </p>
      <p className={text.muted}>{counted + errors}</p>
    </div>
  );
}

/** A case's result on each side: the majority of its answered repeats with the count, Unsteady, or Error. */
function CaseResultLine({
  evaluationCase,
  names,
}: {
  evaluationCase: {
    sides: EvaluationCaseSide[];
    unsteady: boolean;
    change: string | null;
  };
  names: Record<string, string> | null;
}) {
  return (
    <div
      role="group"
      aria-label="Result"
      className="flex flex-wrap items-center gap-3 text-sm"
    >
      {evaluationCase.change === "regression" && <Badge kind="regression" />}
      {evaluationCase.change === "improvement" && <Badge kind="improvement" />}
      {evaluationCase.sides.map((side) =>
        names === null ? (
          <SideOutcome
            key={side.position}
            side={side}
            unsteady={evaluationCase.unsteady}
          />
        ) : (
          <span
            key={side.position}
            className="inline-flex items-center gap-1.5"
          >
            <span className="font-medium">{names[side.position]}:</span>
            <SideOutcome side={side} unsteady={evaluationCase.unsteady} />
          </span>
        ),
      )}
    </div>
  );
}

/** A case's outcome on one side: Pass or Fail with its count (Unsteady when its repeats disagreed), or Error. */
function SideOutcome({
  side,
  unsteady,
}: {
  side: EvaluationCaseSide;
  unsteady: boolean;
}) {
  if (side.outcome === "error")
    return (
      <span className="inline-flex items-center gap-1.5">
        <Badge kind="evaluationError" />
        <span className={text.muted}>
          Every repeat errored; left out of the score.
        </span>
      </span>
    );
  return (
    <ResultBadges
      result={side}
      unsteady={unsteady}
      count={`${String(side.passed)}/${String(side.answered)} repeats passed`}
    />
  );
}

/** One answer of a case: its repeat's outcome, Verdicts with the judge's reasons, and its Trace. */
function CaseAnswer({ result }: { result: EvaluationCaseResult }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm">
        <span className="font-medium">{`Repeat ${String(result.repeat)}: `}</span>
        <span
          className={
            result.status === "error" || result.passed === false
              ? "text-danger"
              : "text-accent"
          }
        >
          {outcomeWord(result)}
        </span>
      </p>
      {result.answer !== null && (
        <div>
          <p className={field.label}>Answer</p>
          <p className="mt-1 rounded-xl bg-sunken px-3.5 py-2.5 text-sm whitespace-pre-wrap text-ink">
            {result.answer}
          </p>
        </div>
      )}
      {result.error_reason !== null && (
        <Notice tone="error">{result.error_reason}</Notice>
      )}
      {result.verdicts.length > 0 && (
        <ul aria-label="Verdicts" className="flex flex-col gap-1 text-sm">
          {result.verdicts.map((verdict, index) => {
            const outcome =
              VERDICT_OUTCOMES[
                verdict.outcome as keyof typeof VERDICT_OUTCOMES
              ];
            return (
              <li key={index}>
                <span className="font-medium">
                  {VERDICTS[verdict.kind as keyof typeof VERDICTS]}:{" "}
                </span>
                <span className={outcome.className}>{outcome.word}</span>
                <span className="text-ink-2">. {verdict.reason}</span>
              </li>
            );
          })}
        </ul>
      )}
      {result.trace !== null && (
        <TraceFold
          summary={`${String(result.trace.input_tokens)} in · ${String(result.trace.output_tokens)} out · ${String(result.trace.latency_ms)} ms`}
        >
          <TraceBody trace={result.trace} />
        </TraceFold>
      )}
    </div>
  );
}

/** How many Regressions and improvements a Run found, in words. */
function changesSummary(cases: { change: string | null }[]): string {
  const regressions = cases.filter(
    (evaluationCase) => evaluationCase.change === "regression",
  ).length;
  const improvements = cases.filter(
    (evaluationCase) => evaluationCase.change === "improvement",
  ).length;
  const regressionWords =
    regressions === 1 ? "1 Regression" : `${String(regressions)} Regressions`;
  const improvementWords =
    improvements === 1
      ? "1 improvement"
      : `${String(improvements)} improvements`;
  return `${regressionWords} and ${improvementWords}: the cases that pass on the first side and fail on the second come first.`;
}

/**
 * A Run: its status and progress while it runs (with Cancel), then each side's Evaluation score and
 * each case, Regressions first, then improvements, then the rest, with every side's answers.
 */
function RunDetail({
  path,
  runId,
  readOnly,
  focusCase,
}: {
  path: AgentPath;
  runId: string;
  readOnly: boolean;
  focusCase: string | undefined;
}) {
  const headingId = useId();
  const focused = useRef<HTMLLIElement>(null);
  const results = useEvaluationRunResults(path, runId);
  const cancel = useCancelEvaluationRun(path);
  const loaded = results.data !== undefined;
  // A link to a case's result scrolls it into view once the Run has loaded.
  useEffect(() => {
    focused.current?.scrollIntoView({ block: "center" });
  }, [loaded]);
  if (results.isError)
    return (
      <Notice tone="error">
        The Run could not be loaded. Try again shortly.
      </Notice>
    );
  if (results.data === undefined) return <Skeleton label="Loading the Run" />;
  const { run, cases } = results.data;
  const twoSided = run.sides.length > 1;
  const names = twoSided
    ? Object.fromEntries(
        run.sides.map((side) => [side.position, sideName(side)]),
      )
    : null;
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h3 id={headingId} className={text.subheading}>
            Run of {formatTime(run.created_at)}
          </h3>
          <p className={text.muted}>
            <RunStatus run={run} /> · {sideSummary(run)} · judged by{" "}
            {run.judge_provider} {run.judge_model} · {repeatsWord(run.repeats)}
          </p>
          <p className={text.muted}>{costSummary(run)}</p>
        </div>
        {inProgress(run) && !readOnly && (
          <button
            type="button"
            className={button.secondary}
            disabled={cancel.isPending}
            onClick={() => {
              cancel.mutate(run.id);
            }}
          >
            Cancel Run
          </button>
        )}
      </div>
      <FormError message={evaluationFailure(cancel.error)} />
      {run.stale && (
        <Notice tone="warning">
          The Draft has changed since this Run: its results describe an earlier
          Draft revision.
        </Notice>
      )}
      {run.status === "cancelled" && (
        <Notice tone="info">
          This Run was cancelled. The answers it gave before stopping are kept.
        </Notice>
      )}
      {!inProgress(run) && (
        <div className="flex flex-wrap gap-x-8 gap-y-3">
          {run.sides.map((side) => (
            <Score key={side.position} side={side} named={twoSided} />
          ))}
        </div>
      )}
      {inProgress(run) && (
        <Meter
          label="Answers given"
          value={run.progress.done}
          max={Math.max(run.progress.total, 1)}
          unit="answers"
          progress
        />
      )}
      {run.error_message !== null && (
        <Notice tone="error">{run.error_message}</Notice>
      )}
      {!inProgress(run) && twoSided && (
        <p className={text.muted}>{changesSummary(cases)}</p>
      )}
      {!inProgress(run) && (
        <ol aria-label="Cases" className="flex flex-col gap-4">
          {cases.map((evaluationCase, index) => (
            <li
              key={index}
              ref={evaluationCase.id === focusCase ? focused : undefined}
              aria-current={
                evaluationCase.id === focusCase ? "true" : undefined
              }
              className={`${surface.panel} flex flex-col gap-3 ${evaluationCase.id === focusCase ? "ring-2 ring-accent" : ""}`}
            >
              <h4 className="font-medium text-ink">
                {evaluationCase.question}
              </h4>
              {evaluationCase.stale_expectation && (
                <p className="inline-flex flex-wrap items-center gap-1.5 text-sm text-ink-2">
                  <StaleBadge title="An Expected source's Document or passage is gone" />
                  An Expected source&apos;s Document or passage is gone, so it
                  was skipped: neither pass nor fail. Fix the case in the
                  Evaluation Set.
                </p>
              )}
              {evaluationCase.reference_answer !== null && (
                <p className="text-sm text-ink-2">
                  <span className="font-medium">Reference answer: </span>
                  {evaluationCase.reference_answer}
                </p>
              )}
              {evaluationCase.expect_fallback && (
                <p className="text-sm text-ink-2">Expects the Fallback Text.</p>
              )}
              {evaluationCase.expected_sources.length > 0 && (
                <div className="text-sm text-ink-2">
                  <p className="font-medium">Expected sources:</p>
                  <ExpectationSummary
                    sources={evaluationCase.expected_sources}
                    referenceAnswer={null}
                    expectFallback={false}
                  />
                </div>
              )}
              <CaseResultLine evaluationCase={evaluationCase} names={names} />
              {names === null
                ? evaluationCase.results.map((result) => (
                    <CaseAnswer
                      key={`${result.position}-${String(result.repeat)}`}
                      result={result}
                    />
                  ))
                : run.sides.map((side) => (
                    <div
                      key={side.position}
                      role="group"
                      aria-label={`Answers of ${sideName(side)}`}
                      className="flex flex-col gap-3"
                    >
                      <p className={field.label}>{sideName(side)}</p>
                      {evaluationCase.results
                        .filter((result) => result.position === side.position)
                        .map((result) => (
                          <CaseAnswer
                            key={String(result.repeat)}
                            result={result}
                          />
                        ))}
                    </div>
                  ))}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/** The Agent's Runs, newest first, with their status, sides and scores; choosing one shows it below. */
function RunList({
  runs,
  chosen,
  onChoose,
}: {
  runs: EvaluationRun[];
  chosen: string | null;
  onChoose: (runId: string) => void;
}) {
  return (
    <ul
      aria-label="Evaluation Runs"
      className={`${surface.card} divide-y divide-line-soft`}
    >
      {runs.map((run) => (
        <li
          key={run.id}
          className={`flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3 text-sm ${run.id === chosen ? "bg-accent-soft" : ""}`}
        >
          <button
            type="button"
            className={button.quiet}
            aria-current={run.id === chosen ? "true" : undefined}
            onClick={() => {
              onChoose(run.id);
            }}
          >
            Run of {formatTime(run.created_at)}
          </button>
          <RunStatus run={run} />
          {run.kind === "rollout" && (
            <span className="font-medium text-ink-2">Rollout evaluation</span>
          )}
          {run.kind === "suggestion" && (
            <span className="font-medium text-ink-2">
              Suggestion&apos;s check
            </span>
          )}
          {run.stale && <Badge kind="runStale" />}
          <span className="text-ink-2">
            {run.sides
              .map(
                (side) =>
                  `${sideName(side)}: ${inProgress(run) ? "running" : percent(side.score)}`,
              )
              .join(" · ")}
          </span>
          <span className="font-mono text-xs text-muted">
            {run.progress.done} / {run.progress.total} answers
          </span>
          <span className="font-mono text-xs text-muted">
            Cost {dollars(run.cost.total_usd)}
          </span>
        </li>
      ))}
    </ul>
  );
}

const DRAFT_SIDE = "draft";
const NO_SECOND_SIDE = "";
const CURRENT_INSTRUCTIONS = "current";
const INSTRUCTIONS_DRAFT = "instructions-draft";

/** The estimated Cost of the Run the Evaluate dialog would start, read again as the choices change. */
function EstimatedCost({
  path,
  choice,
}: {
  path: AgentPath;
  choice: EvaluationRunChoice | null;
}) {
  const estimate = useEvaluationEstimate(path, choice);
  let figure: string;
  let hint: string | null = null;
  if (choice === null) {
    figure = "Choose two different sides to see the estimated Cost.";
  } else if (estimate.isError) {
    figure = `The Cost could not be estimated. ${evaluationFailure(estimate.error) as string}`;
  } else if (estimate.data === undefined) {
    figure = "Estimating the Cost…";
  } else if (
    estimate.data.total_usd === null ||
    estimate.data.answers_usd === null ||
    estimate.data.judging_usd === null
  ) {
    figure =
      "The Cost can't be estimated: a model this Run uses has no price set.";
  } else {
    const { cases, sides, repeats } = estimate.data;
    figure = `About ${dollars(estimate.data.total_usd)}: answers ${dollars(estimate.data.answers_usd)}, judging ${dollars(estimate.data.judging_usd)}`;
    hint = `${casesWord(cases)} × ${sidesWord(sides)} × ${repeatsWord(repeats)}, at each side's mean Cost per reply over the last 30 days, plus judging every answer. The Run records what it actually costs.`;
  }
  return (
    <div>
      <p className={field.label}>Estimated Cost</p>
      <p
        role="status"
        aria-label="Estimated Cost"
        className="mt-1 text-sm text-ink"
      >
        {figure}
      </p>
      {hint !== null && <p className={field.hint}>{hint}</p>}
    </div>
  );
}

/**
 * The Evaluate dialog: the two sides (the Live Version against the Draft by default, or the Draft
 * alone for an Agent never Published) and the Instructions the Draft answers with.
 */
function EvaluateDialog({
  agent,
  organisationId,
  onStarted,
  onClose,
}: {
  agent: Agent;
  organisationId: string;
  onStarted: (runId: string) => void;
  onClose: () => void;
}) {
  const path = {
    organisation_id: organisationId,
    project_id: agent.project_id,
    agent_id: agent.id,
  };
  const formId = useId();
  const sameId = useId();
  const versions = useAgentVersions(organisationId, agent.project_id, agent.id);
  const instructions = useInstructionsVersions(
    organisationId,
    agent.project_id,
  );
  const start = useStartEvaluationRun(path);
  const live = agent.live_version;
  const [first, setFirst] = useState(live === null ? DRAFT_SIDE : live.id);
  const [second, setSecond] = useState(
    live === null ? NO_SECOND_SIDE : DRAFT_SIDE,
  );
  const [draftInstructions, setDraftInstructions] =
    useState(CURRENT_INSTRUCTIONS);
  const same = first === second;
  const versionOptions =
    versions.data?.versions ??
    (live === null ? [] : [{ id: live.id, number: live.number }]);
  const sideOptions = [
    { value: DRAFT_SIDE, label: "Draft" },
    ...versionOptions.map((version) => ({
      value: version.id,
      label: `Version ${String(version.number)}${version.id === live?.id ? " (Live)" : ""}`,
    })),
  ];
  const history = instructions.data;
  const current = history?.versions.find(
    (version) => version.id === history.current_version_id,
  );
  const side = (
    value: string,
  ): NonNullable<EvaluationRunChoice["sides"]>[number] =>
    value === DRAFT_SIDE
      ? { kind: "draft" }
      : { kind: "version", version_id: value };
  const choice: EvaluationRunChoice = {
    sides:
      second === NO_SECOND_SIDE ? [side(first)] : [side(first), side(second)],
    instructions_draft: draftInstructions === INSTRUCTIONS_DRAFT,
    instructions_version_id:
      draftInstructions === CURRENT_INSTRUCTIONS ||
      draftInstructions === INSTRUCTIONS_DRAFT
        ? null
        : draftInstructions,
  };

  function submit(event: SubmitEvent) {
    event.preventDefault();
    start.mutate(choice, {
      onSuccess: (run) => {
        onStarted(run.id);
      },
    });
  }

  return (
    <Dialog
      open
      title="Evaluate"
      description="Both sides answer every case at the same moment, against the same Knowledge Base. A case that passes on the first side and fails on the second is a Regression."
      onClose={onClose}
      closeButton={false}
      footer={
        <>
          <button type="button" className={button.secondary} onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            form={formId}
            className={button.primary}
            disabled={same || start.isPending}
          >
            Start Run
          </button>
        </>
      }
    >
      <form
        id={formId}
        aria-label="Evaluate"
        className="flex flex-col gap-4"
        onSubmit={submit}
      >
        <FormError message={evaluationFailure(start.error)} />
        <label className={field.label}>
          First side
          <select
            className={field.select}
            value={first}
            aria-invalid={same}
            aria-describedby={same ? sameId : undefined}
            onChange={(event) => {
              setFirst(event.target.value);
            }}
          >
            {sideOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className={field.label}>
          Second side
          <select
            className={field.select}
            value={second}
            aria-invalid={same}
            aria-describedby={same ? sameId : undefined}
            onChange={(event) => {
              setSecond(event.target.value);
            }}
          >
            <option value={NO_SECOND_SIDE}>
              None: the first side runs alone
            </option>
            {sideOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        {same && (
          <p id={sameId} className={field.error}>
            Choose two different sides.
          </p>
        )}
        {(first === DRAFT_SIDE || second === DRAFT_SIDE) && (
          <div>
            <label className={field.label}>
              Draft&apos;s Instructions
              <select
                className={field.select}
                value={draftInstructions}
                onChange={(event) => {
                  setDraftInstructions(event.target.value);
                }}
              >
                <option value={CURRENT_INSTRUCTIONS}>
                  {current === undefined
                    ? "Current Instructions Version (none yet)"
                    : `Current Instructions Version (v${String(current.number)})`}
                </option>
                <option value={INSTRUCTIONS_DRAFT}>Instructions Draft</option>
                {(instructions.data?.versions ?? []).map((version) => (
                  <option key={version.id} value={version.id}>
                    Instructions v{version.number}
                  </option>
                ))}
              </select>
            </label>
            <p className={field.hint}>
              A Version always answers with the Instructions it pins.
            </p>
          </div>
        )}
        <EstimatedCost path={path} choice={same ? null : choice} />
      </form>
    </Dialog>
  );
}

const KIND_LABELS = {
  expected_source: "Expected source",
  reference_answer: "Reference answer",
  fallback: "Expect Fallback Text",
} as const;
const RESULT_OPTIONS = [
  { value: "", label: "Any result" },
  { value: "pass", label: "Pass" },
  { value: "fail", label: "Fail" },
  { value: "unsteady", label: "Unsteady" },
  { value: "error", label: "Error" },
  { value: "not_run", label: "Not run" },
] as const;

/** The set's toolbar: search the questions, and filter by expectation kind, the Stale flag and the latest result. */
function CaseFilters({
  filters,
  onChange,
}: {
  filters: EvaluationCaseFilters;
  onChange: (filters: EvaluationCaseFilters) => void;
}) {
  const filtered =
    filters.q !== "" ||
    filters.kind !== "" ||
    filters.stale !== "" ||
    filters.result !== "";
  return (
    <div role="search" className={layout.toolbar}>
      <label className={`${field.search} w-full sm:w-64`}>
        <Icon name="search" size={14} />
        <input
          type="search"
          aria-label="Search the questions"
          placeholder="Search cases"
          value={filters.q}
          onChange={(event) => {
            onChange({ ...filters, q: event.target.value });
          }}
          className="min-w-0 flex-1 bg-transparent text-ink placeholder:text-muted focus:outline-none"
        />
      </label>
      <Segmented
        label="Filter by latest result"
        options={RESULT_OPTIONS}
        value={filters.result}
        onChange={(value) => {
          onChange({ ...filters, result: value });
        }}
      />
      <span className="ml-auto flex flex-wrap items-center gap-3">
        {filtered && (
          <button
            type="button"
            className={button.ghost}
            onClick={() => {
              onChange(NO_CASE_FILTERS);
            }}
          >
            Clear filters
          </button>
        )}
        <select
          aria-label="Expectation"
          value={filters.kind}
          onChange={(event) => {
            onChange({
              ...filters,
              kind: event.target.value as EvaluationCaseFilters["kind"],
            });
          }}
          className={field.pill}
        >
          <option value="">Any expectation</option>
          {Object.entries(KIND_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          aria-label="Stale expectation"
          value={filters.stale}
          onChange={(event) => {
            onChange({
              ...filters,
              stale: event.target.value as EvaluationCaseFilters["stale"],
            });
          }}
          className={field.pill}
        >
          <option value="">Stale or not</option>
          <option value="true">Stale expectation</option>
          <option value="false">No Stale expectation</option>
        </select>
      </span>
    </div>
  );
}

/** One Agent's cases to copy, each with a tick box; "Select all" ticks every one. */
function CopyChoices({
  path,
  chosen,
  onChange,
}: {
  path: AgentPath;
  chosen: Set<string>;
  onChange: (chosen: Set<string>) => void;
}) {
  const cases = useEvaluationCases(path);
  if (cases.isError)
    return (
      <Notice tone="error">
        That Agent&apos;s Evaluation Set could not be loaded. Try again shortly.
      </Notice>
    );
  if (cases.data === undefined) return <Skeleton label="Loading the cases" />;
  if (cases.data.length === 0)
    return (
      <p className={text.muted}>That Agent&apos;s Evaluation Set is empty.</p>
    );
  const all = cases.data.map((evaluationCase) => evaluationCase.id);
  const everyOne = all.every((id) => chosen.has(id));
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className={field.label}>Cases to copy</legend>
      <label className="flex items-center gap-2 text-sm font-medium text-ink">
        <input
          type="checkbox"
          className={field.checkbox}
          checked={everyOne}
          onChange={() => {
            onChange(everyOne ? new Set() : new Set(all));
          }}
        />
        Select all ({cases.data.length})
      </label>
      <ul className="flex max-h-72 flex-col gap-1.5 overflow-y-auto">
        {cases.data.map((evaluationCase) => (
          <li key={evaluationCase.id}>
            <label className="flex items-start gap-2 rounded-xl bg-sunken px-3.5 py-2 text-sm text-ink">
              <input
                type="checkbox"
                className={`${field.checkbox} mt-0.5`}
                checked={chosen.has(evaluationCase.id)}
                onChange={() => {
                  const next = new Set(chosen);
                  if (!next.delete(evaluationCase.id))
                    next.add(evaluationCase.id);
                  onChange(next);
                }}
              />
              <span className="whitespace-pre-wrap">
                {evaluationCase.question}
              </span>
            </label>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}

/** Copy from another Agent: choose an Agent of the Project, then its cases; they arrive as independent copies. */
function CopyDialog({
  agent,
  organisationId,
  onClose,
}: {
  agent: Agent;
  organisationId: string;
  onClose: () => void;
}) {
  const path = {
    organisation_id: organisationId,
    project_id: agent.project_id,
    agent_id: agent.id,
  };
  const formId = useId();
  const toast = useToast();
  const agents = useAgents(organisationId, agent.project_id);
  const others = (agents.data ?? []).filter((other) => other.id !== agent.id);
  const copy = useCopyEvaluationCases(path);
  const [from, setFrom] = useState("");
  const [chosen, setChosen] = useState<Set<string>>(() => new Set());

  function submit(event: SubmitEvent) {
    event.preventDefault();
    copy.mutate(
      { agent_id: from, case_ids: [...chosen] },
      {
        onSuccess: (copies) => {
          toast.show(
            copies.length === 1
              ? "Copied 1 case."
              : `Copied ${String(copies.length)} cases.`,
          );
          onClose();
        },
      },
    );
  }

  return (
    <Dialog
      open
      title="Copy from another Agent"
      description="The cases arrive as independent copies: changing one set later leaves the other as it is."
      onClose={onClose}
      closeButton={false}
      footer={
        <>
          <button type="button" className={button.secondary} onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            form={formId}
            className={button.primary}
            disabled={chosen.size === 0 || copy.isPending}
          >
            {chosen.size === 1
              ? "Copy 1 case"
              : `Copy ${String(chosen.size)} cases`}
          </button>
        </>
      }
    >
      <form
        id={formId}
        aria-label="Copy from another Agent"
        className="flex flex-col gap-4"
        onSubmit={submit}
      >
        <FormError message={evaluationFailure(copy.error)} />
        {agents.isError && (
          <Notice tone="error">
            The Agents could not be loaded. Try again shortly.
          </Notice>
        )}
        {agents.data !== undefined && others.length === 0 && (
          <p className={text.muted}>
            This Project has no other Agent to copy from.
          </p>
        )}
        {others.length > 0 && (
          <label className={field.label}>
            Agent
            <select
              className={field.select}
              value={from}
              onChange={(event) => {
                setFrom(event.target.value);
                setChosen(new Set());
              }}
            >
              <option value="">Choose an Agent</option>
              {others.map((other) => (
                <option key={other.id} value={other.id}>
                  {other.name}
                </option>
              ))}
            </select>
          </label>
        )}
        {from !== "" && (
          <CopyChoices
            key={from}
            path={{ ...path, agent_id: from }}
            chosen={chosen}
            onChange={setChosen}
          />
        )}
      </form>
    </Dialog>
  );
}

/**
 * The Evaluation view: the Agent's Evaluation Set with its case editor and Evaluate, then its Runs
 * and the chosen Run's answers with their Verdicts and Traces. An archived Agent's set is read only.
 */
function EvaluationSetAndRuns({
  agent,
  organisationId,
  focus,
}: {
  agent: Agent;
  organisationId: string;
  focus: EvaluationFocus;
}) {
  const path = {
    organisation_id: organisationId,
    project_id: agent.project_id,
    agent_id: agent.id,
  };
  const setHeadingId = useId();
  const runsHeadingId = useId();
  const archived = agent.archived_at !== null;
  const [filters, setFilters] =
    useState<EvaluationCaseFilters>(NO_CASE_FILTERS);
  const allCases = useEvaluationCases(path);
  const cases = useEvaluationCases(path, filters);
  const runs = useEvaluationRuns(path);
  const remove = useDeleteEvaluationCase(path);
  const [evaluating, setEvaluating] = useState(false);
  const [copying, setCopying] = useState(false);
  const [editing, setEditing] = useState<EvaluationCase | "new" | null>(null);
  const [deleting, setDeleting] = useState<EvaluationCase | null>(null);
  const [chosen, setChosen] = useState<string | null>(focus.run ?? null);
  const shownRun = chosen ?? runs.data?.[0]?.id ?? null;
  const running = (runs.data ?? []).some(inProgress);
  const held = allCases.data?.length;
  const noCases = (held ?? 0) === 0;
  const full = held !== undefined && held >= CASES_MAX;

  const newCase = (
    <button
      type="button"
      className={button.secondary}
      disabled={full}
      onClick={() => {
        setEditing("new");
      }}
    >
      New case
    </button>
  );
  const copyCases = (
    <button
      type="button"
      className={button.secondary}
      disabled={full}
      onClick={() => {
        setCopying(true);
      }}
    >
      Copy from another Agent
    </button>
  );

  return (
    <div className="flex flex-col gap-8">
      {archived && (
        <Notice tone="info">
          This Agent is archived: its Evaluation Set and Runs are read only, and
          it starts no Run.
        </Notice>
      )}
      <section aria-labelledby={setHeadingId} className="flex flex-col gap-4">
        <PageHeader
          level={2}
          headingId={setHeadingId}
          title="Evaluation Set"
          description="Questions this Agent is measured against, each with what a good answer says. Evaluate answers them with two sides, the Live Version and the Draft by default."
          actions={
            !archived && (
              <>
                {newCase}
                {copyCases}
                <button
                  type="button"
                  className={button.primary}
                  disabled={noCases || running}
                  onClick={() => {
                    setEvaluating(true);
                  }}
                >
                  {running ? "Evaluating…" : "Evaluate"}
                </button>
              </>
            )
          }
        />
        {held !== undefined && held > 0 && (
          <Meter
            label="Cases in the set"
            value={held}
            max={CASES_MAX}
            unit="cases"
          />
        )}
        {full && !archived && (
          <Notice tone="warning">
            This Evaluation Set holds the most it can, {CASES_MAX} cases, so a
            Run stays bounded in time and Cost. Delete cases before adding more.
          </Notice>
        )}
        <FormError message={evaluationFailure(remove.error)} />
        {allCases.isPending && <Skeleton label="Loading the Evaluation Set" />}
        {allCases.isError && (
          <EmptyState
            tone="error"
            icon="agents"
            title="The Evaluation Set could not be loaded"
            description="Try again shortly."
          />
        )}
        {allCases.data && allCases.data.length === 0 && (
          <EmptyState
            icon="agents"
            level={3}
            title="No Evaluation Cases yet"
            description={
              archived
                ? "This Agent's Evaluation Set is empty."
                : "Write a question and what a good answer says, add one from an Agent Message in the Conversations viewer or the Playground, or copy cases from another Agent."
            }
            action={archived ? undefined : newCase}
          />
        )}
        {allCases.data && allCases.data.length > 0 && (
          <>
            <CaseFilters filters={filters} onChange={setFilters} />
            {cases.isPending && (
              <Skeleton label="Filtering the Evaluation Set" />
            )}
            {cases.isError && (
              <Notice tone="error">
                The Evaluation Set could not be filtered. Try again shortly.
              </Notice>
            )}
            {cases.data && cases.data.length === 0 && (
              <EmptyState
                icon="search"
                level={3}
                title="No cases match"
                description="Change the search or the filters to see more of the set."
              />
            )}
            {cases.data && cases.data.length > 0 && (
              <CaseTable
                cases={cases.data}
                readOnly={archived}
                onEdit={setEditing}
                onDelete={setDeleting}
              />
            )}
          </>
        )}
      </section>
      <section aria-labelledby={runsHeadingId} className="flex flex-col gap-4">
        <h2 id={runsHeadingId} className={text.heading}>
          Runs
        </h2>
        {runs.isError && (
          <Notice tone="error">
            The Runs could not be loaded. Try again shortly.
          </Notice>
        )}
        {runs.data && runs.data.length === 0 && (
          <p className={text.muted}>
            No Runs yet. Evaluate to answer the set with the Draft.
          </p>
        )}
        {runs.data && runs.data.length > 0 && (
          <RunList runs={runs.data} chosen={shownRun} onChoose={setChosen} />
        )}
        {shownRun !== null && (
          <RunDetail
            key={shownRun}
            path={path}
            runId={shownRun}
            readOnly={archived}
            focusCase={shownRun === focus.run ? focus.case : undefined}
          />
        )}
      </section>
      {evaluating && (
        <EvaluateDialog
          agent={agent}
          organisationId={organisationId}
          onStarted={(runId) => {
            setEvaluating(false);
            setChosen(runId);
          }}
          onClose={() => {
            setEvaluating(false);
          }}
        />
      )}
      {copying && (
        <CopyDialog
          agent={agent}
          organisationId={organisationId}
          onClose={() => {
            setCopying(false);
          }}
        />
      )}
      {editing !== null && (
        <CaseEditor
          path={path}
          editing={editing === "new" ? null : editing}
          onClose={() => {
            setEditing(null);
          }}
        />
      )}
      {deleting !== null && (
        <ConfirmDialog
          open
          title="Delete this Evaluation Case?"
          confirmLabel="Delete case"
          destructive
          busy={remove.isPending}
          onCancel={() => {
            setDeleting(null);
          }}
          onConfirm={() => {
            remove.mutate(deleting.id, {
              onSettled: () => {
                setDeleting(null);
              },
            });
          }}
        >
          “{deleting.question}” leaves the Evaluation Set. Past Runs keep their
          copy of it.
        </ConfirmDialog>
      )}
    </div>
  );
}

/** Where a link opens the Evaluation view: a Run, and a case of it as the Run copied it. */
export type EvaluationFocus = { run?: string; case?: string };

/** The Evaluation view's search: `?run=` and `?case=`, each kept only when it is text. */
export function evaluationSearch(
  search: Record<string, unknown>,
): EvaluationFocus {
  const focus: EvaluationFocus = {};
  if (typeof search.run === "string") focus.run = search.run;
  if (typeof search.case === "string") focus.case = search.case;
  return focus;
}

const EVALUATION_TABS = [
  { value: "set", label: "Evaluation Set and Runs" },
  { value: "suggestions", label: "Suggestions" },
] as const;

/**
 * The Agent's Evaluation view: its Evaluation Set and Runs, and beside them its Suggestions, where
 * failures turn into proposed changes.
 */
export function AgentEvaluation({
  agent,
  organisationId,
  focus,
}: {
  agent: Agent;
  organisationId: string;
  focus: EvaluationFocus;
}) {
  const [tab, setTab] =
    useState<(typeof EVALUATION_TABS)[number]["value"]>("set");
  return (
    <div className="flex flex-col gap-6">
      <Segmented
        label="Evaluation view"
        options={EVALUATION_TABS}
        value={tab}
        onChange={setTab}
      />
      {tab === "set" ? (
        <EvaluationSetAndRuns
          agent={agent}
          organisationId={organisationId}
          focus={focus}
        />
      ) : (
        <AgentSuggestions agent={agent} organisationId={organisationId} />
      )}
    </div>
  );
}
