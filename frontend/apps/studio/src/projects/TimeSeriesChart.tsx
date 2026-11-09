import { useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";

import { type MetricsRange, type TimeSeries, type TimeSeriesGranularity, type TimeSeriesMetric, useTimeSeries } from "./analytics";
import { ProjectRequestError } from "./projects";
import { INPUT } from "./ProjectsPage";

type Point = TimeSeries["points"][number];
type Marker = TimeSeries["markers"][number];

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumSignificantDigits: 3 });
const percent = (rate: number) => `${String(Math.round(rate * 100))}%`;
const whole = (value: number) => String(Math.round(value));

/** Each metric's name, how its values read, and what its sample size counts. */
const METRICS: Record<TimeSeriesMetric, { label: string; format: (value: number) => string; sample: string }> = {
  conversations: { label: "Conversations", format: whole, sample: "Conversations" },
  replies: { label: "Replies", format: whole, sample: "replies" },
  cost_usd: { label: "Cost", format: (value) => usd.format(value), sample: "Conversations" },
  mean_tokens: { label: "Mean tokens per reply", format: whole, sample: "replies that asked a model" },
  thumbs_up_rate: { label: "Thumbs-up rate", format: percent, sample: "votes" },
  mean_rating: { label: "Mean rating", format: (value) => `${value.toFixed(1)} of 5`, sample: "ratings" },
  fallback_rate: { label: "Fallback rate", format: percent, sample: "replies" },
  p95_latency_ms: {
    label: "p95 latency",
    format: (value) => (value < 1000 ? `${whole(value)} ms` : `${(value / 1000).toFixed(1)} s`),
    sample: "replies",
  },
};

const GRANULARITIES: Record<TimeSeriesGranularity, string> = { day: "Day", week: "Week", month: "Month" };

const ACTIONS: Record<string, string> = {
  publish: "published",
  revert: "reverted to",
  bulk_publish: "bulk published",
  bulk_revert: "bulk reverted to",
};

const period = (point: Point) => (point.start === point.end ? point.start : `${point.start} to ${point.end}`);

/** How a Live History entry reads: "v2 published", "v1 reverted to (from v2)". */
function change(marker: Marker): string {
  const to = `v${String(marker.to_version.number)} ${ACTIONS[marker.action] ?? marker.action}`;
  return marker.from_version === null ? to : `${to} (from v${String(marker.from_version.number)})`;
}

/** The markers grouped by the point (period) whose days hold them, keyed by that point's start. */
function markersByPoint(markers: Marker[]): Map<string, Marker[]> {
  const found = new Map<string, Marker[]>();
  for (const marker of markers) found.set(marker.point_start, [...(found.get(marker.point_start) ?? []), marker]);
  return found;
}

function ConfounderNote({ changes }: { changes: TimeSeries["document_changes"] }) {
  if (changes.changed === 0 && changes.deleted === 0) return null;
  const parts = [];
  if (changes.changed > 0) parts.push(`${String(changes.changed)} added, replaced or processed again`);
  if (changes.deleted > 0) parts.push(`${String(changes.deleted)} deleted`);
  return (
    <p role="note" className="mt-4 rounded border border-flag bg-flag-soft p-3 text-sm text-flag">
      {`Documents changed during this period: ${parts.join(", ")}. The Knowledge Base isn't versioned, so these changes may confound the comparison: a difference across a marker may come from the Documents rather than the Version.`}
    </p>
  );
}

