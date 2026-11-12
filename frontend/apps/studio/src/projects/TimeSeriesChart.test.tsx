import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { fakeAgentsApi, hrHelper } from "../test/agents";
import { fakeMetricsApi, fakeTimeSeriesApi, largeSample, marker, seriesPoints, smallSample } from "../test/analytics";
import { adaSession, fakeAuthApi, type Session } from "../test/auth";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";

const organisationId = adaSession.organisations[0]?.id ?? "";
const analyticsTab = `/organisations/${organisationId}/projects/${hrProject.id}/analytics`;
const editorSession: Session = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};

function setUp(options: Parameters<typeof fakeTimeSeriesApi>[0] = {}, session: Session = editorSession) {
  fakeAuthApi({ signedInAs: session });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [hrHelper] });
  fakeMetricsApi({ versions: { [hrHelper.id]: [largeSample, smallSample] } });
  return fakeTimeSeriesApi(options);
}

/** Shows the series as a table (the chart is shown first). */
async function showTable(section: HTMLElement) {
  await userEvent.click(await within(section).findByRole("radio", { name: "Table" }));
}

/** The numbers behind the chart, row by row, as the Editor reads them. */
function rows(): string[][] {
  const table = screen.getByRole("table", { name: /the numbers behind the chart/ });
  return within(table)
    .getAllByRole("row")
    .map((row) => [...row.querySelectorAll("th, td")].map((cell) => cell.textContent));
}

const threeDays = {
  points: seriesPoints(["2026-11-04", "2026-11-04", null, 0], ["2026-11-05", "2026-11-05", 1, 1], ["2026-11-06", "2026-11-06", 0.25, 4]),
  markers: [marker("2026-11-05", null, 1), marker("2026-11-06", 1, 2), marker("2026-11-06", 2, 1, "revert")],
};

test("the time series shows the metric per day with markers where the Live Version changed", async () => {
  const { queries } = setUp({ respond: () => threeDays });
  const { container } = renderStudio(analyticsTab);

  const section = await screen.findByRole("region", { name: "Over time" });
  expect(await within(section).findByRole("figure")).toBeInTheDocument();
  expect(within(section).getByLabelText("Metric")).toHaveDisplayValue("Conversations");
  expect(within(section).getByLabelText("Granularity")).toHaveDisplayValue("Day");
  expect(screen.getByText(/Conversations per day, from 2026-11-03 until 2026-11-06 \(UTC\)/)).toBeInTheDocument();
  // Every Live History entry is listed, and marked on the chart at its day's point.
  expect(within(screen.getByRole("list", { name: "Live Version changes" })).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
    "2026-11-05: v1 published",
    "2026-11-06: v2 published (from v1)",
    "2026-11-06: v1 reverted to (from v2)",
  ]);
  const lines = container.querySelectorAll(".recharts-reference-line");
  expect([...lines].map((line) => line.textContent)).toEqual(["v1", "v2, v1"]);
  expect(container.querySelector(".recharts-area")).not.toBeNull();
  // No Documents changed: no confounder note, and no band.
  expect(screen.queryByRole("note")).not.toBeInTheDocument();
  expect(container.querySelector(".recharts-reference-area")).toBeNull();

  await showTable(section);

  expect(rows()).toEqual([
    ["Period", "Conversations", "n (Conversations)"],
    ["2026-11-04", "No data", "0"],
    ["2026-11-05", "1", "1"],
    ["2026-11-06", "0", "4"],
  ]);
  expect(queries.map(({ agentId, query }) => [agentId, query.toString()])).toEqual([[hrHelper.id, "metric=conversations&granularity=day"]]);
});

test("an Editor isn't offered the cost series, which is for Owners only", async () => {
  setUp({ respond: () => threeDays });
  renderStudio(analyticsTab);

  const section = await screen.findByRole("region", { name: "Over time" });
  const options = within(within(section).getByLabelText("Metric")).getAllByRole("option");
  expect(options.map((o) => o.textContent)).toEqual([
    "Conversations",
    "Replies",
    "Mean tokens per reply",
    "Thumbs-up rate",
    "Mean rating",
    "Fallback rate",
    "p95 latency",
  ]);
});

test("each metric reads in its own units, with what its sample size counts (an Owner sees the cost too)", async () => {
  const values: Record<string, [number, string, string]> = {
    conversations: [12, "12", "n (Conversations)"],
    replies: [30, "30", "n (replies)"],
    cost_usd: [0.0042, "$0.0042", "n (Conversations)"],
    mean_tokens: [120.4, "120", "n (replies that asked a model)"],
    thumbs_up_rate: [2 / 3, "67%", "n (votes)"],
    mean_rating: [3.5, "3.5 of 5", "n (ratings)"],
    fallback_rate: [0.25, "25%", "n (replies)"],
    p95_latency_ms: [1480, "1.5 s", "n (replies)"],
  };
  setUp(
    {
      respond: (query) => ({
        points: seriesPoints(["2026-11-05", "2026-11-05", values[query.get("metric") ?? ""]?.[0] ?? null, 3], ["2026-11-06", "2026-11-06", 320, 3]),
      }),
    },
    adaSession,
  );
  renderStudio(analyticsTab);
  const section = await screen.findByRole("region", { name: "Over time" });
  await showTable(section);

  const options = within(within(section).getByLabelText("Metric")).getAllByRole("option");
  expect(options.map((o) => o.textContent)).toEqual([
    "Conversations",
    "Replies",
    "Cost",
    "Mean tokens per reply",
    "Thumbs-up rate",
    "Mean rating",
    "Fallback rate",
    "p95 latency",
  ]);
  const read: string[][] = [];
  for (const option of options) {
    await userEvent.selectOptions(within(section).getByLabelText("Metric"), option.textContent);
    const name = option.textContent;
    await screen.findByRole("table", { name: `${name}, the numbers behind the chart` });
    const [header, first] = rows();
    read.push([header?.[2] ?? "", first?.[1] ?? ""]);
  }
  expect(read).toEqual(Object.values(values).map(([, shown, sample]) => [sample, shown]));
  // Under a second, latency reads in milliseconds.
  expect(rows()[2]).toEqual(["2026-11-06", "320 ms", "3"]);
});

