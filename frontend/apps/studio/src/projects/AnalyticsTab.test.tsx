import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { fakeAgentsApi, hrHelper } from "../test/agents";
import {
  fakeComparisonApi,
  fakeMetricsApi,
  largeSample,
  smallSample,
  v1AgainstV2Metrics,
  v1ToV2Diff,
  versionComparison,
  versionKpis,
} from "../test/analytics";
import { adaSession, fakeAuthApi, type Session } from "../test/auth";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const analyticsTab = `/organisations/${organisationId}/projects/${hrProject.id}/analytics`;
const editorSession: Session = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};
const payHelper = { ...hrHelper, id: "a9e00000-0000-4000-8000-000000000009", name: "Pay helper" };

function setUp(options: Parameters<typeof fakeMetricsApi>[0] = { versions: { [hrHelper.id]: [largeSample, smallSample] } }) {
  fakeAuthApi({ signedInAs: editorSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [hrHelper, payHelper] });
  fakeComparisonApi();
  return fakeMetricsApi(options);
}

/** A KPI card's text, as the Editor reads it. */
function card(title: string): string {
  return screen.getByRole("listitem", { name: title }).textContent;
}

const lowConfidence = (title: string) => card(title).includes("Low confidence");

test("an Editor sees the Live Version's KPI cards, with the interval and sample size, small samples marked", async () => {
  const { queries } = setUp();
  renderStudio(analyticsTab);

  expect(await screen.findByRole("list", { name: "Key numbers for v2" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 2, name: "Analytics" })).toBeInTheDocument();
  expect(screen.getByLabelText("Agent")).toHaveDisplayValue("HR helper");
  expect(screen.getByLabelText("Version")).toHaveDisplayValue("v2 (Live)");
  expect(within(screen.getByLabelText("Version")).getAllByRole("option").map((o) => o.textContent)).toEqual(["v2 (Live)", "v1"]);
  expect(screen.getByText(/2026-10-08 to 2026-11-06 \(UTC days\), including today so far/)).toBeInTheDocument();
  expect(card("Volume")).toBe("Volume3 Conversations4 repliesLow confidence (fewer than 30 Conversations)");
  expect(card("Tokens per reply")).toBe("Tokens per reply120 meanp95 300n = 3 replies that asked a model");
  expect(card("Cost per Conversation")).toBe("Cost per Conversation$0.0012$0.0036 in total, at the prices of the time");
  expect(card("Thumbs-up rate")).toBe(
    "Thumbs-up rate67%95% interval 21% to 94%n = 3 votes (2 up, 1 down)Low confidence (fewer than 30 votes)",
  );
  expect(card("Mean rating")).toBe("Mean rating3.5 of 5n = 2 ratingsLow confidence (fewer than 30 ratings)");
  expect(card("Fallback rate")).toBe("Fallback rate25%1 of 4 replies were the fallback text");
  expect(card("Guardrail block rate")).toBe("Guardrail block rate50%2 of 4 replies were blocked by the input Guardrail");
  expect(card("p95 latency")).toBe("p95 latency1.5 sFirst token 320 msn = 4 replies");
  // Every Version is fetched at once, for the last 30 days.
  expect(queries.map(({ agentId, query }) => [agentId, query.toString()])).toEqual([[hrHelper.id, ""]]);
});

test("a Version with enough evidence has no low-confidence marks", async () => {
  setUp();
  renderStudio(analyticsTab);
  await screen.findByRole("list", { name: "Key numbers for v2" });

  await userEvent.selectOptions(screen.getByLabelText("Version"), "v1");

  expect(screen.getByRole("list", { name: "Key numbers for v1" })).toBeInTheDocument();
  expect(screen.queryByText(/Low confidence/)).not.toBeInTheDocument();
  expect(["Volume", "Thumbs-up rate", "Mean rating"].map(lowConfidence)).toEqual([false, false, false]);
  expect(card("Volume")).toBe("Volume120 Conversations400 replies");
  expect(card("Thumbs-up rate")).toBe("Thumbs-up rate80%95% interval 63% to 90%n = 30 votes (24 up, 6 down)");
  expect(card("Cost per Conversation")).toBe("Cost per Conversation$1.25$150.00 in total, at the prices of the time");
  expect(card("Mean rating")).toBe("Mean rating4.3 of 5n = 40 ratings");
  expect(card("Fallback rate")).toBe("Fallback rate0%0 of 400 replies were the fallback text");
  // Under one percent shows a decimal, so a small block rate doesn't read as none.
  expect(card("Guardrail block rate")).toBe("Guardrail block rate0.8%3 of 400 replies were blocked by the input Guardrail");
  expect(card("p95 latency")).toBe("p95 latency2.4 sFirst token 950 msn = 400 replies");
});

