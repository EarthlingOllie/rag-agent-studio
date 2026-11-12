import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { type ReactNode, useState } from "react";

import { Badge, EmptyState, Icon, Notice, Skeleton, button, field, text } from "../design";

import { retrievalModeName } from "./AgentDiff";
import { useAgents } from "./agents";
import { type MetricsRange, type VersionKpis, useVersionMetrics } from "./analytics";
import { dollars, duration } from "./format";
import { ProjectRequestError } from "./projects";
import { useOrganisationRole } from "./ProjectsPage";
import { TimeSeriesChart } from "./TimeSeriesChart";
import { VersionComparison } from "./VersionComparison";

const ROUTE = "/signed-in/organisations/$organisationId/projects/$projectId/analytics";

const percent = (rate: number) => `${String(Math.round(rate * 100))}%`;

/** A rate under one percent (but not none) keeps one decimal, so it doesn't read as 0% or 1%. */
const finePercent = (rate: number) => (rate > 0 && rate < 0.01 ? `${(rate * 100).toFixed(1)}%` : percent(rate));

const plural = (count: number, one: string, many = `${one}s`) => `${String(count)} ${count === 1 ? one : many}`;

/**
 * One KPI card: the figure in mono, then its interval and sample size. A small sample is drawn
 * dashed and muted with a Low sample badge (its title says why), so a few lucky votes don't
 * look like a result.
 */