test("the Editor chooses the granularity, and the tab's dates set the range", async () => {
  const { queries } = setUp({
    respond: (query) =>
      query.get("granularity") === "week"
        ? {
            points: seriesPoints(["2026-11-01", "2026-11-01", 2, 2], ["2026-11-02", "2026-11-08", 5, 5]),
            markers: [marker("2026-11-04", 1, 2, "bulk_publish", "2026-11-02"), marker("2026-11-05", 2, 1, "bulk_revert", "2026-11-02")],
          }
        : {},
  });
  const { container } = renderStudio(analyticsTab);
  const section = await screen.findByRole("region", { name: "Over time" });
  await within(section).findByRole("figure");

  await userEvent.type(screen.getByLabelText("From (UTC)"), "2026-11-01");
  await userEvent.type(screen.getByLabelText("To (UTC)"), "2026-11-08");
  await userEvent.selectOptions(within(section).getByLabelText("Granularity"), "Week");

  expect(await screen.findByText(/Conversations per week, from 2026-11-01 until 2026-11-08/)).toBeInTheDocument();
  expect(within(section).getByLabelText("Granularity")).toHaveDisplayValue("Week");
  expect([...container.querySelectorAll(".recharts-reference-line")].map((line) => line.textContent)).toEqual(["v2, v1"]);
  await showTable(section);
  expect(rows().slice(1)).toEqual([
    ["2026-11-01", "2", "2"],
    ["2026-11-02 to 2026-11-08", "5", "5"],
  ]);
  expect(within(screen.getByRole("list", { name: "Live Version changes" })).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
    "2026-11-04: v2 bulk published (from v1)",
    "2026-11-05: v1 bulk reverted to (from v2)",
  ]);
  expect(queries.at(-1)?.query.toString()).toBe("metric=conversations&granularity=week&start=2026-11-01&end=2026-11-08");
  expect(within(within(section).getByLabelText("Granularity")).getAllByRole("option").map((o) => o.textContent)).toEqual([
    "Day",
    "Week",
    "Month",
  ]);
});

test("a period with no Live Version change says so", async () => {
  setUp();
  renderStudio(analyticsTab);
  const section = await screen.findByRole("region", { name: "Over time" });

  expect(await within(section).findByText("None in this period.")).toBeInTheDocument();
  expect(screen.queryByRole("list", { name: "Live Version changes" })).not.toBeInTheDocument();
});

test("an action the Studio doesn't know yet is shown as the API names it", async () => {
  setUp({ respond: () => ({ markers: [marker("2026-11-05", 1, 2, "scheduled_publish")] }) });
  renderStudio(analyticsTab);

  const changes = await screen.findByRole("list", { name: "Live Version changes" });
  expect(within(changes).getByRole("listitem")).toHaveTextContent(/^2026-11-05: v2 scheduled_publish \(from v1\)$/);
});

test.each([
  [{ changed: 2, deleted: 1 }, "2 added, replaced or processed again, 1 deleted"],
  [{ changed: 1, deleted: 0 }, "1 added, replaced or processed again"],
  [{ changed: 0, deleted: 3 }, "3 deleted"],
])("Documents that changed during the period bring a confounder note (%o)", async (changes, counted) => {
  setUp({ respond: () => ({ document_changes: changes }) });
  renderStudio(analyticsTab);

  expect(await screen.findByRole("note")).toHaveTextContent(
    `Documents changed during this period: ${counted}. The Knowledge Base isn't versioned, so these changes may confound the comparison: a difference across a marker may come from the Documents rather than the Version.`,
  );
});

test("a time series that fails to load says so, and a refused range is explained", async () => {
  setUp({ status: 500 });
  renderStudio(analyticsTab);
  const section = await screen.findByRole("region", { name: "Over time" });

  expect(await within(section).findByRole("alert")).toHaveTextContent("The time series could not be loaded. Try again shortly.");
});

test("a range the API refuses is explained in the time series too", async () => {
  setUp({ status: 422 });
  renderStudio(analyticsTab);
  const section = await screen.findByRole("region", { name: "Over time" });

  expect(within(section).getByRole("status", { name: "Loading the time series" })).toBeInTheDocument();
  expect(await within(section).findByRole("alert")).toHaveTextContent(
    "Check the dates: From can't be after To, and the range can be at most 366 days.",
  );
});
