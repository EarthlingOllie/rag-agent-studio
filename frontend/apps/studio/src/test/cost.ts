import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { server } from "./server";

type CostRow = Schemas["CostRowOut"];

const handbook = { project_id: "c0570000-0000-4000-8000-000000000001", project_name: "Handbook" };
const payroll = { project_id: "c0570000-0000-4000-8000-000000000002", project_name: "Payroll" };

/** By Project: the Handbook was used by Visitors and in the Playground; Payroll only by Visitors. */
export const byProject: CostRow[] = [
  { ...handbook, agent_id: null, agent_name: null, visitor_usd: "12.500000000", playground_usd: "0.004200000", total_usd: "12.504200000" },
  { ...payroll, agent_id: null, agent_name: null, visitor_usd: "0.003000000", playground_usd: "0.000000000", total_usd: "0.003000000" },
];

/** By Agent: two of the Handbook's Agents (one tried only in the Playground) and Payroll's. */
export const byAgent: CostRow[] = [
  { ...handbook, agent_id: "a9e00000-0000-4000-8000-000000000001", agent_name: "HR helper", visitor_usd: "12.500000000", playground_usd: "0.000000000", total_usd: "12.500000000" },
  { ...handbook, agent_id: "a9e00000-0000-4000-8000-000000000002", agent_name: "Tried once", visitor_usd: "0.000000000", playground_usd: "0.004200000", total_usd: "0.004200000" },
  { ...payroll, agent_id: "a9e00000-0000-4000-8000-000000000003", agent_name: "Payroll helper", visitor_usd: "0.003000000", playground_usd: "0.000000000", total_usd: "0.003000000" },
];

function total(rows: CostRow[], key: "visitor_usd" | "playground_usd" | "total_usd"): string {
  return rows.reduce((sum, row) => sum + Number(row[key]), 0).toFixed(9);
}

/** Answers the org cost endpoint with these rows for each breakdown, recording queries. */
export function fakeCostApi(options: { rows?: { project: CostRow[]; agent: CostRow[] }; status?: number } = {}) {
  const queries: URLSearchParams[] = [];
  const rows = options.rows ?? { project: byProject, agent: byAgent };
  server.use(
    http.get("*/api/organisations/:organisationId/cost", ({ request }) => {
      const query = new URL(request.url).searchParams;
      queries.push(query);
      if (options.status) return HttpResponse.json({ detail: "Failed" }, { status: options.status });
      const start = query.get("start") ?? "2026-10-08";
      const end = query.get("end") ?? "2026-11-06";
      if (start > end) return HttpResponse.json({ detail: "The start must not be after the end." }, { status: 422 });
      const groupBy = query.get("group_by") === "agent" ? "agent" : "project";
      const shown = rows[groupBy];
      return HttpResponse.json({
        start,
        end,
        group_by: groupBy,
        rows: shown,
        total: { visitor_usd: total(shown, "visitor_usd"), playground_usd: total(shown, "playground_usd"), total_usd: total(shown, "total_usd") },
      });
    }),
  );
  return { queries };
}