test("a Version with no Visitor use yet says so on every card", async () => {
  setUp({ versions: { [hrHelper.id]: [versionKpis(1, { is_live: true })] } });
  renderStudio(analyticsTab);

  expect(await screen.findByRole("list", { name: "Key numbers for v1" })).toBeInTheDocument();
  expect(card("Volume")).toBe("Volume0 Conversations0 repliesLow confidence (fewer than 30 Conversations)");
  expect(card("Tokens per reply")).toBe("Tokens per replyNo replies yetn = 0 replies that asked a model");
  expect(card("Cost per Conversation")).toBe("Cost per ConversationNo Conversations yet$0.00 in total, at the prices of the time");
  expect(card("Thumbs-up rate")).toBe("Thumbs-up rateNo votes yetn = 0 votes (0 up, 0 down)Low confidence (fewer than 30 votes)");
  expect(card("Mean rating")).toBe("Mean ratingNo ratings yetn = 0 ratingsLow confidence (fewer than 30 ratings)");
  expect(card("Fallback rate")).toBe("Fallback rateNo replies yet0 of 0 replies were the fallback text");
  expect(card("Guardrail block rate")).toBe("Guardrail block rateNo replies yet0 of 0 replies were blocked by the input Guardrail");
  expect(card("p95 latency")).toBe("p95 latencyNo replies yetn = 0 replies");
});

test("one of each is counted in the singular", async () => {
  const one = versionKpis(3, {
    conversations: 1,
    messages: 1,
    tokens: { n: 1, mean: 80, p95: 80 },
    cost: { total_usd: "0.000000000", per_conversation_usd: "0.000000000" },
    thumbs_up: { up: 1, down: 0, n: 1, rate: 1, low: 0.2065493, high: 1, low_confidence: true },
    rating: { n: 1, mean: 5, low_confidence: true },
    fallback: { count: 0, rate: 0 },
    guardrail_blocks: { count: 1, rate: 1 },
    latency: { n: 1, first_token_p95_ms: 0.4, total_p95_ms: 999 },
  });
  setUp({ versions: { [hrHelper.id]: [one] } });
  renderStudio(analyticsTab);

  // Not Live: the newest Version is shown.
  expect(await screen.findByRole("list", { name: "Key numbers for v3" })).toBeInTheDocument();
  expect(card("Volume")).toBe("Volume1 Conversation1 replyLow confidence (fewer than 30 Conversations)");
  expect(card("Tokens per reply")).toBe("Tokens per reply80 meanp95 80n = 1 reply that asked a model");
  expect(card("Cost per Conversation")).toBe("Cost per Conversation$0.00$0.00 in total, at the prices of the time");
  expect(card("Thumbs-up rate")).toBe("Thumbs-up rate100%95% interval 21% to 100%n = 1 vote (1 up, 0 down)Low confidence (fewer than 30 votes)");
  expect(card("Mean rating")).toBe("Mean rating5.0 of 5n = 1 ratingLow confidence (fewer than 30 ratings)");
  expect(card("Guardrail block rate")).toBe("Guardrail block rate100%1 of 1 reply was blocked by the input Guardrail");
  expect(card("p95 latency")).toBe("p95 latency999 msFirst token 0 msn = 1 reply");
});

