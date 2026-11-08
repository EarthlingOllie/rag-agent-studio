import type { Schemas } from "@studio/api-client";
import { http, HttpResponse } from "msw";

import { server } from "./server";

type VersionKpis = Schemas["VersionKpisOut"];
type TimeSeries = Schemas["TimeSeriesOut"];
type Marker = TimeSeries["markers"][number];

/** A Version's KPIs with nothing measured; override what a test needs. */
export function versionKpis(number: number, overrides: Partial<VersionKpis> = {}): VersionKpis {
  return {
    version_id: `a1e00000-0000-4000-8000-${String(number).padStart(12, "0")}`,
    number,
    is_live: false,
    conversations: 0,
    messages: 0,
    low_confidence: true,
    tokens: { n: 0, mean: null, p95: null },
    cost: { total_usd: "0.000000000", per_conversation_usd: null },
    thumbs_up: { up: 0, down: 0, n: 0, rate: null, low: null, high: null, low_confidence: true },
    rating: { n: 0, mean: null, low_confidence: true },
    fallback: { count: 0, rate: null },
    latency: { n: 0, first_token_p95_ms: null, total_p95_ms: null },
    ...overrides,
  };
}

/** v2, Live, with a small sample: three Conversations, two thumbs up out of three votes. */
export const smallSample = versionKpis(2, {
  is_live: true,
  conversations: 3,
  messages: 4,
  tokens: { n: 3, mean: 120.4, p95: 300.2 },
  cost: { total_usd: "0.003600000", per_conversation_usd: "0.001200000" },
  thumbs_up: { up: 2, down: 1, n: 3, rate: 2 / 3, low: 0.2076596, high: 0.9385081, low_confidence: true },
  rating: { n: 2, mean: 3.5, low_confidence: true },
  fallback: { count: 1, rate: 0.25 },
  latency: { n: 4, first_token_p95_ms: 320.4, total_p95_ms: 1480 },
});

/** v1, with enough evidence: no number is low confidence. */
export const largeSample = versionKpis(1, {
  conversations: 120,
  messages: 400,
  low_confidence: false,
  tokens: { n: 390, mean: 512, p95: 1890 },
  cost: { total_usd: "150.000000000", per_conversation_usd: "1.250000000" },
  thumbs_up: { up: 24, down: 6, n: 30, rate: 0.8, low: 0.626943, high: 0.9049489, low_confidence: false },
  rating: { n: 40, mean: 4.25, low_confidence: false },
  fallback: { count: 0, rate: 0 },
  latency: { n: 400, first_token_p95_ms: 950, total_p95_ms: 2400 },
});

/** Answers the Version metrics endpoint with each Agent's Versions (oldest first), recording queries. */
export function fakeMetricsApi(options: { versions?: Record<string, VersionKpis[]>; status?: number } = {}) {
  const queries: { agentId: string; query: URLSearchParams }[] = [];
  fakeTimeSeriesApi();
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/metrics", ({ params, request }) => {
      const query = new URL(request.url).searchParams;
      const agentId = String(params.agentId);
      queries.push({ agentId, query });
      if (options.status) return HttpResponse.json({ detail: "Failed" }, { status: options.status });
      const start = query.get("start") ?? "2026-10-08";
      const end = query.get("end") ?? "2026-11-06";
      if (start > end) return HttpResponse.json({ detail: "The start must not be after the end." }, { status: 422 });
      return HttpResponse.json({ agent_id: agentId, start, end, versions: options.versions?.[agentId] ?? [] });
    }),
  );
  return { queries };
}

/** A Live History marker on the day given (and the point starting then, unless given). */
export function marker(day: string, from: number | null, to: number, action = "publish", pointStart = day): Marker {
  const version = (number: number) => ({ id: `a1e00000-0000-4000-8000-${String(number).padStart(12, "0")}`, number });
  return {
    occurred_at: `${day}T10:00:00Z`,
    day,
    point_start: pointStart,
    action,
    from_version: from === null ? null : version(from),
    to_version: version(to),
  };
}

/** Points of a series, from [start, end, value, n]. */
export function seriesPoints(...points: [string, string, number | null, number][]): TimeSeries["points"] {
  return points.map(([start, end, value, n]) => ({ start, end, value, n }));
}

/**
 * Answers the time series endpoint, recording queries. ``respond`` builds each answer from the
 * query (the metric, granularity and range asked for); by default four empty days.
 */
export function fakeTimeSeriesApi(
  options: { respond?: (query: URLSearchParams) => Partial<TimeSeries>; status?: number } = {},
) {
  const queries: { agentId: string; query: URLSearchParams }[] = [];
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/time-series", ({ params, request }) => {
      const query = new URL(request.url).searchParams;
      const agentId = String(params.agentId);
      queries.push({ agentId, query });
      if (options.status) return HttpResponse.json({ detail: "Failed" }, { status: options.status });
      const series: TimeSeries = {
        agent_id: agentId,
        metric: (query.get("metric") ?? "conversations") as TimeSeries["metric"],
        granularity: (query.get("granularity") ?? "day") as TimeSeries["granularity"],
        start: query.get("start") ?? "2026-11-03",
        end: query.get("end") ?? "2026-11-06",
        points: seriesPoints(
          ["2026-11-03", "2026-11-03", 0, 0],
          ["2026-11-04", "2026-11-04", 0, 0],
          ["2026-11-05", "2026-11-05", 0, 0],
          ["2026-11-06", "2026-11-06", 0, 0],
        ),
        markers: [],
        document_changes: { changed: 0, deleted: 0 },
        ...options.respond?.(query),
      };
      return HttpResponse.json(series);
    }),
  );
  return { queries };
}
