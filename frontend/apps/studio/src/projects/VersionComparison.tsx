import { useState } from "react";

import { AgentDiffView } from "./AgentDiff";
import { useTagNames } from "./AgentPublish";
import { type MetricRow, type MetricsRange, type VersionKpis, comparisonCsvUrl, useVersionComparison } from "./analytics";
import { dollars, duration } from "./format";
import { Notice, Skeleton, button, field, table, text } from "../design";

const percent = (rate: number) => `${String(Math.round(rate * 100))}%`;

/** A metric's value as a person reads it, by its unit. */
function value(unit: MetricRow["unit"], amount: number): string {
  switch (unit) {
    case "usd":
      return dollars(String(amount));
    case "rate":
      return percent(amount);
    case "rating":
    case "searches":
      return amount.toFixed(2);
    case "ms":
      return duration(amount);
    default:
      // Counts and tokens, as whole numbers.
      return String(Math.round(amount));
  }
}

/** b minus a, signed: rates in percentage points, the rest in the metric's unit. */
function difference(row: MetricRow): string {
  if (!row.changed) return "Same";
  if (row.difference === null) return "—";
  const sign = row.difference > 0 ? "+" : "−";
  const size = Math.abs(row.difference);
  return row.unit === "rate" ? `${sign}${String(Math.round(size * 100))} pts` : `${sign}${value(row.unit, size)}`;
}

const label = (kpis: VersionKpis) => `v${String(kpis.number)}`;

function ComparisonTable({ rows, a, b }: { rows: MetricRow[]; a: VersionKpis; b: VersionKpis }) {
  const name = { a: label(a), b: label(b) };
  return (
    // A focusable region, so the table can be scrolled sideways with the keyboard on a narrow screen.
    <div className={table.wrap} role="region" aria-label={`${name.a} compared with ${name.b}`} tabIndex={0}>
    <table aria-label={`${name.a} compared with ${name.b}`} className={table.table}>
      <thead>
        <tr>
          <th scope="col" className={table.th}>
            Metric
          </th>
          <th scope="col" className={table.thNumeric}>
            {name.a}
          </th>
          <th scope="col" className={table.thNumeric}>
            {name.b}
          </th>
          <th scope="col" className={table.thNumeric}>{`Difference (${name.b} − ${name.a})`}</th>
          <th scope="col" className={table.th}>
            Better
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          // Rows whose values differ are highlighted; the difference and the better Version are in words too.
          <tr key={row.metric} className={row.changed ? `${table.row} bg-flag-soft` : table.row}>
            <th scope="row" className={`${table.td} text-left font-normal`}>
              {row.label}
              {row.low_confidence && (
                <>
                  {" "}
                  <span className="text-muted">(small sample)</span>
                </>
              )}
            </th>
            <td className={table.tdNumeric}>{row.a === null ? "—" : value(row.unit, row.a)}</td>
            <td className={table.tdNumeric}>{row.b === null ? "—" : value(row.unit, row.b)}</td>
            <td className={`${table.tdNumeric} ${row.changed ? "font-semibold" : ""}`}>{difference(row)}</td>
            <td className={`${table.td} font-mono text-[13px] font-semibold`}>{row.better === null ? "" : name[row.better]}</td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}

function Compared({
  organisationId,
  projectId,
  agentId,
  sides,
  range,
}: {
  organisationId: string;
  projectId: string;
  agentId: string;
  sides: { a: string; b: string };
  range: MetricsRange;
}) {
  const comparison = useVersionComparison(organisationId, projectId, agentId, sides, range);
  const names = useTagNames(organisationId, projectId);
  if (sides.a === sides.b) return <p className={text.muted}>Pick two different Versions to compare.</p>;
  if (comparison.isPending) return <Skeleton label="Comparing the Versions" />;
  if (comparison.isError) return <Notice tone="error">The comparison could not be loaded. Try again shortly.</Notice>;
  const { a, b, metrics, config_diff: diff } = comparison.data;
  return (
    <>
      <p>
        <a className={button.secondary} href={comparisonCsvUrl(organisationId, projectId, agentId, sides, range)} download>
          Export as CSV
        </a>
      </p>
      <div className="grid gap-6 lg:grid-cols-2">
        <ComparisonTable rows={metrics} a={a} b={b} />
        <section aria-labelledby="config-changes-heading">
          <h4 id="config-changes-heading" className="mb-2 text-sm font-medium text-ink">
            Configuration changes
          </h4>
          <AgentDiffView diff={diff} names={names} modes={{ from: a.retrieval_mode, to: b.retrieval_mode }} />
        </section>
      </div>
    </>
  );
}

/**
 * Any two Versions of the Agent side by side over the chosen days: every metric with the differences highlighted and
 * the Version each favours, the configuration diff alongside, and a CSV export. By default the Live Version (else the
 * newest) against the newest other one.
 */
export function VersionComparison({
  organisationId,
  projectId,
  agentId,
  versions,
  range,
}: {
  organisationId: string;
  projectId: string;
  agentId: string;
  // Oldest first.
  versions: VersionKpis[];
  range: MetricsRange;
}) {
  const newestFirst = [...versions].reverse();
  const second = versions.find((v) => v.is_live) ?? newestFirst[0];
  const first = newestFirst.find((v) => v !== second);
  // What the Editor picked; the defaults until they pick.
  const [chosen, setChosen] = useState<{ a?: string; b?: string }>({});

  let body;
  if (first === undefined || second === undefined) {
    body = <p className={text.muted}>Publish another Version of this Agent to compare two.</p>;
  } else {
    const sides = { a: chosen.a ?? first.version_id, b: chosen.b ?? second.version_id };
    const picker = (side: "a" | "b", title: string) => (
      <label className={field.filter}>
        {title}
        <select
          className={field.pill}
          value={sides[side]}
          onChange={(event) => {
            const { value: id } = event.currentTarget;
            setChosen((current) => ({ ...current, [side]: id }));
          }}
        >
          {newestFirst.map((v) => (
            <option key={v.version_id} value={v.version_id}>
              {`v${String(v.number)}${v.is_live ? " (Live)" : ""}`}
            </option>
          ))}
        </select>
      </label>
    );
    body = (
      <>
        <fieldset className="flex flex-wrap items-end gap-3">
          <legend className="sr-only">Choose the two Versions</legend>
          {picker("a", "First Version")}
          {picker("b", "Second Version")}
        </fieldset>
        <Compared organisationId={organisationId} projectId={projectId} agentId={agentId} sides={sides} range={range} />
      </>
    );
  }

  return (
    <section className="flex flex-col gap-4">
      <h3 className={text.heading}>Compare two Versions</h3>
      {body}
    </section>
  );
}
