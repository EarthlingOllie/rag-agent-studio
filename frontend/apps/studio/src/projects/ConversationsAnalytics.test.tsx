import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { agentVersion, fakeAgentsApi, hrHelper, oldHelper } from "../test/agents";
import { fakeMetricsApi, fakeTimeSeriesApi, largeSample, marker, seriesPoints, smallSample } from "../test/analytics";
import { adaSession, fakeAuthApi, type Session } from "../test/auth";
import {
  PLAYGROUND_CONVERSATION_ID,
  VISITOR_CONVERSATION_ID,
  VISITOR_REPLY_ID,
  fakeConversationsApi,
  visitorDetail,
} from "../test/conversations";
import { currentSection, menuButton, openSection } from "../test/navigation";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";

// Ticket 11-10: Conversations as a list beside the transcript (also the Agent's Conversations view),
// and Analytics' KPI cards and chart in the design system.

const organisationId = adaSession.organisations[0]?.id ?? "";
const projectPage = `/organisations/${organisationId}/projects/${hrProject.id}`;
const conversations = `${projectPage}/conversations`;
const analytics = `${projectPage}/analytics`;
const agentConversations = `${projectPage}/agents/${hrHelper.id}/conversations`;
const editorSession: Session = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};
const payHelper = { ...hrHelper, id: "a9e00000-0000-4000-8000-000000000009", name: "Pay helper" };

function setUp(options: Parameters<typeof fakeConversationsApi>[0] = {}) {
  fakeAuthApi({ signedInAs: editorSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [hrHelper, oldHelper], versions: { [hrHelper.id]: [agentVersion(2), agentVersion(1)] } });
  return fakeConversationsApi(options);
}

const list = () => screen.findByRole("list", { name: "Conversations" });
const filters = () => screen.getByRole("group", { name: "Filter Conversations" });

// Conversations

test("the list stays beside the transcript, with the open Conversation marked", async () => {
  setUp();
  renderStudio(conversations);

  expect(await screen.findByRole("heading", { name: "Choose a Conversation" })).toBeInTheDocument();
  await userEvent.click(within(await list()).getByRole("link", { name: "How much leave do I get?" }));

  expect(await screen.findByRole("heading", { name: "Conversation with HR helper" })).toBeInTheDocument();
  const open = within(await list()).getByRole("link", { name: "How much leave do I get?" });
  expect(open).toHaveAttribute("aria-current", "page");
  expect(within(await list()).getByRole("link", { name: "Testing leave" })).not.toHaveAttribute("aria-current");

  await userEvent.click(within(await list()).getByRole("link", { name: "Testing leave" }));
  expect(await screen.findByText(/^Playground Conversation · /)).toBeInTheDocument();
  expect(within(await list()).getByRole("link", { name: "Testing leave" })).toHaveAttribute("aria-current", "page");
});

test("Visitors, Playground or Both is a segmented choice", async () => {
  const { queries } = setUp();
  renderStudio(conversations);
  await list();
  const show = within(filters()).getByRole("radiogroup", { name: "Show" });
  expect(within(show).getAllByRole("radio").map((radio) => radio.textContent)).toEqual(["Visitors", "Playground", "Both"]);
  expect(within(show).getByRole("radio", { name: "Both" })).toBeChecked();

  await userEvent.click(within(show).getByRole("radio", { name: "Playground" }));
  await waitFor(() => {
    expect(queries.at(-1)?.get("playground")).toBe("true");
  });
  expect(within(await list()).getAllByRole("link").map((link) => link.textContent)).toEqual(["Testing leave"]);

  await userEvent.click(within(show).getByRole("radio", { name: "Visitors" }));
  await waitFor(() => {
    expect(queries.at(-1)?.get("playground")).toBe("false");
  });
  await userEvent.click(within(show).getByRole("radio", { name: "Both" }));
  await waitFor(() => {
    expect(queries.at(-1)?.has("playground")).toBe(false);
  });
});

test("a long list pages with Pagination", async () => {
  const { queries } = setUp({ total: 60 });
  renderStudio(conversations);
  await list();
  const pages = screen.getByRole("navigation", { name: "Conversations pages" });
  expect(within(pages).getByRole("button", { name: "Page 1" })).toHaveAttribute("aria-current", "page");

  await userEvent.click(within(pages).getByRole("button", { name: "Page 3" }));

  expect(await screen.findByText("Page 3 of 3 · 60 Conversations")).toBeInTheDocument();
  expect(queries.at(-1)?.get("page")).toBe("3");
});

