import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { agentVersion, fakeAgentsApi, hrHelper, oldHelper } from "../test/agents";
import { adaSession, fakeAuthApi, type Session } from "../test/auth";
import {
  PLAYGROUND_CONVERSATION_ID,
  PLAYGROUND_REPLY_ID,
  VISITOR_CONVERSATION_ID,
  VISITOR_REPLY_ID,
  fakeConversationsApi,
  playgroundConversation,
  playgroundDetail,
  visitorConversation,
  visitorDetail,
} from "../test/conversations";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";

const organisationId = adaSession.organisations[0]?.id ?? "";
const projectPage = `/organisations/${organisationId}/projects/${hrProject.id}`;
const conversationsTab = `${projectPage}/conversations`;
const editorSession: Session = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};
const helperV1 = agentVersion(1);
const helperV2 = agentVersion(2);

function setUp(options: Parameters<typeof fakeConversationsApi>[0] = {}) {
  fakeAuthApi({ signedInAs: editorSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [hrHelper, oldHelper], versions: { [hrHelper.id]: [helperV2, helperV1] } });
  return fakeConversationsApi(options);
}

/** The list's rows as the Editor reads them, one array of cell texts per row. */
async function rows() {
  const table = await screen.findByRole("table", { name: "Conversations" });
  return within(table)
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell").map((cell) => cell.textContent));
}

const filters = () => screen.getByRole("group", { name: "Filter Conversations" });

test("the Conversations tab lists Visitor and Playground Conversations, Playground ones flagged", async () => {
  const { queries } = setUp();
  renderStudio(conversationsTab);

  expect(await screen.findByRole("heading", { level: 2, name: "Conversations" })).toBeInTheDocument();
  expect(await rows()).toEqual([
    ["2026-11-07 08:00 UTC", "HR helper", "Playground", "Draft", "2", "None", "Testing leave"],
    ["2026-11-06 10:15 UTC", "HR helper", "Visitor", "v1, v2", "4", "1 up · 1 down", "How much leave do I get?"],
  ]);
  const table = screen.getByRole("table", { name: "Conversations" });
  expect(within(table).getByText("Playground")).toHaveAccessibleDescription(
    "Tried in the Playground by an Editor; left out of analytics.",
  );
  expect(within(table).getByRole("link", { name: "Testing leave" })).toHaveAttribute(
    "href",
    `${conversationsTab}/${PLAYGROUND_CONVERSATION_ID}`,
  );
  expect(queries.map((query) => query.toString())).toEqual(["page=1&page_size=25"]);
});

test("the list is filtered by Agent, Version, dates and Playground", async () => {
  const { queries } = setUp();
  renderStudio(conversationsTab);
  await rows();
  const version = within(filters()).getByLabelText("Version");
  // Versions belong to one Agent, so one is chosen first.
  expect(version).toBeDisabled();

  await userEvent.selectOptions(within(filters()).getByLabelText("Agent"), "HR helper");
  expect(within(filters()).getByLabelText("Agent")).toHaveTextContent("Every AgentHR helperOld helper (archived)");
  await within(filters()).findByRole("option", { name: "v2" });
  await userEvent.selectOptions(version, "v1");
  await userEvent.type(within(filters()).getByLabelText("From (UTC)"), "2026-11-06");
  await userEvent.type(within(filters()).getByLabelText("To (UTC)"), "2026-11-06");
  await userEvent.selectOptions(within(filters()).getByLabelText("Show"), "Playground only");

  expect(await rows()).toEqual([["2026-11-07 08:00 UTC", "HR helper", "Playground", "Draft", "2", "None", "Testing leave"]]);
  expect(Object.fromEntries(queries.at(-1) ?? [])).toEqual({
    agent_id: hrHelper.id,
    version_id: helperV1.id,
    start: "2026-11-06T00:00:00.000Z",
    // The To day is included: the API's end is the next midnight.
    end: "2026-11-07T00:00:00.000Z",
    playground: "true",
    page: "1",
    page_size: "25",
  });

  await userEvent.selectOptions(within(filters()).getByLabelText("Show"), "Visitors only");
  expect(await rows()).toEqual([["2026-11-06 10:15 UTC", "HR helper", "Visitor", "v1, v2", "4", "1 up · 1 down", "How much leave do I get?"]]);
  expect(queries.at(-1)?.get("playground")).toBe("false");

  // Another Agent's Versions differ, so changing the Agent clears the Version.
  await userEvent.selectOptions(within(filters()).getByLabelText("Agent"), "Old helper (archived)");
  expect(version).toHaveValue("");
  expect(queries.at(-1)?.get("agent_id")).toBe(oldHelper.id);
  expect(queries.at(-1)?.has("version_id")).toBe(false);
  expect(await screen.findByText("No Conversations match these filters.")).toBeInTheDocument();
  await userEvent.selectOptions(within(filters()).getByLabelText("Agent"), "Every Agent");
  expect(version).toBeDisabled();
});

