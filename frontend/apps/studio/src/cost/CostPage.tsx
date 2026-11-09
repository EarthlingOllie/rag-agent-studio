import { useState } from "react";

import { dollars } from "../projects/format";
import { ProjectRequestError } from "../projects/projects";
import { INPUT, useOrganisationRole } from "../projects/ProjectsPage";
import { type CostGroup, type CostQuery, type OrgCost, useOrgCost } from "./cost";

const CELL = "py-2 pr-4";
const AMOUNT = "py-2 pr-4 text-right tabular-nums";

function failure(error: Error): string {
  return error instanceof ProjectRequestError && error.status === 422
    ? "Check the dates: From can't be after To, and the period can be at most 366 days."
    : "The cost could not be loaded. Try again shortly.";
}

function CostTable({ cost }: { cost: OrgCost }) {
  const byAgent = cost.group_by === "agent";
  const name = byAgent ? "Agent" : "Project";
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full text-left text-sm" aria-label={`Cost by ${name}`}>
        <thead>
          <tr className="text-slate-700">
            <th scope="col" className={`${CELL} font-medium`}>{name}</th>
            {byAgent && <th scope="col" className={`${CELL} font-medium`}>Project</th>}
            <th scope="col" className={`${AMOUNT} font-medium`}>Visitors</th>
            <th scope="col" className={`${AMOUNT} font-medium`}>Playground</th>
            <th scope="col" className={`${AMOUNT} font-medium`}>Total</th>
          </tr>
        </thead>
        <tbody>
          {cost.rows.map((row) => (
            <tr key={row.agent_id ?? row.project_id} className="border-t border-slate-200">
              <th scope="row" className={`${CELL} font-normal`}>{byAgent ? row.agent_name : row.project_name}</th>
              {byAgent && <td className={CELL}>{row.project_name}</td>}
              <td className={AMOUNT}>{dollars(row.visitor_usd)}</td>
              <td className={AMOUNT}>{dollars(row.playground_usd)}</td>
              <td className={AMOUNT}>{dollars(row.total_usd)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-slate-400 font-medium">
            <th scope="row" className={CELL}>{`All ${name}s`}</th>
            {byAgent && <td className={CELL} />}
            <td className={AMOUNT}>{dollars(cost.total.visitor_usd)}</td>
            <td className={AMOUNT}>{dollars(cost.total.playground_usd)}</td>
            <td className={AMOUNT}>{dollars(cost.total.total_usd)}</td>
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
    body = <p role="status" className="mt-4">Loading the cost…</p>;
  } else if (cost.isError) {
    body = <p role="alert" className="mt-4 text-red-800">{failure(cost.error)}</p>;
  } else {
    body = (
      <>
        <p className="mt-4 text-sm text-slate-700">
          {`${cost.data.start} to ${cost.data.end} (UTC days), including today so far, at the prices of the time.`}
        </p>
        {cost.data.rows.length === 0 ? <p className="mt-4 text-slate-700">Nothing was spent in this period.</p> : <CostTable cost={cost.data} />}
      </>
    );
  }

  return (
    <>
      <fieldset className="mt-4 flex flex-wrap items-end gap-4">
        <legend className="sr-only">Choose what to show</legend>
        <label className="flex flex-col gap-1 text-sm">
          Break down by
          <select
            className={INPUT}
            value={query.groupBy}
            onChange={(event) => {
              const groupBy = event.currentTarget.value as CostGroup;
              setQuery((current) => ({ ...current, groupBy }));
            }}
          >
            <option value="project">Project</option>
            <option value="agent">Agent</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          From (UTC)
          <input type="date" className={INPUT} value={query.from ?? ""} onChange={day("from")} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          To (UTC)
          <input type="date" className={INPUT} value={query.to ?? ""} onChange={day("to")} />
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
    <section aria-labelledby="page-heading">
      <h1 id="page-heading" className="text-2xl font-semibold">
        Organisation cost
      </h1>
      {isOwner ? (
        <>
          <p className="mt-2 text-slate-700">
            What Visitors' Conversations and Playground testing cost, at the prices frozen when each reply was made.
          </p>
          <OrgCostReport organisationId={organisationId} />
        </>
      ) : (
        <p className="mt-2 text-slate-700">Only Owners can see what the Organisation spends.</p>
      )}
    </section>
  );
}
