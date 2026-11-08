import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { fakeAgentsApi, hrHelper } from "../test/agents";
import { fakeMetricsApi, largeSample, smallSample, versionKpis } from "../test/analytics";
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
