import { useEffect } from "react";

import { type Trace, useTrace } from "./agents";
import { BUTTON } from "./ProjectsPage";

type TraceChunk = Trace["chunks"][number];

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
};

function outcome(chunk: TraceChunk): string {
  if (chunk.excluded_reason) return EXCLUDED[chunk.excluded_reason];
  return chunk.cited ? "Cited" : "Given, not cited";
}

/** US dollars to the nano-dollar, without trailing zeros: "0.000057600" is "$0.0000576" and a
 * zero, even in exponent form ("0E-9"), is "$0". */
function dollars(amount: string | null): string {
  if (amount === null) return "Unknown";
  return `$${Number(amount).toFixed(9).replace(/\.?0+$/, "")}`;
}

/** A fallback reply asked no model, so its model provider and name are both null. */
function model(trace: Trace): string {
  if (trace.model_name === null) return "None (fallback)";
  return `${String(trace.model_provider)} · ${trace.model_name}`;
}

function TraceBody({ trace }: { trace: Trace }) {
  const facts: [string, string][] = [
    // An answer always has its tokens and latency; a fallback reply names no model, and the
    // cost is unknown when the model has no price.
    ["Model", model(trace)],
    ["Tokens", `${String(trace.input_tokens)} input · ${String(trace.output_tokens)} output`],
    ["Cost", dollars(trace.cost_usd)],
    ["Latency", `${String(trace.first_token_ms)} ms to the first token · ${String(trace.latency_ms)} ms in all`],
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
          No Chunk reached the minimum score, so the Agent replied with its fallback text and the model wasn't asked.
        </p>
      )}
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
            <tr key={chunk.chunk_id} className="border-b border-slate-100 align-top">
              <td>{chunk.rank === null ? "—" : `C${String(chunk.rank)}`}</td>
              <td>{chunk.document_name ?? "Deleted Document"}</td>
              <td className="text-xs whitespace-pre-wrap text-slate-700">{chunk.text ?? "—"}</td>
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

/** Why an answer came out as it did: the model, usage, cost, latency and the Chunks retrieved. */
export function TraceDrawer({ path, onClose }: { path: TracePath; onClose: () => void }) {
  const trace = useTrace(path);

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
    body = <p role="alert">The Trace could not be loaded. Try again shortly.</p>;
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
