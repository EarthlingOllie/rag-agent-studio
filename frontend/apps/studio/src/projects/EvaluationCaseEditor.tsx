import { type SubmitEvent, useId, useState } from "react";

import { FormError } from "../auth/AuthLayout";
import { Dialog, Notice, Skeleton, button, field, text, useToast } from "../design";
import { type EvaluationCase, evaluationFailure, useEvaluationPrefill, useSaveEvaluationCase } from "./evaluation";
import { type ChosenSource, ExpectedSourceList, ExpectedSourcePicker } from "./EvaluationExpectations";

export type AgentPath = { organisation_id: string; project_id: string; agent_id: string };

const NEEDS_EXPECTATION =
  "Add an Expected source, write a Reference answer or tick Expect Fallback Text: a case needs at least one expectation.";
const FALLBACK_WITH_REFERENCE = "Expect Fallback Text can't be combined with a Reference answer: clear the Reference answer or untick Expect Fallback Text.";
const FALLBACK_WITH_SOURCE = "Expect Fallback Text can't be combined with an Expected source: remove the Expected sources or untick Expect Fallback Text.";
const DELETED_SOURCE = "Remove the Expected sources whose Document has been deleted, then save.";
const NO_LINK =
  "No link to the Conversation is kept: the question is copied into the Evaluation Set, kept after the Retention Window until you delete the case.";

/** What's wrong with the case's expectations, by the field it names, or null when they can be saved. */
function expectationProblem(
  reference: string,
  sources: ChosenSource[],
  expectFallback: boolean,
): { field: "reference" | "fallback" | "sources"; message: string } | null {
  const hasReference = reference.trim() !== "";
  if (expectFallback && hasReference) return { field: "fallback", message: FALLBACK_WITH_REFERENCE };
  if (expectFallback && sources.length > 0) return { field: "fallback", message: FALLBACK_WITH_SOURCE };
  if (!hasReference && sources.length === 0 && !expectFallback) return { field: "reference", message: NEEDS_EXPECTATION };
  if (sources.some((source) => source.document_id === null)) return { field: "sources", message: DELETED_SOURCE };
  return null;
}

/** A new case from an Agent Message: its question, and the passages it cited, offered unticked. */
export type CasePrefill = { question: string; offered: ChosenSource[] };

