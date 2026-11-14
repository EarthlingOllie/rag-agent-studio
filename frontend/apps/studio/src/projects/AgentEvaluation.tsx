import { type SubmitEvent, useId, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import {
  ConfirmDialog,
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
  field,
  surface,
  table,
  text,
} from "../design";
import { formatTime } from "../settings/AuditPage";
import type { Agent } from "./agents";
import {
  type EvaluationCase,
  type EvaluationCaseResult,
  type EvaluationRun,
  evaluationFailure,
  inProgress,
  useDeleteEvaluationCase,
  useEvaluationCases,
  useEvaluationRunResults,
  useEvaluationRuns,
  useSaveEvaluationCase,
  useStartEvaluationRun,
} from "./evaluation";
import { TraceBody, TraceFold } from "./Trace";

type AgentPath = { organisation_id: string; project_id: string; agent_id: string };

const NEEDS_REFERENCE = "Write a Reference answer: a case needs at least one expectation.";

/** The case editor: a question and its Reference answer, in a dialog. */
function CaseEditor({ path, editing, onClose }: { path: AgentPath; editing: EvaluationCase | null; onClose: () => void }) {
  const formId = useId();
  const hintId = useId();
  const errorId = useId();
  const [question, setQuestion] = useState(editing?.question ?? "");
  const [reference, setReference] = useState(editing?.reference_answer ?? "");
  const [missing, setMissing] = useState(false);
  const save = useSaveEvaluationCase(path, editing?.id ?? null);
  const title = editing === null ? "New Evaluation Case" : "Edit Evaluation Case";

  function submit(event: SubmitEvent) {
    event.preventDefault();
    if (reference.trim() === "") {
      setMissing(true);
      return;
    }
    setMissing(false);
    save.mutate({ question, reference_answer: reference }, { onSuccess: onClose });
  }

  return (
    <Dialog
      open
      title={title}
      description="One standalone question, and what a good answer to it says."
      onClose={onClose}
      closeButton={false}
      footer={
        <>
          <button type="button" className={button.secondary} onClick={onClose}>
            Cancel
          </button>
          <button type="submit" form={formId} className={button.primary} disabled={save.isPending}>
            Save case
          </button>
        </>
      }
    >
      <form id={formId} aria-label={title} className="flex flex-col gap-4" onSubmit={submit}>
        <FormError message={evaluationFailure(save.error)} />
        <label className={field.label}>
          Question
          <textarea
            className={field.textarea}
            rows={3}
            required
            maxLength={4000}
            value={question}
            onChange={(event) => {
              setQuestion(event.target.value);
            }}
          />
        </label>
        <div>
          <label className={field.label}>
            Reference answer
            <textarea
              className={field.textarea}
              rows={4}
              maxLength={4000}
              aria-invalid={missing}
              aria-describedby={missing ? `${hintId} ${errorId}` : hintId}
              value={reference}
              onChange={(event) => {
                setReference(event.target.value);
              }}
            />
          </label>
          <p id={hintId} className={field.hint}>
            What a good answer says, in your own words. The judge checks its meaning, not its wording.
          </p>
          {missing && (
            <p id={errorId} className={field.error}>
              {NEEDS_REFERENCE}
            </p>
          )}
        </div>
      </form>
    </Dialog>
  );
}

/** The Evaluation Set as a table: each case's question and Reference answer, Edit and Delete in its ⋯ menu. */
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
              Reference answer
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
              <td className={`${table.td} whitespace-pre-wrap`}>{evaluationCase.question}</td>
              <td className={`${table.tdMuted} whitespace-pre-wrap`}>{evaluationCase.reference_answer}</td>
              {!readOnly && (
                <td className={`${table.td} w-12 text-right`}>
                  <Menu
                    label={<Icon name="more" />}
                    triggerLabel={`More actions for ${evaluationCase.question}`}
                    menuLabel={`Actions for ${evaluationCase.question}`}
                    align="end"
                    triggerClassName={button.iconBare}
                    items={[
                      { label: "Edit", onSelect: () => { onEdit(evaluationCase); } },
                      { label: "Delete", danger: true, onSelect: () => { onDelete(evaluationCase); } },
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
} as const;

function RunStatus({ run }: { run: EvaluationRun }) {
  const status = STATUS[run.status as keyof typeof STATUS];
  return <Status tone={status.tone}>{status.label}</Status>;
}

/** What the Run answered with: "Draft revision 3 · Instructions v1 · openai gpt-4.1-mini". */
function sideSummary(run: EvaluationRun): string {
  return run.sides
    .map((side) => {
      const answering = `Draft revision ${String(side.draft_revision)}`;
      const instructions =
        side.instructions_version_number === null ? "no Project Instructions" : `Instructions v${String(side.instructions_version_number)}`;
      return `${answering} · ${instructions} · ${side.model_provider} ${side.model_name}`;
    })
    .join("; ");
}

const VERDICTS = { reference_answer: "Reference answer", grounding: "Grounding" } as const;

function outcomeWord(result: EvaluationCaseResult): string {
  if (result.status === "error") return "Error";
  return result.passed ? "Pass" : "Fail";
}

/** One answer of a case: its outcome, Verdicts with the judge's reasons, and its Trace. */
function CaseAnswer({ result }: { result: EvaluationCaseResult }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm">
        <span className="font-medium">Outcome: </span>
        <span className={result.status === "error" || result.passed === false ? "text-danger" : "text-accent"}>{outcomeWord(result)}</span>
      </p>
      {result.answer !== null && (
        <div>
          <p className={field.label}>Answer</p>
          <p className="mt-1 rounded-xl bg-sunken px-3.5 py-2.5 text-sm whitespace-pre-wrap text-ink">{result.answer}</p>
        </div>
      )}
      {result.error_reason !== null && <Notice tone="error">{result.error_reason}</Notice>}
      {result.verdicts.length > 0 && (
        <ul aria-label="Verdicts" className="flex flex-col gap-1 text-sm">
          {result.verdicts.map((verdict) => (
            <li key={verdict.kind}>
              <span className="font-medium">{VERDICTS[verdict.kind as keyof typeof VERDICTS]}: </span>
              <span className={verdict.outcome === "pass" ? "text-accent" : "text-danger"}>{verdict.outcome === "pass" ? "Pass" : "Fail"}</span>
              <span className="text-ink-2">. {verdict.reason}</span>
            </li>
          ))}
        </ul>
      )}
      {result.trace !== null && (
        <TraceFold summary={`${String(result.trace.input_tokens)} in · ${String(result.trace.output_tokens)} out · ${String(result.trace.latency_ms)} ms`}>
          <TraceBody trace={result.trace} />
        </TraceFold>
      )}
    </div>
  );
}

/** A Run: its status and progress while it runs, then each case with its answers. */
function RunDetail({ path, runId }: { path: AgentPath; runId: string }) {
  const headingId = useId();
  const results = useEvaluationRunResults(path, runId);
  if (results.isError) return <Notice tone="error">The Run could not be loaded. Try again shortly.</Notice>;
  if (results.data === undefined) return <Skeleton label="Loading the Run" />;
  const { run, cases } = results.data;
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h3 id={headingId} className={text.subheading}>
          Run of {formatTime(run.created_at)}
        </h3>
        <p className={text.muted}>
          <RunStatus run={run} /> · {sideSummary(run)} · judged by {run.judge_provider} {run.judge_model}
        </p>
      </div>
      {inProgress(run) && <Meter label="Answers given" value={run.progress.done} max={Math.max(run.progress.total, 1)} unit="answers" progress />}
      {run.error_message !== null && <Notice tone="error">{run.error_message}</Notice>}
      {!inProgress(run) && (
        <ol aria-label="Cases" className="flex flex-col gap-4">
          {cases.map((evaluationCase, index) => (
            <li key={index} className={`${surface.panel} flex flex-col gap-3`}>
              <h4 className="font-medium text-ink">{evaluationCase.question}</h4>
              <p className="text-sm text-ink-2">
                <span className="font-medium">Reference answer: </span>
                {evaluationCase.reference_answer}
              </p>
              {evaluationCase.results.map((result) => (
                <CaseAnswer key={`${result.position}-${String(result.repeat)}`} result={result} />
              ))}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/** The Agent's Runs, newest first; choosing one shows it below. */
function RunList({ runs, chosen, onChoose }: { runs: EvaluationRun[]; chosen: string | null; onChoose: (runId: string) => void }) {
  return (
    <ul aria-label="Evaluation Runs" className={`${surface.card} divide-y divide-line-soft`}>
      {runs.map((run) => (
        <li key={run.id} className={`flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3 text-sm ${run.id === chosen ? "bg-accent-soft" : ""}`}>
          <button type="button" className={button.quiet} aria-current={run.id === chosen ? "true" : undefined} onClick={() => { onChoose(run.id); }}>
            Run of {formatTime(run.created_at)}
          </button>
          <RunStatus run={run} />
          <span className="font-mono text-xs text-muted">
            {run.progress.done} / {run.progress.total} answers
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * The Evaluation view: the Agent's Evaluation Set with its case editor and Evaluate, then its Runs
 * and the chosen Run's answers with their Verdicts and Traces. An archived Agent's set is read only.
 */
export function AgentEvaluation({ agent, organisationId }: { agent: Agent; organisationId: string }) {
  const path = { organisation_id: organisationId, project_id: agent.project_id, agent_id: agent.id };
  const setHeadingId = useId();
  const runsHeadingId = useId();
  const archived = agent.archived_at !== null;
  const cases = useEvaluationCases(path);
  const runs = useEvaluationRuns(path);
  const start = useStartEvaluationRun(path);
  const remove = useDeleteEvaluationCase(path);
  const [editing, setEditing] = useState<EvaluationCase | "new" | null>(null);
  const [deleting, setDeleting] = useState<EvaluationCase | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const shownRun = chosen ?? runs.data?.[0]?.id ?? null;
  const running = (runs.data ?? []).some(inProgress);
  const noCases = (cases.data ?? []).length === 0;

  const newCase = (
    <button type="button" className={button.secondary} onClick={() => { setEditing("new"); }}>
      New case
    </button>
  );

  return (
    <div className="flex flex-col gap-8">
      {archived && <Notice tone="info">This Agent is archived: its Evaluation Set and Runs are read only, and it starts no Run.</Notice>}
      <section aria-labelledby={setHeadingId} className="flex flex-col gap-4">
        <PageHeader
          level={2}
          headingId={setHeadingId}
          title="Evaluation Set"
          description="Questions this Agent is measured against, each with what a good answer says. Evaluate answers them with the Draft."
          actions={
            !archived && (
              <>
                {newCase}
                <button
                  type="button"
                  className={button.primary}
                  disabled={noCases || running || start.isPending}
                  onClick={() => {
                    start.mutate(undefined, { onSuccess: (run) => { setChosen(run.id); } });
                  }}
                >
                  {running ? "Evaluating…" : "Evaluate"}
                </button>
              </>
            )
          }
        />
        <FormError message={evaluationFailure(start.error ?? remove.error)} />
        {cases.isPending && <Skeleton label="Loading the Evaluation Set" />}
        {cases.isError && <EmptyState tone="error" icon="agents" title="The Evaluation Set could not be loaded" description="Try again shortly." />}
        {cases.data && cases.data.length === 0 && (
          <EmptyState
            icon="agents"
            level={3}
            title="No Evaluation Cases yet"
            description={archived ? "This Agent's Evaluation Set is empty." : "Write a question and what a good answer says, then evaluate the Draft against it."}
            action={archived ? undefined : newCase}
          />
        )}
        {cases.data && cases.data.length > 0 && (
          <CaseTable cases={cases.data} readOnly={archived} onEdit={setEditing} onDelete={setDeleting} />
        )}
      </section>
      <section aria-labelledby={runsHeadingId} className="flex flex-col gap-4">
        <h2 id={runsHeadingId} className={text.heading}>
          Runs
        </h2>
        {runs.isError && <Notice tone="error">The Runs could not be loaded. Try again shortly.</Notice>}
        {runs.data && runs.data.length === 0 && <p className={text.muted}>No Runs yet. Evaluate to answer the set with the Draft.</p>}
        {runs.data && runs.data.length > 0 && <RunList runs={runs.data} chosen={shownRun} onChoose={setChosen} />}
        {shownRun !== null && <RunDetail key={shownRun} path={path} runId={shownRun} />}
      </section>
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
          remove.mutate(deleting.id, { onSettled: () => { setDeleting(null); } });
        }}
      >
        “{deleting.question}” leaves the Evaluation Set. Past Runs keep their copy of it.
      </ConfirmDialog>
      )}
    </div>
  );
}
