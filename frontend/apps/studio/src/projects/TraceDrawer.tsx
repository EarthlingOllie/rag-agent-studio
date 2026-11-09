import type { UseQueryResult } from "@tanstack/react-query";
import { useEffect, useId, useState } from "react";

import { Icon, surface } from "../design";
import { type Trace, instructionsUsed, useTrace } from "./agents";
import { BUTTON } from "./ProjectsPage";

type TraceChunk = Trace["chunks"][number];
type GuardrailOutcome = Trace["guardrail_outcomes"][number];

const LAYERS: Record<GuardrailOutcome["layer"], string> = {
  input: "Input Guardrail",
  canary: "Canary token",
};
const ACTIONS: Record<GuardrailOutcome["action"], string> = {
  blocked: "blocked before the model",
  replaced: "cut off and replaced",
  // The canary flags an answer it finds encoded once the answer is complete.
  flagged: "flagged after sending",
  logged: "logged only and answered as usual",
  allowed: "let through without the check",
};

/** The input Guardrail flags a message in warn mode, before the model, which it cautions. */
function action(outcome: GuardrailOutcome): string {
  if (outcome.layer === "input" && outcome.action === "flagged")
    return "flagged and answered with a caution to the model";
  return ACTIONS[outcome.action];
}

/** "injection (score 0.99)", or the verdict alone for a layer that doesn't score. */
function verdict(outcome: GuardrailOutcome): string {
  if (typeof outcome.score !== "number") return outcome.verdict;
  return `${outcome.verdict} (score ${outcome.score.toFixed(2)})`;
}

/** Whether the input Guardrail blocked the question, so the reply is the refusal text. */
function blocked(trace: Trace): boolean {
  return trace.guardrail_outcomes.some(
    (outcome) => outcome.layer === "input" && outcome.action === "blocked",
  );
}

export type TracePath = {
  organisation_id: string;
  project_id: string;
  agent_id: string;
  conversation_id: string;
  message_id: string;
};

const EXCLUDED: Record<NonNullable<TraceChunk["excluded_reason"]>, string> = {
  below_min_score: "Excluded: below the minimum score",
  outside_top_k: "Excluded: outside top-k",
  outside_tags: "Excluded: outside the Agent's Tags",
  guardrail_flagged: "Excluded: flagged by the ingestion scan",
};

/** The Chunk's Document, or a tombstone once the Document has been deleted. */
function documentText(chunk: TraceChunk): string {
  if (chunk.document_name === null) return "Chunk from a deleted Document";
  return chunk.document_deleted ? `Chunk from deleted Document ${chunk.document_name}` : chunk.document_name;
}

function outcome(chunk: TraceChunk): string {
  if (chunk.excluded_reason) return EXCLUDED[chunk.excluded_reason];
  return chunk.cited ? "Cited" : "Given, not cited";
}

/** US dollars to the nano-dollar, without trailing zeros: "0.000057600" is "$0.0000576" and a
 * zero, even in exponent form ("0E-9"), is "$0". */
function dollars(amount: string | null): string {
  if (amount === null) return "Unknown";
  return `$${Number(amount)
    .toFixed(9)
    .replace(/\.?0+$/, "")}`;
}

/** A fallback reply or a refusal asked no model, so its model provider and name are both
 * null. */
function model(trace: Trace): string {
  if (trace.model_name === null)
    return blocked(trace) ? "None (blocked)" : "None (fallback)";
  return `${String(trace.model_provider)} · ${trace.model_name}`;
}

/** "Agent Version v2" for a Live answer, "Draft" for a Playground one. */
export function answeredBy(answer: { agent_version_number: number | null }): string {
  return answer.agent_version_number === null ? "Draft" : `Agent Version v${String(answer.agent_version_number)}`;
}

/** A cited Chunk in the accent colour, one the ingestion scan flagged in the flag colour. */
function chunkTone(chunk: TraceChunk): string {
  if (chunk.excluded_reason === "guardrail_flagged") return "text-flag";
  return chunk.cited ? "font-medium text-accent" : "";
}