test("the Editor chooses the days, and a range the API refuses is explained", async () => {
  const { queries } = setUp();
  renderStudio(analyticsTab);
  await screen.findByRole("list", { name: "Key numbers for v2" });

  await userEvent.type(screen.getByLabelText("From (UTC)"), "2026-11-01");
  await userEvent.type(screen.getByLabelText("To (UTC)"), "2026-11-03");

  expect(await screen.findByText(/2026-11-01 to 2026-11-03 \(UTC days\)/)).toBeInTheDocument();
  expect(queries.at(-1)?.query.toString()).toBe("start=2026-11-01&end=2026-11-03");

  await userEvent.clear(screen.getByLabelText("To (UTC)"));
  await userEvent.type(screen.getByLabelText("To (UTC)"), "2026-10-01");

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Check the dates: From can't be after To, and the range can be at most 366 days.",
  );

  await userEvent.clear(screen.getByLabelText("To (UTC)"));
  await userEvent.clear(screen.getByLabelText("From (UTC)"));

  expect(await screen.findByText(/2026-10-08 to 2026-11-06 \(UTC days\)/)).toBeInTheDocument();
  expect(queries.at(-1)?.query.toString()).toBe("");
});

test("choosing another Agent shows its Versions; one not yet published has none", async () => {
  const { queries } = setUp({ versions: { [hrHelper.id]: [largeSample, smallSample], [payHelper.id]: [] } });
  renderStudio(analyticsTab);
  await screen.findByRole("list", { name: "Key numbers for v2" });

  await userEvent.selectOptions(screen.getByLabelText("Agent"), "Pay helper");

  expect(
    await screen.findByText("This Agent has no Versions yet. Publish it, and Visitors' Conversations with each Version are measured here."),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Version")).toBeDisabled();
  expect(screen.queryByRole("list")).not.toBeInTheDocument();
  expect(queries.map(({ agentId }) => agentId)).toEqual([hrHelper.id, payHelper.id]);
});

test("metrics that fail to load say so", async () => {
  setUp({ status: 500 });
  renderStudio(analyticsTab);

  expect(await screen.findByRole("alert")).toHaveTextContent("The metrics could not be loaded. Try again shortly.");
});

test("the tab says so while the Agents load and when they can't be loaded", async () => {
  setUp();
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/agents", () =>
      HttpResponse.json({ detail: "Failed" }, { status: 500 }),
    ),
  );
  renderStudio(analyticsTab);

  expect(await screen.findByText("Loading the Agents…")).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent("The Agents could not be loaded. Try again shortly.");
});

// Version comparison

/** A comparison table row's cells after its metric, as the Editor reads them. */
function compared(metric: string): string[] {
  const header = within(screen.getByRole("table", { name: /compared with/ })).getByRole("rowheader", { name: metric });
  return within(header.closest("tr") as HTMLElement)
    .getAllByRole("cell")
    .map((cell) => cell.textContent);
}

const rowOf = (metric: string) => screen.getByRole("rowheader", { name: metric }).closest("tr") as HTMLElement;

