import { useId, useState } from "react";
import { Area, CartesianGrid, ComposedChart, ReferenceArea, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";

import { Icon, Notice, Segmented, Skeleton, field, notice, surface, table, text } from "../design";

import { type MetricsRange, type TimeSeries, type TimeSeriesGranularity, type TimeSeriesMetric, useTimeSeries } from "./analytics";
import { ProjectRequestError } from "./projects";

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
    <p role="note" className={`${notice.warning} flex items-start gap-2`}>
      <Icon name="warning" className="mt-0.5 shrink-0" />
      <span>
        {`Documents changed during this period: ${parts.join(", ")}. The Knowledge Base isn't versioned, so these changes may confound the comparison: a difference across a marker may come from the Documents rather than the Version.`}
      </span>
    </p>
  );
}

// The chart's size and margins; the plot runs between the y-axis and the right margin.
const WIDTH = 720;
const HEIGHT = 280;
const MARGIN = { top: 36, right: 24, bottom: 8, left: 8 };
const Y_AXIS = 72;
const TICK = { fill: "var(--ds-muted)", fontSize: 12 };

/** A Live marker's pill, centred on top of its dashed rule. */
function MarkerLabel({ viewBox, value }: { viewBox?: { x: number; y: number }; value: string }) {
  const { x, y } = viewBox as { x: number; y: number };
  const width = value.length * 7 + 16;
  return (
    <g>
      <rect x={x - width / 2} y={y - 26} width={width} height={20} rx={10} fill="var(--ds-surface)" stroke="var(--ds-field)" />
      <text x={x} y={y - 12} textAnchor="middle" fill="var(--ds-ink-2)" fontSize={12} fontFamily="var(--font-mono)">
        {value}
      </text>
    </g>
  );
}

/** The Documents-changed band's label: a warning icon and the words, at the band's top left. */
function BandLabel({ viewBox }: { viewBox?: { x: number; y: number } }) {
  const { x, y } = viewBox as { x: number; y: number };
  return (
    <g transform={`translate(${String(x + 8)} ${String(y + 8)})`} className="text-flag">
      <Icon name="warning" size={14} />
      <text x={20} y={11} fill="var(--ds-flag)" fontSize={12}>
        Documents changed
      </text>
    </g>
  );
}

/** The crosshair's horizontal rule across the plot, and the dot where it meets the line. */
function Crosshair({ cx, cy }: { cx?: number; cy?: number }) {
  return (
    <g>
      <line x1={MARGIN.left + Y_AXIS} x2={WIDTH - MARGIN.right} y1={cy} y2={cy} stroke="var(--ds-field)" strokeDasharray="3 3" />
      <circle cx={cx} cy={cy} r={4.5} fill="var(--ds-surface)" stroke="var(--ds-chart-1)" strokeWidth={2} />
    </g>
  );
}

/** The hover readout: the period, the value and its sample size. */
function Readout({
  active,
  payload,
  metric,
}: {
  active?: boolean;
  payload?: { payload: Point }[];
  metric: (typeof METRICS)[TimeSeriesMetric];
}) {
  const point = payload?.[0]?.payload;
  if (active !== true || point === undefined) return null;
  return (
    <div role="status" aria-label="Chart readout" className={`${surface.popover} px-3 py-2 text-xs text-ink-2`}>
      <p className="font-mono text-ink">{period(point)}</p>
      <p>
        {metric.label} <span className="font-mono text-ink">{point.value === null ? "No data" : metric.format(point.value)}</span>
      </p>
      <p className="text-muted">{`n = ${String(point.n)} ${metric.sample}`}</p>
    </div>
  );
}

