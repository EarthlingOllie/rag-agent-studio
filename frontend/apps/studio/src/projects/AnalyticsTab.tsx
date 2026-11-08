import { useParams } from "@tanstack/react-router";
import { type ReactNode, useState } from "react";

import { useAgents } from "./agents";
import { type MetricsRange, type VersionKpis, useVersionMetrics } from "./analytics";
import { ProjectRequestError } from "./projects";
import { INPUT, useOrganisationRole } from "./ProjectsPage";

const ROUTE = "/signed-in/organisations/$organisationId/projects/$projectId/analytics";

const percent = (rate: number) => `${String(Math.round(rate * 100))}%`;

const cents = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fractionOfACent = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumSignificantDigits: 2 });

/** Dollars as a person reads them: to the cent, or to two significant digits below a cent. */
export function dollars(amount: string): string {
  const value = Number(amount);
  return value !== 0 && value < 0.01 ? fractionOfACent.format(value) : cents.format(value);
}

/** Milliseconds, or seconds from one second up. */
export function duration(ms: number): string {
  return ms < 1000 ? `${String(Math.round(ms))} ms` : `${(ms / 1000).toFixed(1)} s`;
}

const plural = (count: number, one: string, many = `${one}s`) => `${String(count)} ${count === 1 ? one : many}`;

/**
 * One KPI card. A small sample gets the low-confidence treatment: muted, dashed, and labelled
 * "Low confidence" with why, so a few lucky votes don't look like a result.
 */
function KpiCard({
  title,
  value,
  details,
  lowConfidence,
  why,
}: {
  title: string;
  value: string;
  details: ReactNode;
  lowConfidence?: boolean;
  why?: string;
}) {
  const id = `kpi-${title.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}`;
  return (
    <li
      aria-labelledby={id}
      className={
        lowConfidence
          ? "rounded border border-dashed border-slate-400 bg-slate-50 p-4 text-slate-600"
          : "rounded border border-slate-200 bg-white p-4 text-slate-900"
      }
    >
      <h3 id={id} className="text-sm font-medium">
        {title}
      </h3>
      <p className={lowConfidence ? "mt-1 text-2xl font-semibold text-slate-600" : "mt-1 text-2xl font-semibold"}>{value}</p>
      <div className="mt-1 space-y-0.5 text-sm">{details}</div>
      {lowConfidence && (
        <p className="mt-2 text-xs font-medium uppercase tracking-wide text-slate-700">
          Low confidence <span className="normal-case tracking-normal">({why})</span>
        </p>
      )}
    </li>
  );
}

function Kpis({ kpis }: { kpis: VersionKpis }) {
  const { tokens, cost, thumbs_up: thumbs, rating, fallback, latency } = kpis;
  return (
    <ul aria-label={`Key numbers for v${String(kpis.number)}`} className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <KpiCard
        title="Volume"
        value={plural(kpis.conversations, "Conversation")}
        details={<p>{plural(kpis.messages, "reply", "replies")}</p>}
        lowConfidence={kpis.low_confidence}
        why="fewer than 30 Conversations"
      />
      <KpiCard
        title="Tokens per reply"
        value={tokens.mean === null ? "No replies yet" : `${String(Math.round(tokens.mean))} mean`}
        details={
          <>
            {tokens.p95 !== null && <p>{`p95 ${String(Math.round(tokens.p95))}`}</p>}
            <p>{`n = ${plural(tokens.n, "reply", "replies")} that asked a model`}</p>
          </>
        }
      />
      <KpiCard
        title="Cost per Conversation"
        value={cost.per_conversation_usd === null ? "No Conversations yet" : dollars(cost.per_conversation_usd)}
        details={<p>{`${dollars(cost.total_usd)} in total, at the prices of the time`}</p>}
      />
      <KpiCard
        title="Thumbs-up rate"
        value={thumbs.rate === null ? "No votes yet" : percent(thumbs.rate)}
        details={
          <>
            {thumbs.low !== null && thumbs.high !== null && <p>{`95% interval ${percent(thumbs.low)} to ${percent(thumbs.high)}`}</p>}
            <p>{`n = ${plural(thumbs.n, "vote")} (${String(thumbs.up)} up, ${String(thumbs.down)} down)`}</p>
          </>
        }
        lowConfidence={thumbs.low_confidence}
        why="fewer than 30 votes"
      />
      <KpiCard
        title="Mean rating"
        value={rating.mean === null ? "No ratings yet" : `${rating.mean.toFixed(1)} of 5`}
        details={<p>{`n = ${plural(rating.n, "rating")}`}</p>}
        lowConfidence={rating.low_confidence}
        why="fewer than 30 ratings"
      />
      <KpiCard
        title="Fallback rate"
        value={fallback.rate === null ? "No replies yet" : percent(fallback.rate)}
        details={<p>{`${String(fallback.count)} of ${plural(kpis.messages, "reply", "replies")} were the fallback text`}</p>}
      />
      <KpiCard
        title="p95 latency"
        value={latency.total_p95_ms === null ? "No replies yet" : duration(latency.total_p95_ms)}
        details={
          <>
            {latency.first_token_p95_ms !== null && <p>{`First token ${duration(latency.first_token_p95_ms)}`}</p>}
            <p>{`n = ${plural(latency.n, "reply", "replies")}`}</p>
          </>
        }
      />
    </ul>
  );
}