test("a transcript badges each answer's Version, a Guardrail block, and folds the Trace under the answer", async () => {
  const blocked = {
    ...visitorDetail,
    messages: visitorDetail.messages.map((message, index) =>
      index === 3 ? { ...message, fallback: false, model_provider: null, model_name: null, content: "I can't help with that." } : message,
    ),
  };
  const { traceReads } = setUp({ details: [blocked] });
  renderStudio(`${conversations}/${VISITOR_CONVERSATION_ID}`);

  const items = within(await screen.findByRole("list", { name: "Messages" })).getAllByRole("listitem");
  const [, first, , second] = items as [HTMLElement, HTMLElement, HTMLElement, HTMLElement];
  expect(within(first).getByLabelText("Version 1")).toBeInTheDocument();
  expect(within(first).queryByText("Blocked by guardrail")).not.toBeInTheDocument();
  expect(within(second).getByLabelText("Version 2")).toBeInTheDocument();
  expect(within(second).getByText("Blocked by guardrail")).toBeInTheDocument();
  // The question has no Trace; nothing is loaded until a Trace is opened.
  expect(within(items[0] as HTMLElement).queryByRole("group", { name: "Trace" })).not.toBeInTheDocument();
  expect(traceReads).toEqual([]);

  const trace = within(first).getByRole("group", { name: "Trace" });
  expect(trace).toHaveTextContent("120 input and 6 output tokens · 85 ms");
  await userEvent.click(within(trace).getByText("Trace"));

  expect((await within(trace).findByText("Answered by")).nextElementSibling).toHaveTextContent("Agent Version v1");
  expect(traceReads).toEqual([`${VISITOR_CONVERSATION_ID}/${VISITOR_REPLY_ID}`]);
  expect(screen.queryByRole("dialog", { name: "Trace" })).not.toBeInTheDocument();
});

test("the Agent's Conversations view is the same list, filtered to that Agent", async () => {
  const { queries } = setUp();
  renderStudio(`${projectPage}/agents/${hrHelper.id}`);

  await openSection("Agent views", "Conversations");

  expect(await currentSection("Agent views")).toBe("Conversations");
  expect(within(await list()).getAllByRole("link").map((link) => link.textContent)).toEqual(["Testing leave", "How much leave do I get?"]);
  await waitFor(() => {
    expect(queries.at(-1)?.get("agent_id")).toBe(hrHelper.id);
  });
  // The Agent is fixed: there is no Agent filter, and its Versions are offered.
  expect(within(filters()).queryByLabelText("Agent")).not.toBeInTheDocument();
  expect(within(filters()).getByLabelText("Version")).toBeEnabled();
  await within(filters()).findByRole("option", { name: "v2" });

  const open = within(await list()).getByRole("link", { name: "Testing leave" });
  expect(open).toHaveAttribute("href", `${agentConversations}/${PLAYGROUND_CONVERSATION_ID}`);
  await userEvent.click(open);

  expect(await screen.findByText(/^Playground Conversation · /)).toBeInTheDocument();
  expect(await currentSection("Agent views")).toBe("Conversations");
  expect(await menuButton("Agents")).toHaveAccessibleName("HR helper, Agents");
});

test("the Agent's Conversations view keeps its filters in the URL, without the Agent", async () => {
  const { queries } = setUp();
  renderStudio(`${agentConversations}?show=playground&agent=${oldHelper.id}`);

  expect(within(await list()).getAllByRole("link").map((link) => link.textContent)).toEqual(["Testing leave"]);
  expect(within(filters()).getByRole("radio", { name: "Playground" })).toBeChecked();
  expect(Object.fromEntries(queries.at(-1) ?? [])).toEqual({ agent_id: hrHelper.id, playground: "true", page: "1", page_size: "25" });

  await userEvent.click(within(filters()).getByRole("radio", { name: "Visitors" }));

  expect(within(await list()).getAllByRole("link").map((link) => link.textContent)).toEqual(["How much leave do I get?"]);
  expect(Object.fromEntries(queries.at(-1) ?? [])).toEqual({ agent_id: hrHelper.id, playground: "false", page: "1", page_size: "25" });
  await userEvent.click(within(await list()).getByRole("link", { name: "How much leave do I get?" }));
  expect(await screen.findByRole("heading", { level: 4, name: "Conversation with HR helper" })).toBeInTheDocument();
  expect(await screen.findByRole("region", { name: "Conversation Rating" })).toHaveTextContent("Rated 4 of 5");
});

// Analytics

function setUpAnalytics() {
  fakeAuthApi({ signedInAs: editorSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [hrHelper, payHelper] });
  return fakeMetricsApi({ versions: { [hrHelper.id]: [largeSample, smallSample], [payHelper.id]: [largeSample] } });
}

test("KPI cards with a small sample carry a Low sample badge, with the interval and n", async () => {
  setUpAnalytics();
  renderStudio(analytics);

  await screen.findByRole("list", { name: "Key numbers for v2" });
  const thumbs = screen.getByRole("listitem", { name: "Thumbs-up rate" });
  expect(within(thumbs).getByText("Low sample")).toHaveAttribute("title", "Fewer than 30 votes");
  expect(thumbs).toHaveTextContent("95% interval 21% to 94%");
  expect(thumbs).toHaveTextContent("n = 3 votes");
  expect(within(screen.getByRole("listitem", { name: "Cost per Conversation" })).queryByText("Low sample")).not.toBeInTheDocument();
});

