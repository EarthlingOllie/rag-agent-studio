import type { UseQueryResult } from "@tanstack/react-query";
import { useEffect } from "react";

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
  flagged: "flagged after sending",
};

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

function TraceBody({ trace }: { trace: Trace }) {
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
        <p className="text-sm text-slate-700">
          No Chunk reached the minimum score, so the Agent replied with its
          fallback text and the model wasn't asked.
        </p>
      )}
      {blocked(trace) && (
        <p className="text-sm text-slate-700">
          The input Guardrail blocked the question, so the Agent replied with
          its refusal text and the model wasn't asked.
        </p>
      )}
      <section aria-labelledby="trace-guardrails" className="space-y-1 text-sm">
        <h3 id="trace-guardrails" className="font-medium">
          Guardrails
        </h3>
        {trace.guardrail_outcomes.length === 0 ? (
          <p className="text-slate-700">No Guardrail stepped in.</p>
        ) : (
          <ul aria-labelledby="trace-guardrails" className="list-disc pl-5">
            {trace.guardrail_outcomes.map((outcome, index) => (
              <li key={index}>
                {LAYERS[outcome.layer]}: {verdict(outcome)},{" "}
                {ACTIONS[outcome.action]}. {outcome.reason}
              </li>
            ))}
          </ul>
        )}
      </section>
      <table className="w-full text-left text-sm">
        <caption className="text-left font-medium">Retrieved Chunks</caption>
        <thead>
          <tr className="border-b border-slate-200">
            <th scope="col">Chunk</th>
            <th scope="col">Document</th>
            <th scope="col">Excerpt</th>
            <th scope="col">Score</th>
            <th scope="col">Relevance</th>
            <th scope="col">Outcome</th>
          </tr>
        </thead>
        <tbody>
          {trace.chunks.map((chunk) => (
            <tr
              key={chunk.chunk_id}
              className="border-b border-slate-100 align-top"
            >
              <td>{chunk.rank === null ? "—" : `C${String(chunk.rank)}`}</td>
              <td>{chunk.document_name ?? "Deleted Document"}</td>
              <td className="text-xs whitespace-pre-wrap text-slate-700">
                {chunk.text ?? "—"}
              </td>
              <td>{chunk.score.toFixed(3)}</td>
              <td>{chunk.relevance.toFixed(3)}</td>
              <td>{outcome(chunk)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Why a Playground answer came out as it did: the model, usage, cost, latency and the Chunks retrieved. */
export function TraceDrawer({
  path,
  onClose,
}: {
  path: TracePath;
  onClose: () => void;
}) {
  return <TraceDrawerFrame trace={useTrace(path)} onClose={onClose} />;
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

  let body;
  if (trace.isError) {
    body = (
      <p role="alert">The Trace could not be loaded. Try again shortly.</p>
    );
  } else if (trace.data === undefined) {
    body = <p role="status">Loading the Trace…</p>;
  } else {
    body = <TraceBody trace={trace.data} />;
  }

  return (
    <aside
      role="dialog"
      aria-labelledby="trace-heading"
      className="fixed inset-y-0 right-0 z-10 w-full max-w-xl space-y-4 overflow-y-auto border-l border-slate-200 bg-white p-6 shadow-lg"
    >
      <div className="flex items-center justify-between">
        <h2 id="trace-heading" className="text-lg font-semibold">
          Trace
        </h2>
        <button type="button" onClick={onClose} className={BUTTON} autoFocus>
          Close
        </button>
      </div>
      {body}
    </aside>
  );
}
