import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { agentVersion, fakeAgentsApi, hrHelper, oldHelper, streamedAnswer } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import { breadcrumb, currentSection, menuButton, openSection, sectionNames } from "../test/navigation";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const agents = `/organisations/${organisationId}/projects/${hrProject.id}/agents`;
const agentPage = (agentId: string, view = "") => `${agents}/${agentId}${view}`;

const payHelper = { ...hrHelper, id: "a9e00000-0000-4000-8000-000000000009", name: "Pay helper" };
const v1 = agentVersion(1);
const v2 = agentVersion(2);
/** Live on v2, with a Draft that has changed since. */
const liveHelper = { ...hrHelper, live_version: { id: v2.id, number: 2 }, has_unpublished_changes: true };

function setUp(options: Parameters<typeof fakeAgentsApi>[0] = {}) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  return fakeAgentsApi({ agents: [hrHelper, payHelper, oldHelper], ...options });
}

const banner = () => screen.getByRole("banner");
const bannerLoaded = () => screen.findByRole("banner", {}, { timeout: 5000 });

/** Opens a ⋯ menu by its button's name and chooses an item. */
async function choose(menu: string, item: string) {
  await userEvent.click(await screen.findByRole("button", { name: menu }, { timeout: 5000 }));
  await userEvent.click(screen.getByRole("menuitem", { name: item }));
}

// The Agent's header and its view tabs

const tabRow = () => screen.findByRole("navigation", { name: "Agent views" }, { timeout: 5000 });