test("Analytics takes its Agent from the URL, and another can be chosen", async () => {
  const { queries } = setUpAnalytics();
  renderStudio(`${analytics}?agent=${payHelper.id}`);

  expect(await screen.findByRole("list", { name: "Key numbers for v1" })).toBeInTheDocument();
  expect(screen.getByLabelText("Agent")).toHaveDisplayValue("Pay helper");
  expect(queries.map(({ agentId }) => agentId)).toEqual([payHelper.id]);

  await userEvent.selectOptions(screen.getByLabelText("Agent"), "HR helper");

  expect(await screen.findByRole("list", { name: "Key numbers for v2" })).toBeInTheDocument();
  expect(screen.getByLabelText("Agent")).toHaveDisplayValue("HR helper");
});

test("each Agent view offers Analytics for this Agent, opening it pre-filtered", async () => {
  setUpAnalytics();
  fakeConversationsApi();
  renderStudio(`${projectPage}/agents/${payHelper.id}/versions`);

  const link = await screen.findByRole("link", { name: "Analytics for this Agent" });
  expect(link).toHaveAttribute("href", `${analytics}?agent=${payHelper.id}`);
  await userEvent.click(link);

  expect(await screen.findByRole("list", { name: "Key numbers for v1" })).toBeInTheDocument();
  expect(screen.getByLabelText("Agent")).toHaveDisplayValue("Pay helper");
  expect(await currentSection("Project sections")).toBe("Analytics");
});

// The chart

function setUpChart(respond: Parameters<typeof fakeTimeSeriesApi>[0]) {
  setUpAnalytics();
  fakeTimeSeriesApi(respond);
}

const threeDays = {
  points: seriesPoints(["2026-11-04", "2026-11-04", 3, 3], ["2026-11-05", "2026-11-05", 5, 5], ["2026-11-06", "2026-11-06", 2, 2]),
  markers: [marker("2026-11-05", 1, 2)],
};

test("the chart has a Table view, chosen with a segmented control", async () => {
  setUpChart({ respond: () => threeDays });
  const { container } = renderStudio(analytics);
  const section = await screen.findByRole("region", { name: "Over time" });
  const view = await within(section).findByRole("radiogroup", { name: "Show as" });
  expect(within(view).getByRole("radio", { name: "Chart" })).toBeChecked();
  expect(within(section).getByRole("figure", { name: /^Conversations per day/ })).toBeInTheDocument();
  expect(container.querySelector(".recharts-area")).not.toBeNull();
  expect(within(section).queryByRole("table")).not.toBeInTheDocument();

  await userEvent.click(within(view).getByRole("radio", { name: "Table" }));

  expect(within(section).getByRole("table", { name: "Conversations, the numbers behind the chart" })).toBeInTheDocument();
  // On a narrow screen the table scrolls sideways in a box that takes keyboard focus.
  expect(within(section).getByRole("region", { name: "Conversations, the numbers behind the chart" })).toHaveAttribute("tabindex", "0");
  expect(container.querySelector(".recharts-wrapper")).toBeNull();
});

test("Live markers are labelled rules, and changed Documents draw a band with a note", async () => {
  setUpChart({ respond: () => ({ ...threeDays, document_changes: { changed: 2, deleted: 0 } }) });
  const { container } = renderStudio(analytics);
  const chart = await screen.findByRole("figure", { name: /^Conversations per day/ });

  expect(within(chart).getByText("v2")).toBeInTheDocument();
  expect(within(chart).getByText("Documents changed")).toBeInTheDocument();
  expect(container.querySelectorAll(".recharts-yAxis")).toHaveLength(1);
  expect(screen.getByRole("note")).toHaveTextContent(/^Documents changed during this period: 2 added/);
});

test("hovering the chart shows a crosshair readout of the period, its value and n", async () => {
  const noFirstDay = { ...threeDays, points: threeDays.points.map((point, index) => (index === 0 ? { ...point, value: null } : point)) };
  setUpChart({ respond: () => noFirstDay });
  const { container } = renderStudio(analytics);
  await screen.findByRole("figure", { name: /^Conversations per day/ });
  const surface = container.querySelector(".recharts-wrapper") as HTMLElement;

  /** Moves the pointer to `x` on the chart until the readout says `expected`. */
  const hover = (x: number, expected: string) =>
    waitFor(() => {
      fireEvent.mouseMove(surface, { clientX: x, clientY: 120 });
      expect(screen.getByRole("status", { name: "Chart readout" })).toHaveTextContent(expected);
    });

  await hover(400, "2026-11-05Conversations 5n = 5 Conversations");
  expect(container.querySelector(".recharts-active-dot")).not.toBeNull();
  // A day with no data says so.
  await hover(100, "2026-11-04Conversations No datan = 3 Conversations");
  fireEvent.mouseLeave(surface);
  await waitFor(() => {
    expect(screen.queryByRole("status", { name: "Chart readout" })).not.toBeInTheDocument();
  });
});