function failure(error: Error): string {
  return error instanceof ProjectRequestError && error.status === 422
    ? "Check the dates: From can't be after To, and the range can be at most 366 days."
    : "The metrics could not be loaded. Try again shortly.";
}

function AgentMetrics({ organisationId, projectId, agentId }: { organisationId: string; projectId: string; agentId: string }) {
  const [range, setRange] = useState<MetricsRange>({});
  const [chosen, setChosen] = useState<string>();
  const metrics = useVersionMetrics(organisationId, projectId, agentId, range);
  const versions = metrics.data?.versions ?? [];
  // The chosen Version, else the Live one, else the newest.
  const shown = versions.find((v) => v.version_id === chosen) ?? versions.find((v) => v.is_live) ?? versions.at(-1);
  const day = (key: keyof MetricsRange) => (event: { currentTarget: { value: string } }) => {
    const { value } = event.currentTarget;
    setRange((current) => ({ ...current, [key]: value === "" ? undefined : value }));
  };

  let body;
  if (metrics.isPending) {
    body = <p role="status">Loading the metrics…</p>;
  } else if (metrics.isError) {
    body = <p role="alert">{failure(metrics.error)}</p>;
  } else if (shown === undefined) {
    body = <p className="mt-4 text-slate-700">This Agent has no Versions yet. Publish it, and Visitors' Conversations with each Version are measured here.</p>;
  } else {
    body = (
      <>
        <p className="mt-4 text-sm text-slate-700">
          {`${metrics.data.start} to ${metrics.data.end} (UTC days), including today so far. Visitor Conversations only: the Playground is left out.`}
        </p>
        <Kpis kpis={shown} />
      </>
    );
  }

  return (
    <>
      <fieldset className="mt-4 flex flex-wrap items-end gap-4">
        <legend className="sr-only">Choose what to measure</legend>
        <label className="flex flex-col gap-1 text-sm">
          Version
          <select
            className={INPUT}
            value={shown?.version_id ?? ""}
            disabled={shown === undefined}
            onChange={(event) => {
              setChosen(event.currentTarget.value);
            }}
          >
            {[...versions].reverse().map((v) => (
              <option key={v.version_id} value={v.version_id}>
                {`v${String(v.number)}${v.is_live ? " (Live)" : ""}`}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          From (UTC)
          <input type="date" className={INPUT} value={range.from ?? ""} onChange={day("from")} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          To (UTC)
          <input type="date" className={INPUT} value={range.to ?? ""} onChange={day("to")} />
        </label>
      </fieldset>
      {body}
    </>
  );
}

/** The Analytics tab: an Agent Version's KPI cards, with intervals, sample sizes and small samples marked. */
export function AnalyticsTab() {
  const { organisationId } = useOrganisationRole();
  const { projectId } = useParams({ from: ROUTE });
  const agents = useAgents(organisationId, projectId);
  const [agentId, setAgentId] = useState<string>();
  const shownAgent = agents.data?.find((agent) => agent.id === agentId) ?? agents.data?.[0];

  let body;
  if (agents.isPending) {
    body = <p role="status">Loading the Agents…</p>;
  } else if (agents.isError) {
    body = <p role="alert">The Agents could not be loaded. Try again shortly.</p>;
  } else if (shownAgent === undefined) {
    body = <p className="mt-2 text-slate-700">No Agents to measure yet. Create and publish an Agent, and each Version's key numbers appear here.</p>;
  } else {
    body = (
      <>
        <label className="mt-4 flex w-fit flex-col gap-1 text-sm">
          Agent
          <select
            className={INPUT}
            value={shownAgent.id}
            onChange={(event) => {
              setAgentId(event.currentTarget.value);
            }}
          >
            {agents.data.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </select>
        </label>
        <AgentMetrics key={shownAgent.id} organisationId={organisationId} projectId={projectId} agentId={shownAgent.id} />
      </>
    );
  }

  return (
    <section aria-labelledby="tab-heading">
      <h2 id="tab-heading" className="text-lg font-semibold">
        Analytics
      </h2>
      {body}
    </section>
  );
}