test("an Agent's Conversations open from the list already filtered to it", async () => {
  const { queries } = setUp();
  renderStudio(`${conversationsTab}?agent=${hrHelper.id}`);

  await rows();

  expect(within(filters()).getByLabelText("Agent")).toHaveValue(hrHelper.id);
  expect(queries.at(-1)?.get("agent_id")).toBe(hrHelper.id);
});

test("a Project with no Conversations says so", async () => {
  setUp({ conversations: [] });
  renderStudio(conversationsTab);

  expect(await screen.findByText(/No Conversations yet/)).toBeInTheDocument();
  expect(screen.queryByRole("table", { name: "Conversations" })).not.toBeInTheDocument();
});

test("a list that can't be loaded says so", async () => {
  setUp({ listStatus: 500 });
  renderStudio(conversationsTab);

  expect(await screen.findByRole("alert")).toHaveTextContent("The Conversations could not be loaded. Try again shortly.");
});

test("a long list comes in pages", async () => {
  const { queries } = setUp({ total: 30 });
  renderStudio(conversationsTab);
  await rows();
  expect(screen.getByText("Page 1 of 2 · 30 Conversations")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();

  await userEvent.click(screen.getByRole("button", { name: "Next page" }));

  expect(await screen.findByText("Page 2 of 2 · 30 Conversations")).toBeInTheDocument();
  expect(queries.at(-1)?.get("page")).toBe("2");
  expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Previous page" }));
  expect(await screen.findByText("Page 1 of 2 · 30 Conversations")).toBeInTheDocument();
  // A new filter starts from the first page again.
  await userEvent.click(screen.getByRole("button", { name: "Next page" }));
  await screen.findByText("Page 2 of 2 · 30 Conversations");
  await userEvent.selectOptions(within(filters()).getByLabelText("Show"), "Visitors only");
  expect(await screen.findByText("Page 1 of 2 · 30 Conversations")).toBeInTheDocument();
});

test("one Conversation is counted as one", async () => {
  setUp({ conversations: [visitorConversation] });
  renderStudio(conversationsTab);

  expect(await screen.findByText("Page 1 of 1 · 1 Conversation")).toBeInTheDocument();
});

test("an Editor opens a Visitor Conversation and reads each reply's Trace in the drawer", async () => {
  const { traceReads } = setUp();
  renderStudio(`${conversationsTab}?agent=${hrHelper.id}`);
  await userEvent.click(await screen.findByRole("link", { name: "How much leave do I get?" }));

  expect(await screen.findByRole("heading", { level: 2, name: "Conversation with HR helper" })).toBeInTheDocument();
  expect(screen.getByText("Visitor Conversation · started 2026-11-06 10:15 UTC · last active 2026-11-06 10:20 UTC")).toBeInTheDocument();
  const messages = screen.getByRole("list", { name: "Messages" });
  const items = within(messages).getAllByRole("listitem");
  expect(items.map((item) => item.getAttribute("aria-label"))).toEqual(["Visitor", "HR helper", "Visitor", "HR helper"]);
  expect(items[0]).toHaveTextContent("How much leave do I get?");
  expect(items[1]).toHaveTextContent("Twenty-five days.");
  expect(items[1]).toHaveTextContent("Agent Version v1");
  expect(items[3]).toHaveTextContent("Agent Version v2 · fallback reply");
  // Questions have no Trace.
  expect(within(items[0] as HTMLElement).queryByRole("button", { name: "Trace" })).not.toBeInTheDocument();

  await userEvent.click(within(items[1] as HTMLElement).getByRole("button", { name: "Trace" }));

  const drawer = await screen.findByRole("dialog", { name: "Trace" });
  const answeredBy = await within(drawer).findByText("Answered by");
  expect(answeredBy.nextElementSibling).toHaveTextContent("Agent Version v1");
  expect(within(drawer).getByText("Instructions").nextElementSibling).toHaveTextContent("Pinned by Agent Version v1");
  expect(within(drawer).getByRole("table", { name: "Retrieved Chunks" })).toBeInTheDocument();
  expect(traceReads).toEqual([`${VISITOR_CONVERSATION_ID}/${VISITOR_REPLY_ID}`]);
  await userEvent.click(within(drawer).getByRole("button", { name: "Close" }));
  expect(screen.queryByRole("dialog", { name: "Trace" })).not.toBeInTheDocument();

  // Back to the list, with the filters it had.
  await userEvent.click(screen.getByRole("link", { name: "All Conversations" }));
  expect(await rows()).toHaveLength(2);
  expect(within(filters()).getByLabelText("Agent")).toHaveValue(hrHelper.id);
});

test("a Playground Conversation is flagged, and its replies' Traces say the Draft answered", async () => {
  const { traceReads } = setUp();
  renderStudio(`${conversationsTab}/${PLAYGROUND_CONVERSATION_ID}`);

  expect(
    await screen.findByText(
      "Playground Conversation · tried in the Playground by an Editor; left out of analytics · started 2026-11-07 08:00 UTC · last active 2026-11-07 08:01 UTC",
    ),
  ).toBeInTheDocument();
  const items = within(screen.getByRole("list", { name: "Messages" })).getAllByRole("listitem");
  expect(items.map((item) => item.getAttribute("aria-label"))).toEqual(["Editor", "HR helper"]);
  expect(items[1]).toHaveTextContent("Draft");

  await userEvent.click(within(items[1] as HTMLElement).getByRole("button", { name: "Trace" }));

  const drawer = await screen.findByRole("dialog", { name: "Trace" });
  expect((await within(drawer).findByText("Answered by")).nextElementSibling).toHaveTextContent("Draft");
  expect(within(drawer).getByText("Instructions").nextElementSibling).toHaveTextContent("Draft");
  expect(traceReads).toEqual([`${PLAYGROUND_CONVERSATION_ID}/${PLAYGROUND_REPLY_ID}`]);
});

test("a Trace that can't be loaded says so", async () => {
  setUp({ traces: [] });
  renderStudio(`${conversationsTab}/${VISITOR_CONVERSATION_ID}`);
  const items = within(await screen.findByRole("list", { name: "Messages" })).getAllByRole("listitem");

  await userEvent.click(within(items[1] as HTMLElement).getByRole("button", { name: "Trace" }));

  const drawer = await screen.findByRole("dialog", { name: "Trace" });
  expect(await within(drawer).findByRole("alert")).toHaveTextContent("The Trace could not be loaded.");
});

test("a Conversation that doesn't exist says so", async () => {
  setUp();
  renderStudio(`${conversationsTab}/c7000000-0000-4000-8000-00000000ffff`);

  expect(await screen.findByRole("alert")).toHaveTextContent("The Conversation could not be found.");
  expect(screen.getByRole("link", { name: "All Conversations" })).toHaveAttribute("href", conversationsTab);
});

test("an Agent page links to that Agent's Conversations", async () => {
  setUp({ conversations: [playgroundConversation] });
  renderStudio(`${projectPage}/agents/${hrHelper.id}`);

  await userEvent.click(await screen.findByRole("link", { name: "Conversations with this Agent" }, { timeout: 5000 }));

  expect(await rows()).toHaveLength(1);
  expect(within(filters()).getByLabelText("Agent")).toHaveValue(hrHelper.id);
});

test("a Conversation where nothing was asked yet still opens from the list", async () => {
  setUp({ conversations: [{ ...playgroundConversation, preview: null, message_count: 0 }] });
  renderStudio(conversationsTab);

  expect(await rows()).toEqual([["2026-11-07 08:00 UTC", "HR helper", "Playground", "Draft", "0", "None", "(nothing asked yet)"]]);
  expect(screen.getByRole("link", { name: "(nothing asked yet)" })).toHaveAttribute(
    "href",
    `${conversationsTab}/${PLAYGROUND_CONVERSATION_ID}`,
  );
});

test("the list shows each Conversation's thumbs and is filtered by feedback", async () => {
  const liked = { ...visitorConversation, id: "c7000000-0000-4000-8000-000000000003", preview: "Liked it", thumbs_up: 2, thumbs_down: 0 };
  const disliked = { ...visitorConversation, id: "c7000000-0000-4000-8000-000000000004", preview: "Hated it", thumbs_up: 0, thumbs_down: 3 };
  const { queries } = setUp({ conversations: [playgroundConversation, liked, disliked] });
  renderStudio(conversationsTab);
  const feedbackOf = async () => (await rows()).map((row) => [row[6], row[5]]);
  expect(await feedbackOf()).toEqual([
    ["Testing leave", "None"],
    ["Liked it", "2 up"],
    ["Hated it", "3 down"],
  ]);
  const feedback = within(filters()).getByLabelText("Feedback");
  expect(feedback).toHaveTextContent("Any or noneThumbs upThumbs downWith feedbackWithout feedback");

  await userEvent.selectOptions(feedback, "Thumbs down");
  expect(await screen.findByRole("link", { name: "Hated it" })).toBeInTheDocument();
  expect(await feedbackOf()).toEqual([["Hated it", "3 down"]]);
  expect(queries.at(-1)?.get("feedback")).toBe("down");

  await userEvent.selectOptions(feedback, "Thumbs up");
  expect(await feedbackOf()).toEqual([["Liked it", "2 up"]]);
  await userEvent.selectOptions(feedback, "With feedback");
  expect(await feedbackOf()).toEqual([
    ["Liked it", "2 up"],
    ["Hated it", "3 down"],
  ]);
  await userEvent.selectOptions(feedback, "Without feedback");
  expect(await feedbackOf()).toEqual([["Testing leave", "None"]]);
  expect(queries.at(-1)?.get("feedback")).toBe("none");

  await userEvent.selectOptions(feedback, "Any or none");
  expect(await rows()).toHaveLength(3);
  expect(queries.at(-1)?.has("feedback")).toBe(false);
});

test("a feedback filter in the URL is kept", async () => {
  const { queries } = setUp();
  renderStudio(`${conversationsTab}?feedback=up`);
  await rows();
  expect(within(filters()).getByLabelText("Feedback")).toHaveValue("up");
  expect(queries.at(-1)?.get("feedback")).toBe("up");
});

test("an unknown feedback filter in the URL is ignored", async () => {
  const { queries } = setUp();
  renderStudio(`${conversationsTab}?feedback=sideways`);
  await rows();
  expect(within(filters()).getByLabelText("Feedback")).toHaveValue("");
  expect(queries.at(-1)?.has("feedback")).toBe(false);
});

test("an Editor reads each reply's Visitor feedback, with its comment and the Version it counts for", async () => {
  setUp();
  renderStudio(`${conversationsTab}/${VISITOR_CONVERSATION_ID}`);
  const items = within(await screen.findByRole("list", { name: "Messages" })).getAllByRole("listitem");

  const first = within(items[1] as HTMLElement).getByRole("group", { name: "Visitor feedback" });
  expect(first).toHaveTextContent("Thumbs up · for Agent Version v1 · 2026-11-06 10:16 UTC");
  const second = within(items[3] as HTMLElement).getByRole("group", { name: "Visitor feedback" });
  expect(second).toHaveTextContent("Thumbs down · for Agent Version v2 · 2026-11-06 10:21 UTC");
  expect(within(second).getByText("It should know part-time leave.").tagName).toBe("BLOCKQUOTE");
  expect(within(items[0] as HTMLElement).queryByRole("group")).not.toBeInTheDocument();
});

test("a reply without feedback, or with feedback on a Draft answer, says so plainly", async () => {
  setUp({
    details: [
      {
        ...playgroundDetail,
        messages: playgroundDetail.messages.map((message) =>
          message.role === "assistant"
            ? { ...message, feedback: { rating: "down", comment: null, agent_version_number: null, updated_at: "2026-11-07T08:05:00Z" } }
            : message,
        ),
      },
      visitorDetail,
    ],
  });
  renderStudio(`${conversationsTab}/${PLAYGROUND_CONVERSATION_ID}`);
  const items = within(await screen.findByRole("list", { name: "Messages" })).getAllByRole("listitem");
  const feedback = within(items[1] as HTMLElement).getByRole("group", { name: "Visitor feedback" });
  expect(feedback).toHaveTextContent("Thumbs down · for the Draft · 2026-11-07 08:05 UTC");
  expect(within(feedback).queryByRole("blockquote")).not.toBeInTheDocument();
});

test("a reply nobody rated shows no feedback", async () => {
  setUp({ details: [{ ...visitorDetail, messages: visitorDetail.messages.map((m) => ({ ...m, feedback: null })) }] });
  renderStudio(`${conversationsTab}/${VISITOR_CONVERSATION_ID}`);
  const items = within(await screen.findByRole("list", { name: "Messages" })).getAllByRole("listitem");
  expect(within(items[1] as HTMLElement).getByText("No feedback")).toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "Visitor feedback" })).not.toBeInTheDocument();
});