test("the Agent's views are a tab row under its header, the current one marked", async () => {
  setUp();
  renderStudio(agentPage(hrHelper.id));

  const tabs = await tabRow();
  expect(
    within(tabs)
      .getAllByRole("link")
      .map((tab) => [tab.textContent, tab.getAttribute("href"), tab.getAttribute("aria-current")]),
  ).toEqual([
    ["Playground", agentPage(hrHelper.id), "page"],
    ["Versions", agentPage(hrHelper.id, "/versions"), null],
    ["Embed & limits", agentPage(hrHelper.id, "/embed"), null],
    ["Conversations", agentPage(hrHelper.id, "/conversations"), null],
  ]);
  // The tab row follows the Agent's header.
  const header = screen.getByRole("region", { name: "HR helper" });
  expect(header.compareDocumentPosition(tabs) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

  await userEvent.click(within(tabs).getByRole("link", { name: "Versions" }));
  expect(await screen.findByRole("heading", { name: "Live History" })).toBeInTheDocument();
  expect(within(tabs).getByRole("link", { name: "Versions" })).toHaveAttribute("aria-current", "page");
  expect(within(tabs).getByRole("link", { name: "Playground" })).not.toHaveAttribute("aria-current");
  expect(screen.queryByRole("region", { name: "Playground" })).not.toBeInTheDocument();
});

test("the navigation helpers read the Agent's views from the tab row", async () => {
  setUp();
  renderStudio(agentPage(hrHelper.id));

  expect(await sectionNames("Agent views")).toEqual(["Playground", "Versions", "Embed & limits", "Conversations"]);
  expect(await currentSection("Agent views")).toBe("Playground");

  await openSection("Agent views", "Versions");
  expect(await screen.findByRole("heading", { name: "Live History" })).toBeInTheDocument();
  expect(await currentSection("Agent views")).toBe("Versions");

  await openSection("Agent views", "Embed & limits");
  expect(await screen.findByRole("heading", { name: "Allowed Origins" })).toBeInTheDocument();
  expect(await currentSection("Agent views")).toBe("Embed & limits");
});

test("the Agent's name is the page's one h1, without the Project's header", async () => {
  setUp();
  renderStudio(agentPage(hrHelper.id));

  expect(await screen.findByRole("heading", { level: 1, name: "HR helper" }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  expect(screen.queryByRole("heading", { name: hrProject.name })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Edit details" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "More Project actions" })).not.toBeInTheDocument();

  await openSection("Agent views", "Versions");
  expect(await screen.findByRole("heading", { name: "Live History" })).toBeInTheDocument();
  expect(screen.getAllByRole("heading", { level: 1 }).map((heading) => heading.textContent)).toEqual(["HR helper"]);
});

test("the ▾ on the Agent's name lists the Project's open Agents and switches between them", async () => {
  setUp();
  renderStudio(agentPage(hrHelper.id));

  const header = await screen.findByRole("region", { name: "HR helper" }, { timeout: 5000 });
  const switcher = within(header).getByRole("button", { name: "HR helper, Agents" });
  expect(switcher).toHaveAttribute("aria-haspopup", "menu");
  expect(await menuButton("Agents")).toBe(switcher);
  expect(await currentSection("Agents")).toBe("HR helper");
  expect(await sectionNames("Agents")).toEqual(["HR helper", "Pay helper"]);
  // On an Agent the sidebar keeps Agents current.
  expect(await currentSection("Project sections")).toBe("Agents");

  await openSection("Agents", "Pay helper");

  expect(await screen.findByRole("heading", { level: 1, name: "Pay helper" })).toBeInTheDocument();
  expect(await menuButton("Agents")).toHaveAccessibleName("Pay helper, Agents");
  expect(await currentSection("Agent views")).toBe("Playground");
});

test("the breadcrumb is the Project, Agents and the Agent, which stays the current crumb on each of its views", async () => {
  setUp();
  renderStudio(agentPage(hrHelper.id, "/embed"));
  await screen.findByRole("heading", { level: 1, name: "HR helper" }, { timeout: 5000 });

  expect(await breadcrumb()).toEqual({ crumbs: ["HR handbook", "Agents", "HR helper"], current: "HR helper" });
  const crumbs = within(screen.getByRole("navigation", { name: "Breadcrumb" }));
  expect(crumbs.getByRole("link", { name: "HR helper" })).toHaveAttribute("href", agentPage(hrHelper.id));
  expect(crumbs.getByRole("link", { name: "Agents" })).toHaveAttribute("href", agents);
  // The views are the tab row's; the breadcrumb offers no menu of them.
  expect(crumbs.queryAllByRole("button")).toEqual([]);

  await openSection("Agent views", "Versions");
  expect(await currentSection("Agent views")).toBe("Versions");
  expect(await breadcrumb()).toEqual({ crumbs: ["HR handbook", "Agents", "HR helper"], current: "HR helper" });

  await userEvent.click(crumbs.getByRole("link", { name: "Agents" }));
  expect(await screen.findByRole("table", { name: "Agents" }, { timeout: 5000 })).toBeInTheDocument();
  expect(await breadcrumb()).toEqual({ crumbs: ["HR handbook", "Agents"], current: "Agents" });
});

test("until the Agent has loaded, or when it can't be found, the breadcrumb ends at Agents", async () => {
  setUp();
  renderStudio(agentPage("a0000000-0000-4000-8000-00000000dead"));

  expect(await screen.findByRole("heading", { name: "Agent not found" }, { timeout: 5000 })).toBeInTheDocument();
  expect(await breadcrumb()).toEqual({ crumbs: ["HR handbook", "Agents"], current: "Agents" });
});

test("when the Agents can't be listed, the ▾ still names the Agent", async () => {
  setUp();
  server.use(http.get("*/api/organisations/:organisationId/projects/:projectId/agents", () => HttpResponse.json({}, { status: 500 })));
  renderStudio(agentPage(hrHelper.id));

  expect(await menuButton("Agents")).toHaveAccessibleName("HR helper, Agents");
  expect(await currentSection("Agent views")).toBe("Playground");
});

test("an Agent that can't be found has no tab row and no Agent switcher", async () => {
  setUp();
  renderStudio(agentPage("a9e00000-0000-4000-8000-0000000000ff"));

  expect(await screen.findByRole("heading", { name: "Agent not found" }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.queryByRole("navigation", { name: "Agent views" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /, Agents$/ })).not.toBeInTheDocument();
});

// The top bar and the header

test("Saved state, History and Publish sit in the top bar", async () => {
  const { requests } = setUp({ agents: [liveHelper], versions: { [liveHelper.id]: [v2, v1] } });
  renderStudio(agentPage(liveHelper.id));

  const status = await within(await bannerLoaded()).findByRole("status", { name: "Draft status" }, { timeout: 5000 });
  expect(status).toHaveTextContent("All changes saved");
  expect(within(banner()).getByRole("link", { name: "History" })).toHaveAttribute("href", agentPage(liveHelper.id, "/versions"));

  await userEvent.click(within(banner()).getByRole("button", { name: "Publish" }));
  const dialog = await screen.findByRole("dialog", { name: "Publish HR helper" });
  await userEvent.type(within(dialog).getByLabelText("Note"), "Shorter answers");
  await userEvent.click(within(dialog).getByRole("button", { name: "Publish" }));

  expect(await within(dialog).findByText(/Published v3 .* It is now Live\./)).toBeInTheDocument();
  expect(requests.filter((request) => request.route === "publish")).toHaveLength(1);
  await userEvent.click(within(dialog).getByRole("button", { name: "Close" }));
  expect(screen.queryByRole("dialog", { name: "Publish HR helper" })).not.toBeInTheDocument();
});

test("the top bar's Saved state follows the Draft as it is edited", async () => {
  setUp({ agents: [hrHelper] });
  renderStudio(agentPage(hrHelper.id));

  await userEvent.type(await screen.findByLabelText("Max output tokens", {}, { timeout: 5000 }), "0");

  expect(within(banner()).getByRole("status", { name: "Draft status" })).toHaveTextContent("Unsaved changes");
  expect(await within(banner()).findByText("All changes saved", {}, { timeout: 3000 })).toBeInTheDocument();
});

test("an archived Agent has no Publish, and the top bar says the Draft is read only", async () => {
  setUp();
  renderStudio(agentPage(oldHelper.id));

  expect(await within(await bannerLoaded()).findByRole("status", { name: "Draft status" }, { timeout: 5000 })).toHaveTextContent(
    "Read only while archived.",
  );
  expect(within(banner()).queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
  expect(within(banner()).getByRole("link", { name: "History" })).toBeInTheDocument();
});

test("Live, Draft and Not live are badges beside the Agent's name", async () => {
  setUp({ agents: [liveHelper, payHelper], versions: { [liveHelper.id]: [v2, v1] } });
  renderStudio(agentPage(liveHelper.id));

  const header = await screen.findByRole("region", { name: "HR helper" }, { timeout: 5000 });
  expect(within(header).getByText("Live")).toBeInTheDocument();
  expect(within(header).getByLabelText("Version 2")).toBeInTheDocument();
  expect(within(header).getByText("Draft")).toHaveAttribute("title", "The Draft has changes that aren't published yet.");

  await openSection("Agents", "Pay helper");
  const other = await screen.findByRole("region", { name: "Pay helper" });
  expect(within(other).getByText("Not live")).toBeInTheDocument();
  expect(within(other).queryByText("Draft")).not.toBeInTheDocument();
});

// The Playground and its configuration

test("the configuration is four sections: Behaviour open, the rest folded with a summary", async () => {
  setUp({ agents: [hrHelper] });
  renderStudio(agentPage(hrHelper.id));

  const panel = await screen.findByRole("form", { name: "Draft" }, { timeout: 5000 });
  expect(within(panel).getByRole("textbox", { name: "System prompt" })).toBeVisible();
  expect(within(panel).getByLabelText("Chunks per answer (top-k)")).not.toBeVisible();
  expect(within(panel).getByText("Automatic · top-5 · hybrid 0.5")).toBeVisible();
  expect(within(panel).getByText("block · fail closed")).toBeVisible();

  await userEvent.click(within(panel).getByText("Retrieval"));
  expect(within(panel).getByLabelText("Chunks per answer (top-k)")).toBeVisible();
  await userEvent.click(within(panel).getByText("Guardrails"));
  expect(within(panel).getByLabelText("Input Guardrail mode")).toBeVisible();
});

test("a section opens to show a setting the API refused", async () => {
  setUp({
    agents: [hrHelper],
    saveDraft: () =>
      Response.json(
        { detail: [{ loc: ["body", "retrieval", "top_k"], msg: "Input should be less than or equal to 20", type: "x" }] },
        { status: 422 },
      ),
  });
  renderStudio(agentPage(hrHelper.id));

  await userEvent.type(await screen.findByLabelText("Max output tokens", {}, { timeout: 5000 }), "0");

  await waitFor(
    () => {
      expect(screen.getByLabelText("Chunks per answer (top-k)")).toBeVisible();
    },
    { timeout: 3000 },
  );
});

test("each answer's Trace folds open under it", async () => {
  setUp({ agents: [hrHelper], answer: () => streamedAnswer(["Twenty-five days."]) });
  renderStudio(agentPage(hrHelper.id));
  await userEvent.type(await screen.findByLabelText("Question", {}, { timeout: 5000 }), "How much leave?");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  const answer = await within(screen.getByRole("list", { name: "Playground messages" })).findByRole("listitem", {
    name: "HR helper",
  });
  await within(answer).findByText(/output tokens/);
  expect(within(answer).queryByRole("table", { name: "Retrieved Chunks" })).not.toBeInTheDocument();

  await userEvent.click(within(answer).getByText("Trace"));

  expect(await within(answer).findByRole("table", { name: "Retrieved Chunks" })).toBeVisible();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

  await userEvent.click(within(answer).getByText("Trace"));
  expect(within(answer).getByRole("table", { name: "Retrieved Chunks" })).not.toBeVisible();
});

// The ⋯ menu

test("the Agent's ⋯ menu archives it after a confirmation", async () => {
  const { requests } = setUp();
  renderStudio(agentPage(hrHelper.id));

  await choose("More Agent actions", "Archive");
  const dialog = screen.getByRole("alertdialog", { name: "Archive HR helper?" });
  expect(dialog).toHaveTextContent(/HR helper will be hidden from the Agents list/);
  await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
  expect(requests.filter((request) => request.route === "archive")).toEqual([]);

  await choose("More Agent actions", "Archive");
  await userEvent.click(screen.getByRole("button", { name: "Yes, archive HR helper" }));

  expect(await screen.findByRole("status", { name: "Archived" })).toBeInTheDocument();
  await waitFor(() => {
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });
  expect(requests.filter((request) => request.route === "archive")).toEqual([{ route: "archive" }]);
});

test("an archived Agent's ⋯ menu deletes it permanently once its name is typed", async () => {
  const { requests } = setUp();
  renderStudio(agentPage(oldHelper.id));

  await choose("More Agent actions", "Delete permanently");
  const dialog = screen.getByRole("alertdialog", { name: "Delete Old helper permanently" });
  const confirm = within(dialog).getByRole("button", { name: "Delete Old helper permanently" });
  expect(confirm).toBeDisabled();
  await userEvent.type(within(dialog).getByLabelText("Type Old helper to confirm"), "Old helper{Enter}");

  expect(await screen.findByText("Old helper was deleted permanently.")).toBeInTheDocument();
  expect(requests).toEqual([{ route: "delete", body: { confirm_name: "Old helper" } }]);
});

test("Discard Draft is in the ⋯ menu while the Draft has unpublished changes", async () => {
  const { requests } = setUp({ agents: [liveHelper], versions: { [liveHelper.id]: [v2, v1] } });
  renderStudio(agentPage(liveHelper.id));

  await choose("More Agent actions", "Discard Draft");
  const dialog = screen.getByRole("alertdialog", { name: "Discard the Draft?" });
  expect(dialog).toHaveTextContent("goes back to the settings of the Live Version (v2)");
  await userEvent.click(within(dialog).getByRole("button", { name: "Yes, discard the changes" }));

  await waitFor(() => {
    expect(requests.filter((request) => request.route === "discard")).toHaveLength(1);
  });
});

// Versions

test("Versions: Revert and Start Draft from are in ⋯ menus, confirmed in a dialog", async () => {
  const live = { ...hrHelper, live_version: { id: v2.id, number: 2 } };
  const { requests } = setUp({
    agents: [live],
    versions: { [live.id]: [v2, v1] },
    liveHistory: {
      [live.id]: [
        {
          from_version: { id: v1.id, number: 1 },
          to_version: { id: v2.id, number: 2 },
          action: "publish",
          actor: { id: "6a1b0c58-0d6e-4c1b-9d1e-1f1a6c0f0a01", name: "Ada Lovelace" },
          occurred_at: "2026-11-06T10:01:00Z",
          bulk_operation_id: null,
        },
        {
          from_version: null,
          to_version: { id: v1.id, number: 1 },
          action: "publish",
          actor: { id: "6a1b0c58-0d6e-4c1b-9d1e-1f1a6c0f0a01", name: "Ada Lovelace" },
          occurred_at: "2026-11-06T10:00:00Z",
          bulk_operation_id: null,
        },
      ],
    },
  });
  renderStudio(agentPage(live.id, "/versions"));

  await choose("Actions for the Live Version", "Revert to v1");
  const revert = screen.getByRole("dialog", { name: "Revert to v1?" });
  expect(revert).toHaveTextContent("Visitors are served v1 with the Instructions it pins at once.");
  await userEvent.click(within(revert).getByRole("button", { name: "Yes, revert to v1" }));
  expect(await screen.findByText(/Reverted to v1 .* It is now Live\./)).toBeInTheDocument();

  await choose("Actions for v1", "Start Draft from v1");
  const start = screen.getByRole("dialog", { name: "Start Draft from v1?" });
  await userEvent.click(within(start).getByRole("button", { name: "Yes, replace the Draft" }));
  await waitFor(() => {
    expect(requests.filter((request) => request.route === "from-version")).toHaveLength(1);
  });
  expect(requests.filter((request) => request.route === "revert")).toEqual([{ route: "revert" }]);
});

test("Versions compares From and To with a line Diff of the Instructions and settings", async () => {
  const live = { ...hrHelper, live_version: { id: v2.id, number: 2 } };
  setUp({
    agents: [live],
    versions: { [live.id]: [v2, v1] },
    diff: (from, to) => ({
      from: { kind: "version", version: { id: from, number: 1 } },
      to: { kind: "version", version: { id: to, number: 2 } },
      changes: [
        {
          path: "behaviour.system_prompt",
          before: "Answer from the handbook.",
          after: "Answer from the handbook.\nBe brief.",
          lines: [
            { op: "equal", text: "Answer from the handbook." },
            { op: "insert", text: "Be brief." },
          ],
          added: null,
          removed: null,
        },
      ],
      instructions: {
        before: { id: "1a5e0000-0000-4000-8000-000000000001", number: 1 },
        after: { id: "1a5e0000-0000-4000-8000-000000000002", number: 2 },
        lines: [
          { op: "delete", text: "Be formal." },
          { op: "insert", text: "Be friendly." },
        ],
      },
    }),
  });
  renderStudio(agentPage(live.id, "/versions"));

  await userEvent.selectOptions(await screen.findByLabelText("From", {}, { timeout: 5000 }), "v1");
  await userEvent.selectOptions(screen.getByLabelText("To"), "v2 (Live)");

  const prompt = await screen.findByRole("table", { name: "Behaviour › System prompt changes" });
  expect(within(prompt).getAllByRole("row").slice(1).map((row) => row.textContent)).toEqual([
    "11Answer from the handbook.",
    "2+AddedBe brief.",
  ]);
  const instructions = screen.getByRole("table", { name: "Project Instructions changes" });
  expect(within(instructions).getAllByRole("row").slice(1).map((row) => row.textContent)).toEqual([
    "1−RemovedBe formal.",
    "1+AddedBe friendly.",
  ]);
});

// Embed & limits

test("Embed & limits: the snippet with its launcher, and copying it", async () => {
  const user = userEvent.setup();
  setUp({ agents: [liveHelper], versions: { [liveHelper.id]: [v2, v1] } });
  renderStudio(agentPage(liveHelper.id, "/embed"));

  const snippet = await screen.findByRole("region", { name: "Embed Snippet" }, { timeout: 5000 });
  await user.selectOptions(within(snippet).getByLabelText("Launcher"), "Bubble in the corner");
  await user.click(within(snippet).getByRole("button", { name: "Copy Embed Snippet" }));

  expect(await within(snippet).findByText("Embed Snippet copied.")).toBeInTheDocument();
  expect(await navigator.clipboard.readText()).toContain('data-launcher="bubble"');
});

test("Embed & limits: Allowed Origins are an editable list that warns when empty", async () => {
  const { requests } = setUp({ agents: [liveHelper], allowedOrigins: [] });
  renderStudio(agentPage(liveHelper.id, "/embed"));

  const origins = await screen.findByRole("region", { name: "Allowed Origins" }, { timeout: 5000 });
  expect(await within(origins).findByText("No site can embed this Agent until you add an origin.")).toBeInTheDocument();
  await userEvent.type(within(origins).getByRole("textbox", { name: "Add an Allowed Origin" }), "https://www.example.com{Enter}");
  expect(within(origins).getByRole("list", { name: "Allowed Origins" })).toHaveTextContent("https://www.example.com");
  expect(within(origins).queryByText(/No site can embed/)).not.toBeInTheDocument();

  await userEvent.click(within(origins).getByRole("button", { name: "Save Allowed Origins" }));

  expect(await within(origins).findByText("Saved. Pages on these sites can show the Agent now.")).toBeInTheDocument();
  expect(requests.filter((request) => request.route === "operational-settings")).toEqual([
    { route: "operational-settings", body: { allowed_origins: ["https://www.example.com"] } },
  ]);
});

test("Embed & limits: the Token Budget is a meter, beside the rate limits and the unavailable text", async () => {
  setUp({ agents: [liveHelper], tokensUsed: 850_000 });
  renderStudio(agentPage(liveHelper.id, "/embed"));

  const budget = await screen.findByRole("region", { name: "Token Budget" }, { timeout: 5000 });
  const meter = await within(budget).findByRole("meter", { name: "Tokens used today" });
  expect(meter).toHaveAttribute("aria-valuetext", "850,000 of 1,000,000 tokens");
  expect(screen.getByRole("region", { name: "Rate limits" })).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Unavailable text" })).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Theme override" })).toBeInTheDocument();
});

test("an archived Agent's Embed & limits view says it can't be embedded", async () => {
  setUp();
  renderStudio(agentPage(oldHelper.id, "/embed"));

  expect(
    await screen.findByText("An archived Agent can't be embedded. An Owner can restore it.", {}, { timeout: 5000 }),
  ).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Allowed Origins" })).not.toBeInTheDocument();
});
