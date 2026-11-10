import { useState } from "react";

import { EmptyState, field, layout, Notice, PageHeader, Segmented, Skeleton, StatCard, table, text } from "../design";
import { dollars } from "../projects/format";
import { ProjectRequestError } from "../projects/projects";
import { useOrganisationRole } from "../projects/ProjectsPage";
import { type CostGroup, type CostQuery, type OrgCost, useOrgCost } from "./cost";

const BREAKDOWNS = [
  { value: "project", label: "Project" },
  { value: "agent", label: "Agent" },
] as const satisfies readonly { value: CostGroup; label: string }[];

/** The total row, set apart from the rows above it. */
const TOTAL_ROW = "border-t border-line bg-sunken font-medium";

function failure(error: Error): string {
  return error instanceof ProjectRequestError && error.status === 422
    ? "Check the dates: From can't be after To, and the period can be at most 366 days."
    : "The cost could not be loaded. Try again shortly.";
}

/** The period's headline figures: everything, then Visitors and the Playground apart. */
function CostStats({ cost }: { cost: OrgCost }) {
  const figures = [
    { label: "Total", value: cost.total.total_usd },
    { label: "Visitors", value: cost.total.visitor_usd },
    { label: "Playground", value: cost.total.playground_usd },
  ];
  return (
    <ul aria-label="Spend for the period" className={layout.stats}>
      {figures.map((figure) => (
        <li key={figure.label}>
          <StatCard label={figure.label} value={dollars(figure.value)} />
        </li>
      ))}
    </ul>
  );
}

function CostTable({ cost }: { cost: OrgCost }) {
  const byAgent = cost.group_by === "agent";
  const name = byAgent ? "Agent" : "Project";
  return (
    // A focusable region, so the table can be scrolled sideways with the keyboard on a narrow screen.
    <div className={table.wrap} role="region" aria-label={`Cost by ${name}`} tabIndex={0}>
      <table className={table.table} aria-label={`Cost by ${name}`}>
        <thead>
          <tr>
            <th scope="col" className={table.th}>
              {name}
            </th>
            {byAgent && (
              <th scope="col" className={table.th}>
                Project
              </th>
            )}
            <th scope="col" className={table.thNumeric}>
              Visitors
            </th>
            <th scope="col" className={table.thNumeric}>
              Playground
            </th>
            <th scope="col" className={table.thNumeric}>
              Total
            </th>
          </tr>
        </thead>
        <tbody>
          {cost.rows.map((row) => (
            <tr key={row.agent_id ?? row.project_id} className={table.row}>
              <th scope="row" className={`${table.td} font-medium`}>
                {byAgent ? row.agent_name : row.project_name}
              </th>
              {byAgent && <td className={table.tdMuted}>{row.project_name}</td>}
              <td className={table.tdNumeric}>{dollars(row.visitor_usd)}</td>
              <td className={table.tdNumeric}>{dollars(row.playground_usd)}</td>
              <td className={table.tdNumeric}>{dollars(row.total_usd)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className={TOTAL_ROW}>
            <th scope="row" className={`${table.td} text-left`}>{`All ${name}s`}</th>
            {byAgent && <td className={table.td} />}
            <td className={`${table.tdNumeric} font-medium`}>{dollars(cost.total.visitor_usd)}</td>
            <td className={`${table.tdNumeric} font-medium`}>{dollars(cost.total.playground_usd)}</td>
            <td className={`${table.tdNumeric} font-medium`}>{dollars(cost.total.total_usd)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function OrgCostReport({ organisationId }: { organisationId: string }) {
  const [query, setQuery] = useState<CostQuery>({ groupBy: "project" });
  const cost = useOrgCost(organisationId, query);
  const day = (key: "from" | "to") => (event: { currentTarget: { value: string } }) => {
    const { value } = event.currentTarget;
    setQuery((current) => ({ ...current, [key]: value === "" ? undefined : value }));
  };

  let body;
  if (cost.isPending) {
    body = <Skeleton label="Loading the cost" />;
  } else if (cost.isError) {
    body = <Notice tone="error">{failure(cost.error)}</Notice>;
  } else {
    body = (
      <>
        <p className={text.muted}>
          {`${cost.data.start} to ${cost.data.end} (UTC days), including today so far, at the prices of the time.`}
        </p>
        {cost.data.rows.length === 0 ? (
          <EmptyState
            icon="analytics"
            title="Nothing was spent in this period"
            description="Visitors' Conversations and Playground testing in any Project show up here, with what they cost."
          />
        ) : (
          <>
            <CostStats cost={cost.data} />
            <CostTable cost={cost.data} />
          </>
        )}
      </>
    );
  }

  return (
    <>
      <fieldset className="flex flex-wrap items-end gap-3">
        <legend className="sr-only">Choose what to show</legend>
        <Segmented
          label="Break down by"
          options={BREAKDOWNS}
          value={query.groupBy}
          onChange={(groupBy) => {
            setQuery((current) => ({ ...current, groupBy }));
          }}
        />
        <label className={field.filter}>
          From (UTC)
          <input type="date" className={field.pill} value={query.from ?? ""} onChange={day("from")} />
        </label>
        <label className={field.filter}>
          To (UTC)
          <input type="date" className={field.pill} value={query.to ?? ""} onChange={day("to")} />
        </label>
      </fieldset>
      {body}
    </>
  );
}

/** The Organisation cost page: what the Organisation spent over a period, by Project or by Agent, with Playground usage in its own column. Owners only. */
export function CostPage() {
  const { organisationId, isOwner } = useOrganisationRole();
  return (
    <div className={layout.stack}>
      <PageHeader
        title="Organisation cost"
        description={
          isOwner
            ? "What Visitors' Conversations and Playground testing cost, at the prices frozen when each reply was made."
            : undefined
        }
      />
      {isOwner ? (
        <OrgCostReport organisationId={organisationId} />
      ) : (
        <EmptyState
          icon="members"
          title="Only Owners see the Organisation's spend"
          description="Ask an Owner of this Organisation if you need to know what it spent."
        />
      )}
    </div>
  );
}