/** The passages the Message cited, each ticked to make it an Expected source. */
function OfferedSources({ offered, chosen, onToggle }: { offered: ChosenSource[]; chosen: Set<number>; onToggle: (index: number) => void }) {
  const headingId = useId();
  if (offered.length === 0) return null;
  return (
    <fieldset aria-labelledby={headingId} className="flex flex-col gap-2">
      <legend id={headingId} className={field.label}>
        Cited passages
      </legend>
      <p className={field.hint}>Tick a passage the answer should cite to make it an Expected source.</p>
      <ul className="flex flex-col gap-2">
        {offered.map((source, index) => (
          <li key={index} className="rounded-xl bg-sunken px-3.5 py-2.5 text-sm">
            <label className="flex items-start gap-2.5">
              <input
                type="checkbox"
                className={`${field.checkbox} mt-0.5`}
                checked={chosen.has(index)}
                onChange={() => {
                  onToggle(index);
                }}
              />
              <span className="flex min-w-0 flex-col gap-1">
                <span className="font-medium text-ink">{source.document_name}</span>
                <span className="whitespace-pre-wrap text-ink-2">“{source.passage}”</span>
              </span>
            </label>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}

/**
 * The case editor, in a dialog: a question and its expectations (Expected sources, a Reference
 * answer, or Expect Fallback Text). With `prefill`, a new case added from an Agent Message: the
 * question copied, editable, and the cited passages offered unticked.
 */
export function CaseEditor({
  path,
  editing,
  prefill,
  onClose,
  onSaved,
}: {
  path: AgentPath;
  editing: EvaluationCase | null;
  prefill?: CasePrefill;
  onClose: () => void;
  onSaved?: () => void;
}) {
  const formId = useId();
  const hintId = useId();
  const errorId = useId();
  const sourcesId = useId();
  const fallbackHintId = useId();
  const [question, setQuestion] = useState(editing?.question ?? prefill?.question ?? "");
  const [reference, setReference] = useState(editing?.reference_answer ?? "");
  const [sources, setSources] = useState<ChosenSource[]>(editing?.expected_sources ?? []);
  const [ticked, setTicked] = useState<Set<number>>(() => new Set());
  const [expectFallback, setExpectFallback] = useState(editing?.expect_fallback ?? false);
  const [picking, setPicking] = useState(false);
  const [problem, setProblem] = useState<ReturnType<typeof expectationProblem>>(null);
  const save = useSaveEvaluationCase(path, editing?.id ?? null);
  let title = "New Evaluation Case";
  if (editing !== null) title = "Edit Evaluation Case";
  else if (prefill !== undefined) title = "Add to Evaluation Set";
  const offered = prefill?.offered ?? [];
  const allSources = [...offered.filter((_, index) => ticked.has(index)), ...sources];

  function submit(event: SubmitEvent) {
    event.preventDefault();
    const found = expectationProblem(reference, allSources, expectFallback);
    setProblem(found);
    if (found !== null) return;
    save.mutate(
      {
        question,
        reference_answer: reference,
        expected_sources: allSources.map((source) => ({ document_id: source.document_id as string, passage: source.passage })),
        expect_fallback: expectFallback,
        source: prefill === undefined ? "written" : "from_message",
      },
      { onSuccess: onSaved ?? onClose },
    );
  }

  const describedBy = (fieldName: string, hint: string) => (problem?.field === fieldName ? `${hint} ${errorId}` : hint);
  const error = (fieldName: string) =>
    problem?.field === fieldName && (
      <p id={errorId} className={field.error}>
        {problem.message}
      </p>
    );

  return (
    <Dialog
      open
      title={title}
      description="One standalone question, and what a good answer to it does."
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
        {prefill !== undefined && <Notice tone="info">{NO_LINK}</Notice>}
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
        <OfferedSources
          offered={offered}
          chosen={ticked}
          onToggle={(index) => {
            const next = new Set(ticked);
            if (!next.delete(index)) next.add(index);
            setTicked(next);
          }}
        />
        <div role="group" aria-labelledby={sourcesId} aria-describedby={problem?.field === "sources" ? errorId : undefined} className="flex flex-col gap-2">
          <p id={sourcesId} className={field.label}>
            {prefill === undefined ? "Expected sources" : "Other Expected sources"}
          </p>
          <ExpectedSourceList
            sources={sources}
            onRemove={(index) => {
              setSources(sources.filter((_, at) => at !== index));
            }}
          />
          {error("sources")}
          {picking ? (
            <ExpectedSourcePicker
              organisationId={path.organisation_id}
              projectId={path.project_id}
              onAdd={(source) => {
                setSources([...sources, source]);
                setPicking(false);
              }}
              onCancel={() => {
                setPicking(false);
              }}
            />
          ) : (
            <button
              type="button"
              className={`${button.secondary} self-start`}
              onClick={() => {
                setPicking(true);
              }}
            >
              Add Expected source
            </button>
          )}
        </div>
        <div>
          <label className={field.label}>
            Reference answer
            <textarea
              className={field.textarea}
              rows={4}
              maxLength={4000}
              aria-invalid={problem?.field === "reference"}
              aria-describedby={describedBy("reference", hintId)}
              value={reference}
              onChange={(event) => {
                setReference(event.target.value);
              }}
            />
          </label>
          <p id={hintId} className={field.hint}>
            What a good answer says, in your own words. The judge checks its meaning, not its wording.
          </p>
          {error("reference")}
        </div>
        <div>
          <label className="flex items-center gap-2 text-sm font-medium text-ink">
            <input
              type="checkbox"
              className={field.checkbox}
              checked={expectFallback}
              aria-invalid={problem?.field === "fallback"}
              aria-describedby={describedBy("fallback", fallbackHintId)}
              onChange={(event) => {
                setExpectFallback(event.target.checked);
              }}
            />
            Expect Fallback Text
          </label>
          <p id={fallbackHintId} className={field.hint}>
            A good answer says it doesn&apos;t know: the Fallback Text, or the Refusal text. It stands alone, without Expected sources or a Reference answer.
          </p>
          {error("fallback")}
        </div>
      </form>
    </Dialog>
  );
}

/**
 * "Add to Evaluation Set" on an Agent Message: reads the question it answered and the passages it
 * cited, then opens the case editor with them. Saving says so in a toast.
 */
export function AddToEvaluationSet({ path, messageId, onClose }: { path: AgentPath; messageId: string; onClose: () => void }) {
  const prefill = useEvaluationPrefill(path, messageId);
  const toast = useToast();
  if (prefill.data !== undefined)
    return (
      <CaseEditor
        path={path}
        editing={null}
        prefill={{ question: prefill.data.question, offered: prefill.data.expected_sources }}
        onClose={onClose}
        onSaved={() => {
          toast.show("Added to the Evaluation Set.");
          onClose();
        }}
      />
    );
  return (
    <Dialog
      open
      title="Add to Evaluation Set"
      onClose={onClose}
      closeButton={false}
      footer={
        <button type="button" className={button.secondary} onClick={onClose}>
          Close
        </button>
      }
    >
      {prefill.isError ? (
        <Notice tone="error">{evaluationFailure(prefill.error)}</Notice>
      ) : (
        <>
          <Skeleton label="Reading the Message" />
          <p className={text.muted}>Reading the question and the passages it cited…</p>
        </>
      )}
    </Dialog>
  );
}