test("an Editor compares two Versions side by side, with the differences highlighted", async () => {
  setUp();
  const { queries } = fakeComparisonApi();
  renderStudio(analyticsTab);

  const table = await screen.findByRole("table", { name: "v1 compared with v2" });
  expect(screen.getByRole("heading", { level: 3, name: "Compare two Versions" })).toBeInTheDocument();
  // The Live Version against the newest other one, by default.
  expect(screen.getByLabelText("First Version")).toHaveDisplayValue("v1");
  expect(screen.getByLabelText("Second Version")).toHaveDisplayValue("v2 (Live)");
  expect(within(table).getAllByRole("columnheader").map((c) => c.textContent)).toEqual([
    "Metric",
    "v1",
    "v2",
    "Difference (v2 − v1)",
    "Better",
  ]);
  expect(within(table).getAllByRole("rowheader").map((c) => c.textContent)).toEqual([
    "Conversations (small sample)",
    "Replies (small sample)",
    "Mean tokens per reply",
    "p95 tokens per reply",
    "Cost per Conversation (USD)",
    "Total cost (USD)",
    "Thumbs-up rate (small sample)",
    "Thumbs-up rate, 95% interval low (small sample)",
    "Thumbs-up rate, 95% interval high (small sample)",
    "Votes (small sample)",
    "Mean rating (small sample)",
    "Ratings (small sample)",
    "Fallback rate",
    "p95 time to first token (ms)",
    "p95 total latency (ms)",
  ]);
  expect(compared("Conversations (small sample)")).toEqual(["120", "3", "−117", ""]);
  expect(compared("Mean tokens per reply")).toEqual(["512", "120", "−392", "v2"]);
  expect(compared("Cost per Conversation (USD)")).toEqual(["$1.25", "$0.0012", "−$1.25", "v2"]);
  expect(compared("Total cost (USD)")).toEqual(["$150.00", "$0.0036", "−$150.00", ""]);
  expect(compared("Thumbs-up rate (small sample)")).toEqual(["80%", "67%", "−13 pts", "v1"]);
  expect(compared("Mean rating (small sample)")).toEqual(["4.25", "3.50", "−0.75", "v1"]);
  expect(compared("Fallback rate")).toEqual(["0%", "25%", "+25 pts", "v1"]);
  expect(compared("p95 time to first token (ms)")).toEqual(["950 ms", "320 ms", "−630 ms", "v2"]);
  expect(compared("p95 total latency (ms)")).toEqual(["2.4 s", "1.5 s", "−920 ms", "v2"]);
  // Rows that differ are highlighted; the Version a metric favours is named in words too.
  expect(rowOf("Mean tokens per reply")).toHaveClass("bg-amber-50");
  expect(queries.map((q) => q.toString())).toEqual([`a=${largeSample.version_id}&b=${smallSample.version_id}`]);
});

test("the configuration diff between the two Versions is shown alongside", async () => {
  setUp();
  renderStudio(analyticsTab);

  const changes = await screen.findByRole("region", { name: "Configuration changes" });
  expect(within(changes).getByRole("list", { name: "Changes from v1 to v2" })).toBeInTheDocument();
  expect(within(changes).getByText("Behaviour › System prompt")).toBeInTheDocument();
  expect(within(changes).getByRole("list", { name: "Behaviour › System prompt changes" })).toHaveTextContent(
    "Removed: − Answer fully.Added: + Answer in one sentence.",
  );
});

test("the comparison is exported as CSV for the chosen Versions and days", async () => {
  setUp();
  renderStudio(analyticsTab);
  await screen.findByRole("table", { name: "v1 compared with v2" });

  const base = `/api/organisations/${organisationId}/projects/${hrProject.id}/agents/${hrHelper.id}/comparison.csv`;
  const link = screen.getByRole("link", { name: "Export as CSV" });
  expect(link).toHaveAttribute("href", `${base}?a=${largeSample.version_id}&b=${smallSample.version_id}`);
  expect(link).toHaveAttribute("download");

  await userEvent.type(screen.getByLabelText("From (UTC)"), "2026-11-01");
  await userEvent.type(screen.getByLabelText("To (UTC)"), "2026-11-03");

  await screen.findByText(/2026-11-01 to 2026-11-03 \(UTC days\)/);
  expect(screen.getByRole("link", { name: "Export as CSV" })).toHaveAttribute(
    "href",
    `${base}?a=${largeSample.version_id}&b=${smallSample.version_id}&start=2026-11-01&end=2026-11-03`,
  );
});

test("the chosen date range applies to the comparison", async () => {
  setUp();
  const { queries } = fakeComparisonApi();
  renderStudio(analyticsTab);
  await screen.findByRole("table", { name: "v1 compared with v2" });

  await userEvent.type(screen.getByLabelText("From (UTC)"), "2026-11-01");
  await userEvent.type(screen.getByLabelText("To (UTC)"), "2026-11-03");

  await screen.findByText(/2026-11-01 to 2026-11-03 \(UTC days\)/);
  expect(queries.at(-1)?.get("start")).toBe("2026-11-01");
  expect(queries.at(-1)?.get("end")).toBe("2026-11-03");
});

