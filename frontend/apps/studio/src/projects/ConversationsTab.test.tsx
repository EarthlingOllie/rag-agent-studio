import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { agentVersion, fakeAgentsApi, hrHelper, oldHelper } from "../test/agents";
import { adaSession, fakeAuthApi, type Session } from "../test/auth";
import {
  DELETED_AT,
  PLAYGROUND_CONVERSATION_ID,
  PLAYGROUND_REPLY_ID,
  VISITOR_CONVERSATION_ID,
  VISITOR_REPLY_ID,
  fakeConversationsApi,
  playgroundConversation,
  playgroundDetail,
  visitorConversation,
  visitorDetail,
  visitorTrace,
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

function setUp(options: Parameters<typeof fakeConversationsApi>[0] = {}, session: Session = editorSession) {
  fakeAuthApi({ signedInAs: session });
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
    ["2026-11-07 08:00 UTC", "HR helper", "Playground", "Draft", "2", "None", "Not rated", "None", "Testing leave"],
    ["2026-11-06 10:15 UTC", "HR helper", "Visitor", "v1, v2", "4", "1 up · 1 down", "4 of 5", "2 events", "How much leave do I get?"],
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

  expect(await rows()).toEqual([["2026-11-07 08:00 UTC", "HR helper", "Playground", "Draft", "2", "None", "Not rated", "None", "Testing leave"]]);
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
  expect(await rows()).toEqual([["2026-11-06 10:15 UTC", "HR helper", "Visitor", "v1, v2", "4", "1 up · 1 down", "4 of 5", "2 events", "How much leave do I get?"]]);
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

  expect(await rows()).toEqual([["2026-11-07 08:00 UTC", "HR helper", "Playground", "Draft", "0", "None", "Not rated", "None", "(nothing asked yet)"]]);
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
  const feedbackOf = async () => (await rows()).map((row) => [row[8], row[5]]);
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

test("the list shows each Conversation's rating and is filtered by it", async () => {
  const loved = { ...visitorConversation, id: "c7000000-0000-4000-8000-000000000005", preview: "Loved it", rating: 5 };
  const hated = { ...visitorConversation, id: "c7000000-0000-4000-8000-000000000006", preview: "Hated it", rating: 1 };
  const { queries } = setUp({ conversations: [playgroundConversation, loved, hated] });
  renderStudio(conversationsTab);
  const ratingOf = async () => (await rows()).map((row) => [row[8], row[6]]);
  expect(await ratingOf()).toEqual([
    ["Testing leave", "Not rated"],
    ["Loved it", "5 of 5"],
    ["Hated it", "1 of 5"],
  ]);
  const rating = within(filters()).getByLabelText("Rating");
  expect(rating).toHaveTextContent("Rated or not5 of 54 of 53 of 52 of 51 of 5RatedNot rated");

  await userEvent.selectOptions(rating, "1 of 5");
  expect(await ratingOf()).toEqual([["Hated it", "1 of 5"]]);
  expect(queries.at(-1)?.get("rating")).toBe("1");
  await userEvent.selectOptions(rating, "3 of 5");
  expect(await screen.findByText("No Conversations match these filters.")).toBeInTheDocument();
  await userEvent.selectOptions(rating, "Rated");
  expect(await ratingOf()).toEqual([
    ["Loved it", "5 of 5"],
    ["Hated it", "1 of 5"],
  ]);
  await userEvent.selectOptions(rating, "Not rated");
  expect(await ratingOf()).toEqual([["Testing leave", "Not rated"]]);
  expect(queries.at(-1)?.get("rating")).toBe("none");

  await userEvent.selectOptions(rating, "Rated or not");
  expect(await rows()).toHaveLength(3);
  expect(queries.at(-1)?.has("rating")).toBe(false);
});

test.each([
  ["?rating=4", "4"],
  ["?rating=any", "any"],
  ["?rating=9", ""],
  ['?rating="2"', "2"],
  ["?rating=great", ""],
])("a rating filter in the URL (%s) is kept when it is one", async (search, kept) => {
  const { queries } = setUp();
  renderStudio(`${conversationsTab}${search}`);
  await screen.findByRole("group", { name: "Filter Conversations" });
  expect(within(filters()).getByLabelText("Rating")).toHaveValue(kept);
  expect(queries.at(-1)?.get("rating") ?? "").toBe(kept);
});

test("an Editor reads the Visitor's Conversation Rating, the Version it counts for and its change log", async () => {
  setUp();
  renderStudio(`${conversationsTab}/${VISITOR_CONVERSATION_ID}`);

  const rating = await screen.findByRole("region", { name: "Conversation Rating" });

  expect(rating).toHaveTextContent("Rated 4 of 5 · for Agent Version v2 · 2026-11-06 10:22 UTC");
  expect(rating).toHaveTextContent("The Visitor dismissed the rating prompt · 2026-11-06 10:17 UTC");
  const changes = within(within(rating).getByRole("list", { name: "Rating changes" })).getAllByRole("listitem");
  expect(changes.map((change) => change.textContent)).toEqual([
    "Rated 2 · for Agent Version v1 · 2026-11-06 10:16 UTC",
    "Changed from 2 to 4 · for Agent Version v2 · 2026-11-06 10:22 UTC",
  ]);
});

test("a Conversation the Visitor didn't rate says so", async () => {
  setUp({ details: [{ ...visitorDetail, rating: null }] });
  renderStudio(`${conversationsTab}/${VISITOR_CONVERSATION_ID}`);

  const rating = await screen.findByRole("region", { name: "Conversation Rating" });
  expect(rating).toHaveTextContent(/^Conversation RatingNot rated$/);
});

test("a dismissal without a rating is shown, and a Playground Conversation has no rating", async () => {
  const dismissedOnly = {
    ...visitorDetail,
    rating: { score: null, agent_version_number: null, rated_at: null, prompt_dismissed_at: "2026-11-06T10:17:00Z", changes: [] },
  };
  setUp({ details: [dismissedOnly, playgroundDetail] });
  const { unmount } = renderStudio(`${conversationsTab}/${VISITOR_CONVERSATION_ID}`);
  const rating = await screen.findByRole("region", { name: "Conversation Rating" });
  expect(rating).toHaveTextContent("Not rated");
  expect(rating).toHaveTextContent("The Visitor dismissed the rating prompt · 2026-11-06 10:17 UTC");
  expect(within(rating).queryByRole("list")).not.toBeInTheDocument();
  unmount();

  renderStudio(`${conversationsTab}/${PLAYGROUND_CONVERSATION_ID}`);
  await screen.findByRole("list", { name: "Messages" });
  expect(screen.queryByRole("region", { name: "Conversation Rating" })).not.toBeInTheDocument();
});

test("a rating attributed to a Draft answer says so", async () => {
  const draftRated = {
    ...visitorDetail,
    rating: {
      score: 3,
      agent_version_number: null,
      rated_at: "2026-11-06T10:22:00Z",
      prompt_dismissed_at: null,
      changes: [{ score: 3, previous_score: null, agent_version_number: null, changed_at: "2026-11-06T10:22:00Z" }],
    },
  };
  setUp({ details: [draftRated] });
  renderStudio(`${conversationsTab}/${VISITOR_CONVERSATION_ID}`);
  const rating = await screen.findByRole("region", { name: "Conversation Rating" });
  expect(rating).toHaveTextContent("Rated 3 of 5 · for the Draft · 2026-11-06 10:22 UTC");
  expect(rating).not.toHaveTextContent("dismissed");
});

// Retention and deletion

test("an Owner deletes a Conversation on request after confirming, and its text is shown as purged", async () => {
  const { deletions } = setUp({}, adaSession);
  renderStudio(`${conversationsTab}/${VISITOR_CONVERSATION_ID}`);
  await screen.findByRole("list", { name: "Messages" });

  await userEvent.click(screen.getByRole("button", { name: "Delete Conversation" }));
  const confirm = screen.getByRole("group", { name: "Delete Conversation" });
  expect(confirm).toHaveTextContent(
    "Its Messages' text and feedback comments will be purged now and can't be recovered. Its numbers stay in the metrics.",
  );
  await userEvent.click(within(confirm).getByRole("button", { name: "Cancel" }));
  expect(deletions).toEqual([]);
  await userEvent.click(screen.getByRole("button", { name: "Delete Conversation" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, delete it" }));

  expect(
    await screen.findByText("Deleted on request 2026-11-08 12:00 UTC. Its numbers stay in the metrics."),
  ).toBeInTheDocument();
  expect(deletions).toEqual([VISITOR_CONVERSATION_ID]);
  expect(screen.queryByRole("button", { name: "Delete Conversation" })).not.toBeInTheDocument();
  const items = within(screen.getByRole("list", { name: "Messages" })).getAllByRole("listitem");
  for (const item of items) {
    expect(item).toHaveTextContent("Text purged 2026-11-08 12:00 UTC: the Conversation was deleted on request.");
  }
  expect(screen.queryByText("It should know part-time leave.")).not.toBeInTheDocument();
  // The feedback and rating stay.
  expect(within(items[3] as HTMLElement).getByRole("group", { name: "Visitor feedback" })).toHaveTextContent("Thumbs down");
  expect(screen.getByRole("region", { name: "Conversation Rating" })).toHaveTextContent("Rated 4 of 5");

  await userEvent.click(screen.getByRole("link", { name: "All Conversations" }));
  expect((await rows()).map((row) => row[8])).toEqual(["Testing leave", "(deleted on request)"]);
});

test("Editors can't delete a Conversation", async () => {
  setUp();
  renderStudio(`${conversationsTab}/${VISITOR_CONVERSATION_ID}`);
  await screen.findByRole("list", { name: "Messages" });
  expect(screen.queryByRole("button", { name: "Delete Conversation" })).not.toBeInTheDocument();
});

test("a failed deletion says so", async () => {
  setUp({ deleteStatus: 500 }, adaSession);
  renderStudio(`${conversationsTab}/${VISITOR_CONVERSATION_ID}`);
  await userEvent.click(await screen.findByRole("button", { name: "Delete Conversation" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, delete it" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("The Conversation could not be deleted. Try again shortly.");
  expect(screen.getByRole("button", { name: "Delete Conversation" })).toBeInTheDocument();
});

test("Messages purged by the Retention Window say so, also in a Conversation deleted later", async () => {
  const purgedAt = "2026-11-07T00:35:00Z";
  const purged = visitorDetail.messages.map((m, index) =>
    index < 2 ? { ...m, content: "", purged_at: purgedAt } : { ...m, content: "", purged_at: DELETED_AT },
  );
  setUp({
    conversations: [{ ...visitorConversation, preview: null }, { ...playgroundConversation, preview: null, message_count: 0 }],
    details: [{ ...visitorDetail, messages: purged, deleted_at: DELETED_AT }],
  });
  renderStudio(conversationsTab);
  expect((await rows()).map((row) => row[8])).toEqual(["(text purged)", "(nothing asked yet)"]);

  await userEvent.click(screen.getByRole("link", { name: "(text purged)" }));

  const items = within(await screen.findByRole("list", { name: "Messages" })).getAllByRole("listitem");
  expect(items[0]).toHaveTextContent("Text purged 2026-11-07 00:35 UTC: it was older than the Retention Window.");
  expect(items[1]).toHaveTextContent("Text purged 2026-11-07 00:35 UTC: it was older than the Retention Window.");
  expect(items[2]).toHaveTextContent("Text purged 2026-11-08 12:00 UTC: the Conversation was deleted on request.");
});

test("a Trace names a deleted Document's Chunk as a tombstone", async () => {
  const legacy = { ...visitorTrace.chunks[3], document_name: null } as (typeof visitorTrace.chunks)[number];
  setUp({ traces: [{ ...visitorTrace, chunks: [...visitorTrace.chunks, legacy] }] });
  renderStudio(`${conversationsTab}/${VISITOR_CONVERSATION_ID}`);
  const items = within(await screen.findByRole("list", { name: "Messages" })).getAllByRole("listitem");
  await userEvent.click(within(items[1] as HTMLElement).getByRole("button", { name: "Trace" }));

  const table = await screen.findByRole("table", { name: "Retrieved Chunks" });
  const documents = within(table)
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell")[1]?.textContent);
  expect(documents).toEqual([
    "leave-policy.md",
    "expenses.md",
    "parking.md",
    "Chunk from deleted Document old-handbook.md",
    "price-list.md",
    // Deleted before Traces kept Document names.
    "Chunk from a deleted Document",
  ]);
});

test("the list shows each Conversation's Guardrail events and is filtered by Guardrail outcome", async () => {
  const attacked = { ...visitorConversation, id: "c7000000-0000-4000-8000-000000000007", preview: "Ignore your instructions", guardrail_events: 1 };
  const { queries } = setUp({ conversations: [playgroundConversation, attacked] });
  renderStudio(conversationsTab);
  const guardrailOf = async () => (await rows()).map((row) => [row[8], row[7]]);
  expect(await guardrailOf()).toEqual([
    ["Testing leave", "None"],
    ["Ignore your instructions", "1 event"],
  ]);
  const guardrail = within(filters()).getByLabelText("Guardrail");
  expect(within(guardrail).getAllByRole("option").map((option) => option.textContent)).toEqual([
    "Any or none",
    "Blocked",
    "Flagged",
    "Logged",
    "Replaced (Canary token)",
    "Allowed unchecked",
    "With a Guardrail event",
    "Without",
  ]);

  await userEvent.selectOptions(guardrail, "Blocked");
  expect(await guardrailOf()).toEqual([["Ignore your instructions", "1 event"]]);
  expect(queries.at(-1)?.get("guardrail")).toBe("blocked");
  await userEvent.selectOptions(guardrail, "Without");
  expect(await guardrailOf()).toEqual([["Testing leave", "None"]]);
  expect(queries.at(-1)?.get("guardrail")).toBe("none");
  for (const [option, value] of [
    ["Flagged", "flagged"],
    ["Logged", "logged"],
    ["Replaced (Canary token)", "replaced"],
    ["Allowed unchecked", "allowed"],
    ["With a Guardrail event", "any"],
  ] as const) {
    await userEvent.selectOptions(guardrail, option);
    await screen.findByRole("table", { name: "Conversations" });
    expect(queries.at(-1)?.get("guardrail")).toBe(value);
  }

  await userEvent.selectOptions(guardrail, "Any or none");
  expect(await rows()).toHaveLength(2);
  expect(queries.at(-1)?.has("guardrail")).toBe(false);
});

test.each([
  ["?guardrail=blocked", "blocked"],
  ["?guardrail=none", "none"],
  ["?guardrail=evil", ""],
])("a Guardrail filter in the URL (%s) is kept when it is one", async (search, kept) => {
  const { queries } = setUp();
  renderStudio(`${conversationsTab}${search}`);
  await screen.findByRole("group", { name: "Filter Conversations" });
  expect(within(filters()).getByLabelText("Guardrail")).toHaveValue(kept);
  expect(queries.at(-1)?.get("guardrail") ?? "").toBe(kept);
});