function Chart({ series }: { series: TimeSeries }) {
  const metric = METRICS[series.metric];
  const byPoint = markersByPoint(series.markers);
  const { changed, deleted } = series.document_changes;
  const first = series.points[0];
  const last = series.points.at(-1);
  return (
    <div className="overflow-x-auto">
      <ComposedChart width={WIDTH} height={HEIGHT} data={series.points} margin={MARGIN} accessibilityLayer>
        {changed + deleted > 0 && first !== undefined && last !== undefined && (
          <ReferenceArea x1={first.start} x2={last.start} fill="var(--ds-flag-soft)" fillOpacity={1} label={<BandLabel />} />
        )}
        <CartesianGrid stroke="var(--ds-line-soft)" vertical={false} />
        <XAxis dataKey="start" tick={TICK} tickLine={false} axisLine={{ stroke: "var(--ds-line)" }} />
        <YAxis tick={TICK} tickFormatter={metric.format} width={Y_AXIS} tickLine={false} axisLine={false} />
        <Tooltip
          cursor={{ stroke: "var(--ds-field)", strokeDasharray: "3 3" }}
          content={<Readout metric={metric} />}
          filterNull={false}
          isAnimationActive={false}
        />
        <Area
          type="monotone"
          dataKey="value"
          name={metric.label}
          stroke="var(--ds-chart-1)"
          strokeWidth={2}
          fill="var(--ds-chart-1)"
          fillOpacity={0.12}
          activeDot={<Crosshair />}
          isAnimationActive={false}
        />
        {[...byPoint].map(([start, markers]) => (
          <ReferenceLine
            key={start}
            x={start}
            stroke="var(--ds-muted)"
            strokeDasharray="4 3"
            label={<MarkerLabel value={markers.map((m) => `v${String(m.to_version.number)}`).join(", ")} />}
          />
        ))}
      </ComposedChart>
    </div>
  );
}

function NumbersTable({ series }: { series: TimeSeries }) {
  const { label, format, sample } = METRICS[series.metric];
  return (
    // A focusable region, so the table can be scrolled sideways with the keyboard on a narrow screen.
    <div className={table.wrap} role="region" aria-label={`${label}, the numbers behind the chart`} tabIndex={0}>
      <table className={table.table}>
        <caption className="sr-only">{`${label}, the numbers behind the chart`}</caption>
        <thead>
          <tr>
            <th scope="col" className={table.th}>
              Period
            </th>
            <th scope="col" className={table.thNumeric}>
              {label}
            </th>
            <th scope="col" className={table.thNumeric}>{`n (${sample})`}</th>
          </tr>
        </thead>
        <tbody>
          {series.points.map((point) => (
            <tr key={point.start} className={table.row}>
              <th scope="row" className={`${table.td} text-left font-mono text-[13px] font-normal`}>
                {period(point)}
              </th>
              <td className={table.tdNumeric}>{point.value === null ? "No data" : format(point.value)}</td>
              <td className={table.tdNumeric}>{point.n}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The series as a chart or a table, the Live Version changes, and the Documents note. */
function Series({ series }: { series: TimeSeries }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const captionId = useId();
  const { label } = METRICS[series.metric];
  return (
    <figure aria-labelledby={captionId} className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <figcaption id={captionId} className={`${text.muted} max-w-2xl`}>
          {`${label} per ${series.granularity}, from ${series.start} until ${series.end} (UTC), today so far included. Every Version of the Agent together; the Playground is left out. Dashed lines mark where the Live Version changed.`}
        </figcaption>
        <Segmented label="Show as" options={VIEWS} value={view} onChange={setView} />
      </div>
      {view === "chart" ? <Chart series={series} /> : <NumbersTable series={series} />}
      <ConfounderNote changes={series.document_changes} />
      <div>
        <h4 className="text-sm font-medium text-ink">Live Version changes</h4>
        {series.markers.length === 0 ? (
          <p className={text.muted}>None in this period.</p>
        ) : (
          <ul aria-label="Live Version changes" className="mt-1 flex flex-col gap-0.5 text-sm text-ink-2">
            {series.markers.map((marker) => (
              <li key={marker.occurred_at}>
                <span className="font-mono text-[13px]">{marker.day}</span>
                {`: ${change(marker)}`}
              </li>
            ))}
          </ul>
        )}
      </div>
    </figure>
  );
}

const VIEWS = [
  { value: "chart", label: "Chart" },
  { value: "table", label: "Table" },
] as const;

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
    body = <Skeleton label="Loading the time series" />;
  } else if (series.isError) {
    body = <Notice tone="error">{failure(series.error)}</Notice>;
  } else {
    body = <Series series={series.data} />;
  }

  return (
    <section aria-labelledby="time-series-heading" className="flex flex-col gap-4">
      <h3 id="time-series-heading" className={text.heading}>
        Over time
      </h3>
      <fieldset className="flex flex-wrap items-end gap-3">
        <legend className="sr-only">Choose the time series</legend>
        <label className={field.filter}>
          Metric
          <select
            className={field.pill}
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
        <label className={field.filter}>
          Granularity
          <select
            className={field.pill}
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