function TraceBody({ trace }: { trace: Trace }) {
  const guardrailsId = useId();
  const facts: [string, string][] = [
    // An answer always has its tokens and latency; a fallback reply names no model, and the
    // cost is unknown when the model has no price.
    ["Answered by", answeredBy(trace)],
    ["Model", model(trace)],
    // An Agent Version's answer ran with the Instructions the Version pins.
    [
      "Instructions",
      trace.agent_version_number === null ? instructionsUsed(trace) : `Pinned by ${answeredBy(trace)}`,
    ],
    [
      "Tokens",
      `${String(trace.input_tokens)} input · ${String(trace.output_tokens)} output`,
    ],
    ["Cost", dollars(trace.cost_usd)],
    [
      "Latency",
      `${String(trace.first_token_ms)} ms to the first token · ${String(trace.latency_ms)} ms in all`,
    ],
  ];
  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        {facts.map(([term, value]) => (
          <div key={term} className="contents">
            <dt className="font-medium">{term}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {trace.fallback && (
        <p className="text-sm text-muted">
          No Chunk reached the minimum score, so the Agent replied with its
          fallback text and the model wasn't asked.
        </p>
      )}
      {blocked(trace) && (
        <p className="text-sm text-muted">
          The input Guardrail blocked the question, so the Agent replied with
          its refusal text and the model wasn't asked.
        </p>
      )}
      <section aria-labelledby={guardrailsId} className="space-y-1 text-sm">
        <h3 id={guardrailsId} className="font-medium">
          Guardrails
        </h3>
        {trace.guardrail_outcomes.length === 0 ? (
          <p className="text-muted">No Guardrail stepped in.</p>
        ) : (
          <ul aria-labelledby={guardrailsId} className="list-disc pl-5">
            {trace.guardrail_outcomes.map((outcome, index) => (
              <li key={index}>
                {LAYERS[outcome.layer]}: {verdict(outcome)},{" "}
                {action(outcome)}. {outcome.reason}
              </li>
            ))}
          </ul>
        )}
      </section>
      <table className="w-full text-left text-sm">
        <caption className="text-left font-medium">Retrieved Chunks</caption>
        <thead>
          <tr className="border-b border-line">
            <th scope="col">Chunk</th>
            <th scope="col">Document</th>
            <th scope="col">Excerpt</th>
            <th scope="col">Score</th>
            <th scope="col">Relevance</th>
            <th scope="col">Outcome</th>
          </tr>
        </thead>
        <tbody>
          {trace.chunks.map((chunk, index) => (
            <tr
              // A deleted Document's Chunk has no ID left; the Trace's order is fixed.
              key={index}
              className="border-b border-line-soft align-top"
            >
              <td className={chunkTone(chunk)}>{chunk.rank === null ? "—" : `C${String(chunk.rank)}`}</td>
              <td>{documentText(chunk)}</td>
              <td className="text-xs whitespace-pre-wrap text-muted">
                {chunk.text ?? "—"}
              </td>
              <td>{chunk.score.toFixed(3)}</td>
              <td>{chunk.relevance.toFixed(3)}</td>
              <td className={chunkTone(chunk)}>{outcome(chunk)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A Trace however it is loaded: loading, failed, or its body. */
function TraceContent({ trace }: { trace: UseQueryResult<Trace> }) {
  if (trace.isError) return <p role="alert">The Trace could not be loaded. Try again shortly.</p>;
  if (trace.data === undefined) return <p role="status">Loading the Trace…</p>;
  return <TraceBody trace={trace.data} />;
}

function LoadedTrace({ path }: { path: TracePath }) {
  return <TraceContent trace={useTrace(path)} />;
}

/**
 * Why a Playground answer came out as it did, folded under the answer: the summary row shows its
 * usage; opening it loads the model, cost, latency, Guardrails and the Chunks retrieved.
 */
export function TraceFold({ path, summary }: { path: TracePath; summary: string }) {
  // Loaded the first time it opens, and kept while it is folded again.
  const [opened, setOpened] = useState(false);
  return (
    <details
      aria-label="Trace"
      className={`${surface.card} group overflow-hidden`}
      onToggle={(event) => {
        if (event.currentTarget.open) setOpened(true);
      }}
    >
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-sm">
        <Icon name="chevronRight" size={14} className="text-muted transition-transform group-open:rotate-90" />
        <span className="font-medium text-ink">Trace</span>
        <span className="font-mono text-xs text-muted">{summary}</span>
      </summary>
      <div className="overflow-x-auto border-t border-line-soft px-4 py-4">{opened && <LoadedTrace path={path} />}</div>
    </details>
  );
}

/** The Trace drawer around a Trace however it is loaded (the Playground's or a Conversation's). */
export function TraceDrawerFrame({
  trace,
  onClose,
}: {
  trace: UseQueryResult<Trace>;
  onClose: () => void;
}) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose]);

  return (
    <aside
      role="dialog"
      aria-labelledby="trace-heading"
      className="fixed inset-y-0 right-0 z-10 w-full max-w-xl space-y-4 overflow-y-auto border-l border-line bg-surface p-6 shadow-lg"
    >
      <div className="flex items-center justify-between">
        <h2 id="trace-heading" className="text-lg font-semibold">
          Trace
        </h2>
        <button type="button" onClick={onClose} className={BUTTON} autoFocus>
          Close
        </button>
      </div>
      <TraceContent trace={trace} />
    </aside>
  );
}