function KpiCard({
  title,
  value,
  details,
  lowSample = false,
}: {
  title: string;
  value: string;
  details: ReactNode;
  /** Why the sample is small ("Fewer than 30 votes"), when it is. */
  lowSample?: string | false;
}) {
  const id = `kpi-${title.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}`;
  return (
    <li
      aria-labelledby={id}
      className={`flex flex-col gap-1 rounded-2xl border px-5 py-4 ${lowSample !== false ? "border-dashed border-field bg-canvas" : "border-line bg-surface"}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={id} className="text-[13px] text-muted">
          {title}
        </h3>
        {lowSample !== false && <Badge kind="lowSample" title={lowSample} />}
      </div>
      <p className={`font-mono text-[22px] ${lowSample !== false ? "text-muted" : "text-ink"}`}>{value}</p>
      <div className="space-y-0.5 text-[13px] text-muted">{details}</div>
    </li>
  );
}

function Kpis({ kpis }: { kpis: VersionKpis }) {
  const { tokens, cost, thumbs_up: thumbs, rating, fallback, guardrail_blocks: blocks, searches, latency } = kpis;
  return (
    <ul aria-label={`Key numbers for v${String(kpis.number)}`} className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
      <KpiCard
        title="Volume"
        value={plural(kpis.conversations, "Conversation")}
        details={<p>{plural(kpis.messages, "reply", "replies")}</p>}
        lowSample={kpis.low_confidence && "Fewer than 30 Conversations"}
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
      {/* Cost is for Owners only: the API leaves it out for Editors. */}
      {cost !== null && (
        <KpiCard
          title="Cost per Conversation"
          value={cost.per_conversation_usd === null ? "No Conversations yet" : dollars(cost.per_conversation_usd)}
          details={<p>{`${dollars(cost.total_usd)} in total, at the prices of the time`}</p>}
        />
      )}
      <KpiCard
        title="Thumbs-up rate"
        value={thumbs.rate === null ? "No votes yet" : percent(thumbs.rate)}
        details={
          <>
            {thumbs.low !== null && thumbs.high !== null && <p>{`95% interval ${percent(thumbs.low)} to ${percent(thumbs.high)}`}</p>}
            <p>{`n = ${plural(thumbs.n, "vote")} (${String(thumbs.up)} up, ${String(thumbs.down)} down)`}</p>
          </>
        }
        lowSample={thumbs.low_confidence && "Fewer than 30 votes"}
      />
      <KpiCard
        title="Mean rating"
        value={rating.mean === null ? "No ratings yet" : `${rating.mean.toFixed(1)} of 5`}
        details={<p>{`n = ${plural(rating.n, "rating")}`}</p>}
        lowSample={rating.low_confidence && "Fewer than 30 ratings"}
      />
      <KpiCard
        title="Fallback rate"
        value={fallback.rate === null ? "No replies yet" : percent(fallback.rate)}
        details={<p>{`${String(fallback.count)} of ${plural(kpis.messages, "reply", "replies")} were the fallback text`}</p>}
      />
      <KpiCard
        title="Guardrail block rate"
        value={blocks.rate === null ? "No replies yet" : finePercent(blocks.rate)}
        details={
          <p>{`${String(blocks.count)} of ${plural(kpis.messages, "reply was", "replies were")} blocked by the input Guardrail`}</p>
        }
      />
      <KpiCard
        title="Searches per reply"
        value={searches.mean_per_reply === null ? "No replies yet" : `${searches.mean_per_reply.toFixed(1)} mean`}
        details={
          <>
            <p>{`Retrieval Mode: ${retrievalModeName(kpis.retrieval_mode)}`}</p>
            <p>{`${plural(searches.total, "Search", "Searches")} in ${plural(kpis.messages, "reply", "replies")}`}</p>
          </>
        }
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

function AgentMetrics({
  organisationId,
  projectId,
  agentId,
  agentFilter,
}: {
  organisationId: string;
  projectId: string;
  agentId: string;
  /** The Agent filter, first in the toolbar. */
  agentFilter: ReactNode;
}) {
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
    body = <Skeleton label="Loading the metrics" />;
  } else if (metrics.isError) {
    body = <Notice tone="error">{failure(metrics.error)}</Notice>;
  } else if (shown === undefined) {
    body = (
      <EmptyState
        icon="analytics"
        title="No Versions yet"
        description="This Agent has no Versions yet. Publish it, and Visitors' Conversations with each Version are measured here."
        level={3}
      />
    );
  } else {
    body = (
      <>
        <p className={text.muted}>
          {`${metrics.data.start} to ${metrics.data.end} (UTC days), including today so far. Visitor Conversations only: the Playground is left out.`}
        </p>
        <Kpis kpis={shown} />
        <VersionComparison organisationId={organisationId} projectId={projectId} agentId={agentId} versions={versions} range={range} />
        <TimeSeriesChart organisationId={organisationId} projectId={projectId} agentId={agentId} range={range} />
      </>
    );
  }

  return (
    <>
      <fieldset className="flex flex-wrap items-end gap-3">
        <legend className="sr-only">Choose what to measure</legend>
        {agentFilter}
        <label className={field.filter}>
          Version
          <select
            className={field.pill}
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
        <label className={field.filter}>
          From (UTC)
          <input type="date" className={field.pill} value={range.from ?? ""} onChange={day("from")} />
        </label>
        <label className={field.filter}>
          To (UTC)
          <input type="date" className={field.pill} value={range.to ?? ""} onChange={day("to")} />
        </label>
      </fieldset>
      {body}
    </>
  );
}

const ANALYTICS = "/organisations/$organisationId/projects/$projectId/analytics";

/**
 * The Analytics section: an Agent Version's KPI cards, with intervals, sample sizes and small
 * samples marked, the Agent's time series and two Versions compared. The Agent is in the URL
 * (`?agent=`), so each Agent's views can link here filtered to it.
 */
export function AnalyticsTab() {
  const { organisationId } = useOrganisationRole();
  const { projectId } = useParams({ from: ROUTE });
  const { agent: agentId } = useSearch({ from: ROUTE });
  const navigate = useNavigate({ from: ANALYTICS });
  const agents = useAgents(organisationId, projectId);
  const shownAgent = agents.data?.find((agent) => agent.id === agentId) ?? agents.data?.[0];

  let body;
  if (agents.isPending) {
    body = <Skeleton label="Loading the Agents" />;
  } else if (agents.isError) {
    body = <Notice tone="error">The Agents could not be loaded. Try again shortly.</Notice>;
  } else if (shownAgent === undefined) {
    body = (
      <EmptyState
        icon="analytics"
        title="No Agents yet"
        description="No Agents to measure yet. Create and publish an Agent, and each Version's key numbers appear here."
        level={3}
      />
    );
  } else {
    const agentFilter = (
      <label className={field.filter}>
        Agent
        <select
          className={field.pill}
          value={shownAgent.id}
          onChange={(event) => {
            void navigate({ search: { agent: event.currentTarget.value } });
          }}
        >
          {agents.data.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name}
            </option>
          ))}
        </select>
      </label>
    );
    body = (
      <AgentMetrics
        key={shownAgent.id}
        organisationId={organisationId}
        projectId={projectId}
        agentId={shownAgent.id}
        agentFilter={agentFilter}
      />
    );
  }

  return (
    <section aria-labelledby="tab-heading" className="flex flex-col gap-6">
      <h2 id="tab-heading" className="text-2xl font-medium tracking-[-0.01em] text-ink">
        Analytics
      </h2>
      {body}
    </section>
  );
}

/** The link each Agent view offers to Analytics, filtered to the Agent. */
export function AgentAnalyticsLink({ organisationId, projectId, agentId }: { organisationId: string; projectId: string; agentId: string }) {
  return (
    <Link to={ANALYTICS} params={{ organisationId, projectId }} search={{ agent: agentId }} className={button.ghost}>
      <Icon name="analytics" />
      Analytics for this Agent
    </Link>
  );
}