test("the Editor picks any two Versions; the same one twice is not compared", async () => {
  const v3 = versionKpis(3, { conversations: 5, messages: 5 });
  setUp({ versions: { [hrHelper.id]: [largeSample, { ...smallSample, is_live: false }, v3] } });
  const rows = [
    {
      metric: "conversations",
      label: "Conversations",
      unit: "count" as const,
      a: 5,
      b: 120,
      difference: 115,
      changed: true,
      better: null,
      low_confidence: true,
    },
    {
      metric: "rating_mean",
      label: "Mean rating",
      unit: "rating" as const,
      a: null,
      b: 4.25,
      difference: null,
      changed: true,
      better: null,
      low_confidence: true,
    },
    {
      metric: "fallback_rate",
      label: "Fallback rate",
      unit: "rate" as const,
      a: null,
      b: null,
      difference: null,
      changed: false,
      better: null,
      low_confidence: false,
    },
    {
      metric: "messages",
      label: "Replies",
      unit: "count" as const,
      a: 5,
      b: 5,
      difference: 0,
      changed: false,
      better: null,
      low_confidence: false,
    },
  ];
  const same = {
    from: { kind: "version" as const, version: { id: v3.version_id, number: 3 } },
    to: v1ToV2Diff.from,
    changes: [],
    instructions: null,
  };
  const { queries } = fakeComparisonApi({
    comparisons: [
      versionComparison(largeSample, smallSample, v1AgainstV2Metrics, v1ToV2Diff),
      versionComparison(v3, largeSample, rows, same),
    ],
  });
  renderStudio(analyticsTab);
  // Nothing is Live: the newest against the one before it.
  await screen.findByRole("list", { name: "Key numbers for v3" });
  expect(screen.getByLabelText("First Version")).toHaveDisplayValue("v2");
  expect(screen.getByLabelText("Second Version")).toHaveDisplayValue("v3");
  expect(await screen.findByRole("alert")).toHaveTextContent("The comparison could not be loaded. Try again shortly.");

  await userEvent.selectOptions(screen.getByLabelText("First Version"), "v3");
  await userEvent.selectOptions(screen.getByLabelText("Second Version"), "v3");

  expect(await screen.findByText("Pick two different Versions to compare.")).toBeInTheDocument();
  expect(screen.queryByRole("table", { name: /compared with/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Export as CSV" })).not.toBeInTheDocument();

  await userEvent.selectOptions(screen.getByLabelText("Second Version"), "v1");

  expect(await screen.findByRole("table", { name: "v3 compared with v1" })).toBeInTheDocument();
  expect(compared("Conversations (small sample)")).toEqual(["5", "120", "+115", ""]);
  // A side with no value has no difference; nothing on either side is the same.
  expect(compared("Mean rating (small sample)")).toEqual(["—", "4.25", "—", ""]);
  expect(rowOf("Mean rating (small sample)")).toHaveClass("bg-amber-50");
  expect(compared("Fallback rate")).toEqual(["—", "—", "Same", ""]);
  expect(compared("Replies")).toEqual(["5", "5", "Same", ""]);
  expect(rowOf("Replies")).not.toHaveClass("bg-amber-50");
  expect(screen.getByText("No differences: v3 and v1 have the same settings.")).toBeInTheDocument();
  // The pair asked for each time; never the same Version twice.
  expect(queries.map((q) => [q.get("a"), q.get("b")])).toEqual([
    [smallSample.version_id, v3.version_id],
    [v3.version_id, largeSample.version_id],
  ]);
});

test("an Agent with one Version has nothing to compare yet", async () => {
  setUp({ versions: { [hrHelper.id]: [versionKpis(1, { is_live: true })] } });
  renderStudio(analyticsTab);

  expect(await screen.findByText("Publish another Version of this Agent to compare two.")).toBeInTheDocument();
  expect(screen.queryByLabelText("First Version")).not.toBeInTheDocument();
});

test("the comparison says so while it loads", async () => {
  setUp();
  renderStudio(analyticsTab);

  expect(await screen.findByText("Comparing the Versions…")).toBeInTheDocument();
  expect(await screen.findByRole("table", { name: "v1 compared with v2" })).toBeInTheDocument();
});