function Chart({ series }: { series: TimeSeries }) {
  const { label, format, sample } = METRICS[series.metric];
  const byPoint = markersByPoint(series.markers);
  return (
    <figure className="mt-4">
      <figcaption className="text-sm text-muted">
        {`${label} per ${series.granularity}, from ${series.start} until ${series.end} (UTC), today so far included. Every Version of the Agent together; the Playground is left out. Dashed lines mark where the Live Version changed.`}
      </figcaption>
      <div className="mt-2 overflow-x-auto">
        <LineChart
          width={720}
          height={280}
          data={series.points.map((p) => ({ start: p.start, value: p.value }))}
          margin={{ top: 24, right: 24, bottom: 8, left: 8 }}
          accessibilityLayer
        >
          <CartesianGrid stroke="#e2e8f0" />
          <XAxis dataKey="start" tick={{ fill: "#334155", fontSize: 12 }} />
          <YAxis tick={{ fill: "#334155", fontSize: 12 }} tickFormatter={format} width={72} />
          <Tooltip />
          <Line type="monotone" dataKey="value" name={label} stroke="#1d4ed8" strokeWidth={2} isAnimationActive={false} />
          {[...byPoint].map(([start, markers]) => (
            <ReferenceLine
              key={start}
              x={start}
              stroke="#b45309"
              strokeDasharray="4 2"
              label={{ value: markers.map((m) => `v${String(m.to_version.number)}`).join(", "), position: "top", fill: "#78350f", fontSize: 12 }}
            />
          ))}
        </LineChart>
      </div>
      <h4 className="mt-4 text-sm font-medium">Live Version changes</h4>
      {series.markers.length === 0 ? (
        <p className="text-sm text-muted">None in this period.</p>
      ) : (
        <ul aria-label="Live Version changes" className="list-inside list-disc text-sm">
          {series.markers.map((marker) => (
            <li key={marker.occurred_at}>{`${marker.day}: ${change(marker)}`}</li>
          ))}
        </ul>
      )}
      <table className="mt-4 w-full text-left text-sm">
        <caption className="text-left font-medium">{`${label}, the numbers behind the chart`}</caption>
        <thead>
          <tr>
            <th scope="col">Period</th>
            <th scope="col">{label}</th>
            <th scope="col">{`n (${sample})`}</th>
          </tr>
        </thead>
        <tbody>
          {series.points.map((point) => (
            <tr key={point.start}>
              <th scope="row" className="font-normal">
                {period(point)}
              </th>
              <td>{point.value === null ? "No data" : format(point.value)}</td>
              <td>{point.n}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

function failure(error: Error): string {
  return error instanceof ProjectRequestError && error.status === 422
    ? "Check the dates: From can't be after To, and the range can be at most 366 days."
    : "The time series could not be loaded. Try again shortly.";
}

/**
 * The Agent's time series: one metric per day, week or month over the tab's date range, with
 * markers where the Live Version changed and a confounder note when Documents changed.
 */
export function TimeSeriesChart({
  organisationId,
  projectId,
  agentId,
  range,
}: {
  organisationId: string;
  projectId: string;
  agentId: string;
  range: MetricsRange;
}) {
  const [metric, setMetric] = useState<TimeSeriesMetric>("conversations");
  const [granularity, setGranularity] = useState<TimeSeriesGranularity>("day");
  const series = useTimeSeries(organisationId, projectId, agentId, metric, granularity, range);

  let body;
  if (series.isPending) {
    body = <p role="status">Loading the time series…</p>;
  } else if (series.isError) {
    body = <p role="alert">{failure(series.error)}</p>;
  } else {
    body = (
      <>
        <Chart series={series.data} />
        <ConfounderNote changes={series.data.document_changes} />
      </>
    );
  }

  return (
    <section aria-labelledby="time-series-heading" className="mt-8">
      <h3 id="time-series-heading" className="text-base font-semibold">
        Over time
      </h3>
      <fieldset className="mt-2 flex flex-wrap items-end gap-4">
        <legend className="sr-only">Choose the time series</legend>
        <label className="flex flex-col gap-1 text-sm">
          Metric
          <select
            className={INPUT}
            value={metric}
            onChange={(event) => {
              setMetric(event.currentTarget.value as TimeSeriesMetric);
            }}
          >
            {Object.entries(METRICS).map(([value, { label }]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Granularity
          <select
            className={INPUT}
            value={granularity}
            onChange={(event) => {
              setGranularity(event.currentTarget.value as TimeSeriesGranularity);
            }}
          >
            {Object.entries(GRANULARITIES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </fieldset>
      {body}
    </section>
  );
}
