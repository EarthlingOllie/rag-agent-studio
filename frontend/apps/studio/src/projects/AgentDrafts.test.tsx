import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { agentVersion, defaultDraft, emptyDiff, fakeAgentsApi, hrHelper, hrTag, payTag } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const agentPage = `/organisations/${organisationId}/projects/${hrProject.id}/agents/${hrHelper.id}`;
type Draft = typeof defaultDraft;

const prompted = (system_prompt: string): Draft => ({ ...defaultDraft, behaviour: { ...defaultDraft.behaviour, system_prompt } });
const v1 = agentVersion(1, { config: prompted("First"), note: "First release" });
const v2 = agentVersion(2, {
  config: prompted("Second"),
  note: "Shorter answers",
  author: { id: "6a1b0c58-0d6e-4c1b-9d1e-1f1a6c0f0a02", name: "Grace Hopper" },
  instructions_version: { id: "b1e00000-0000-4000-8000-000000000002", number: 2 },
});
/** Live v2, with a Draft that differs from it. */
const liveHelper = {
  ...hrHelper,
  draft: prompted("Draft"),
  draft_revision: 4,
  live_version: { id: v2.id, number: 2 },
  has_unpublished_changes: true,
};

function setUp(options: Parameters<typeof fakeAgentsApi>[0] = {}) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  return fakeAgentsApi({ agents: [liveHelper], versions: { [hrHelper.id]: [v2, v1] }, ...options });
}

async function openAgent() {
  renderStudio(agentPage);
  return screen.findByRole("form", { name: "Draft" }, { timeout: 5000 });
}

const systemPrompt = () => within(screen.getByRole("group", { name: "Behaviour" })).findByRole("textbox", { name: "System prompt" });
const versionsList = () => screen.findByRole("list", { name: "Versions" }, { timeout: 5000 });

function routes(requests: { route: string; body?: unknown }[], route: string) {
  return requests.filter((request) => request.route === route).map((request) => request.body);
}

/** A Draft-to-Live diff touching every kind of setting. */
const draftToLive = {
  from: { kind: "version" as const, version: { id: v2.id, number: 2 } },
  to: { kind: "draft" as const, version: null },
  changes: [
    {
      path: "behaviour.system_prompt",
      before: "# Role\nHelp with HR.",
      after: "# Role\nHelp with HR and IT.",
      added: null,
      removed: null,
      lines: [
        { op: "equal" as const, text: "# Role" },
        { op: "delete" as const, text: "Help with HR." },
        { op: "insert" as const, text: "Help with HR and IT." },
      ],
    },
    {
      path: "behaviour.model",
      before: null,
      after: { credential_id: "c1000000-0000-4000-8000-000000000001", model: "gpt-4.1" },
      added: null,
      removed: null,
      lines: null,
    },
    { path: "behaviour.temperature", before: 0.7, after: 0.2, added: null, removed: null, lines: null },
    {
      path: "retrieval.tag_ids",
      before: [hrTag.id, "d1000000-0000-4000-8000-00000000dead"],
      after: [hrTag.id, payTag.id],
      added: [payTag.id],
      removed: ["d1000000-0000-4000-8000-00000000dead"],
      lines: null,
    },
    { path: "retrieval.citations", before: true, after: false, added: null, removed: null, lines: null },
    { path: "experience.starter_questions", before: [], after: ["Holidays?"], added: ["Holidays?"], removed: [], lines: null },
    { path: "experience.greeting", before: "", after: "Hi", added: null, removed: null, lines: null },
    { path: "experience.ui_text.send_button", before: "Go", after: null, added: null, removed: null, lines: null },
    { path: "experience.starter_questions", before: ["A?", "B?"], after: ["B?", "A?"], added: [], removed: [], lines: null },
  ],
  instructions: null,
};

// Unpublished changes

test("a live Agent whose Draft differs from the Live Version is badged", async () => {
  setUp();
  await openAgent();

  expect(screen.getByText("Live v2")).toBeInTheDocument();
  expect(screen.getByText("Unpublished changes")).toBeInTheDocument();
});

test("the badge appears once a change to a live Agent's Draft is saved, and goes once it is published", async () => {
  setUp({ agents: [{ ...liveHelper, draft: v2.config, has_unpublished_changes: false }] });
  await openAgent();
  expect(screen.queryByText("Unpublished changes")).not.toBeInTheDocument();

  const temperature = within(screen.getByRole("group", { name: "Behaviour" })).getByLabelText("Temperature");
  await userEvent.clear(temperature);
  await userEvent.type(temperature, "0.2");

  expect(await screen.findByText("Unpublished changes", {}, { timeout: 5000 })).toBeInTheDocument();
  const publish = screen.getByRole("form", { name: "Publish" });
  await userEvent.type(within(publish).getByLabelText("Note"), "Cooler");
  await userEvent.click(within(publish).getByRole("button", { name: "Publish" }));
  expect(await screen.findByText("Live v3", {}, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.queryByText("Unpublished changes")).not.toBeInTheDocument();
});

// The publish dialog's diff

test("the publish dialog shows what the Draft changes from the Live Version", async () => {
  const { requests } = setUp({ diff: () => draftToLive });
  await openAgent();

  const changes = await within(screen.getByRole("region", { name: "Changes to publish" })).findByRole(
    "list",
    { name: "Changes from v2 to the Draft" },
    { timeout: 5000 },
  );
  expect(within(screen.getByRole("form", { name: "Publish" })).getByRole("heading", { name: "Changes from the Live Version (v2)" })).toBeInTheDocument();
  expect(routes(requests, "diff")).toContainEqual({ from: "live", to: "draft" });
  const items = [...changes.children] as HTMLElement[];
  expect(items.map((item) => item.querySelector("p")?.textContent)).toEqual([
    "Behaviour › System prompt",
    "Behaviour › Model",
    "Behaviour › Temperature",
    "Retrieval › Tag ids",
    "Retrieval › Citations",
    "Experience › Starter questions",
    "Experience › Greeting",
    "Experience › Ui text › Send button",
    "Experience › Starter questions",
  ]);
  const prompt = within(changes).getByRole("list", { name: "Behaviour › System prompt changes" });
  expect(within(prompt).getAllByRole("listitem").map((line) => line.textContent)).toEqual([
    "Unchanged:   # Role",
    "Removed: − Help with HR.",
    "Added: + Help with HR and IT.",
  ]);
  expect(items[1]).toHaveTextContent("(none) → gpt-4.1");
  expect(items[2]).toHaveTextContent("0.7 → 0.2");
  // Tags read as their names; a Tag that no longer exists as its ID.
  expect(await within(items[3] as HTMLElement).findByText("Added: Pay", {}, { timeout: 5000 })).toBeInTheDocument();
  expect(items[3]).toHaveTextContent("Removed: d1000000-0000-4000-8000-00000000dead");
  expect(items[4]).toHaveTextContent("On → Off");
  expect(items[5]).toHaveTextContent("Added: Holidays?");
  expect(items[5]).not.toHaveTextContent("Removed");
  expect(items[6]).toHaveTextContent("(empty) → Hi");
  expect(items[7]).toHaveTextContent("Go → (none)");
  expect(items[8]).toHaveTextContent("Reordered");
});

test("the publish dialog says when the Draft is the same as the Live Version", async () => {
  setUp({ agents: [{ ...liveHelper, has_unpublished_changes: false }] });
  await openAgent();

  const changes = screen.getByRole("region", { name: "Changes to publish" });
  expect(await within(changes).findByText("No differences: v2 and the Draft have the same settings.", {}, { timeout: 5000 })).toBeInTheDocument();
});

test("the first publish says the whole Draft goes live, without asking for a diff", async () => {
  const { requests } = setUp({ agents: [hrHelper], versions: {} });
  await openAgent();

  const changes = screen.getByRole("region", { name: "Changes to publish" });
  expect(within(changes).getByRole("heading", { name: "Changes" })).toBeInTheDocument();
  expect(within(changes).getByText(/This is the first Version/)).toBeInTheDocument();
  expect(routes(requests, "diff")).not.toContainEqual({ from: "live", to: "draft" });
});

test("the publish dialog says when the diff can't be loaded", async () => {
  let release: () => void = () => undefined;
  const held = new Promise<void>((resolve) => (release = resolve));
  setUp({
    diff: (from, to) => (from === "live" ? held.then(() => HttpResponse.json({ detail: "Boom" }, { status: 500 })) : emptyDiff(from, to)),
  });
  await openAgent();
  const changes = screen.getByRole("region", { name: "Changes to publish" });
  expect(within(changes).getByText("Comparing the Draft with the Live Version (v2)…")).toBeInTheDocument();
  release();

  expect(await within(changes).findByText(/The changes could not be loaded/, {}, { timeout: 5000 })).toBeInTheDocument();
});

// Discarding the Draft

test("an Editor discards the Draft back to the Live Version after confirming", async () => {
  const { requests } = setUp();
  await openAgent();
  expect(await systemPrompt()).toHaveTextContent("Draft");

  await userEvent.click(screen.getByRole("button", { name: "Discard Draft" }));
  const confirm = screen.getByRole("group", { name: "Discard the Draft" });
  expect(confirm).toHaveTextContent("it goes back to the settings of the Live Version (v2)");
  await userEvent.click(within(confirm).getByRole("button", { name: "Cancel" }));
  expect(routes(requests, "discard")).toEqual([]);
  await userEvent.click(screen.getByRole("button", { name: "Discard Draft" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, discard the changes" }));

  expect(await within(screen.getByRole("group", { name: "Behaviour" })).findByText("Second", {}, { timeout: 5000 })).toBeInTheDocument();
  expect(routes(requests, "discard")).toEqual([{ base_revision: 4 }]);
  expect(screen.queryByText("Unpublished changes")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Discard Draft" })).not.toBeInTheDocument();
});

test("the Draft can't be discarded once someone else has changed it, and their Draft is shown", async () => {
  const { colleagueSaves } = setUp();
  await openAgent();
  colleagueSaves(hrHelper.id, prompted("Colleague's edit"));

  await userEvent.click(screen.getByRole("button", { name: "Discard Draft" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, discard the changes" }));

  expect(await screen.findByText(/Someone else changed this Draft since you opened it/, {}, { timeout: 5000 })).toBeInTheDocument();
});

test("an Agent without unpublished changes, or not live, offers no discard", async () => {
  setUp({ agents: [{ ...liveHelper, has_unpublished_changes: false }] });
  await openAgent();
  expect(screen.queryByRole("button", { name: "Discard Draft" })).not.toBeInTheDocument();
});

// Versions and starting the Draft from one

test("the Version history lists each Version with its author, note, Instructions and which is Live", async () => {
  setUp();
  await openAgent();

  const [second, first] = within(await versionsList()).getAllByRole("listitem") as [HTMLElement, HTMLElement];
  expect(second).toHaveTextContent("v2Live · Shorter answers");
  expect(second).toHaveTextContent("Grace Hopper");
  expect(second).toHaveTextContent("Instructions v2");
  expect(first).toHaveTextContent("v1 · First release");
  expect(first).toHaveTextContent("No Project Instructions");
  expect(first).not.toHaveTextContent("Live");
});

test("an Agent that has never been published has no Versions yet", async () => {
  setUp({ agents: [hrHelper], versions: {} });
  await openAgent();

  expect(await screen.findByText("No Versions yet. Publishing the Draft makes v1.", {}, { timeout: 5000 })).toBeInTheDocument();
});

test("the Version history says when it can't be loaded", async () => {
  setUp();
  server.use(http.get("*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/versions", () => HttpResponse.json({}, { status: 500 })));
  await openAgent();

  expect(await screen.findByText("The Versions could not be loaded.", {}, { timeout: 5000 })).toBeInTheDocument();
});

test("an Editor starts the Draft from an earlier Version after confirming", async () => {
  const { requests } = setUp();
  await openAgent();
  const first = within(await versionsList()).getAllByRole("listitem")[1] as HTMLElement;

  await userEvent.click(within(first).getByRole("button", { name: "Start Draft from v1" }));
  await userEvent.click(within(first).getByRole("button", { name: "Cancel" }));
  await userEvent.click(within(first).getByRole("button", { name: "Start Draft from v1" }));
  expect(within(first).getByRole("group", { name: "Start Draft from v1" })).toHaveTextContent("Nothing is published");
  await userEvent.click(within(first).getByRole("button", { name: "Yes, replace the Draft" }));

  expect(await within(screen.getByRole("group", { name: "Behaviour" })).findByText("First", {}, { timeout: 5000 })).toBeInTheDocument();
  expect(routes(requests, "from-version")).toEqual([{ version_id: v1.id, base_revision: 4 }]);
  // v2 stays Live, and the Draft now differs from it.
  expect(screen.getByText("Live v2")).toBeInTheDocument();
  expect(screen.getByText("Unpublished changes")).toBeInTheDocument();
});

test("a Version whose credential is gone can't start the Draft", async () => {
  setUp({ replaceDraft: () => HttpResponse.json({ detail: [{ loc: ["body", "behaviour", "model", "credential_id"], msg: "gone" }] }, { status: 422 }) });
  await openAgent();
  const first = within(await versionsList()).getAllByRole("listitem")[1] as HTMLElement;

  await userEvent.click(within(first).getByRole("button", { name: "Start Draft from v1" }));
  await userEvent.click(within(first).getByRole("button", { name: "Yes, replace the Draft" }));

  expect(await within(first).findByText(/names a credential or Tag that no longer exists/, {}, { timeout: 5000 })).toBeInTheDocument();
  expect(await systemPrompt()).toHaveTextContent("Draft");
});

test("other refusals of a Draft change show the API's reason", async () => {
  setUp({ replaceDraft: () => HttpResponse.json({ detail: "This Agent is archived. An Owner can restore it." }, { status: 409 }) });
  await openAgent();

  await userEvent.click(screen.getByRole("button", { name: "Discard Draft" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, discard the changes" }));

  expect(await screen.findByText("This Agent is archived. An Owner can restore it.", {}, { timeout: 5000 })).toBeInTheDocument();
});

test("an archived Agent's Versions can be read but start no Draft, and it offers no discard", async () => {
  setUp({ agents: [{ ...liveHelper, archived_at: "2026-11-06T09:00:00Z" }] });
  await openAgent();

  expect(within(await versionsList()).getAllByRole("listitem")).toHaveLength(2);
  expect(screen.queryByRole("button", { name: /Start Draft from/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Discard Draft" })).not.toBeInTheDocument();
});

// Comparing Versions

test("an Editor compares any two Versions, including their pinned Instructions", async () => {
  const { requests } = setUp({
    diff: (from, to) =>
      from === v1.id && to === v2.id
        ? {
            from: { kind: "version", version: { id: v1.id, number: 1 } },
            to: { kind: "version", version: { id: v2.id, number: 2 } },
            changes: [{ path: "behaviour.system_prompt", before: "First", after: "Second", added: null, removed: null, lines: [{ op: "delete", text: "First" }, { op: "insert", text: "Second" }] }],
            instructions: { before: null, after: { id: "b1e00000-0000-4000-8000-000000000002", number: 2 }, lines: [{ op: "insert", text: "Be kind." }] },
          }
        : emptyDiff(from, to),
  });
  await openAgent();
  await versionsList();
  const compare = screen.getByRole("region", { name: "Compare" });
  // By default the Live Version against the Draft.
  expect(within(compare).getByLabelText("From")).toHaveValue(v2.id);
  expect(within(compare).getByLabelText("To")).toHaveValue("draft");
  expect(within(within(compare).getByLabelText("From")).getAllByRole("option").map((option) => option.textContent)).toEqual(["Draft", "v2 (Live)", "v1"]);

  await userEvent.selectOptions(within(compare).getByLabelText("From"), v1.id);
  await userEvent.selectOptions(within(compare).getByLabelText("To"), v2.id);

  expect(await within(compare).findByRole("list", { name: "Changes from v1 to v2" }, { timeout: 5000 })).toBeInTheDocument();
  expect(within(compare).getByText("Project Instructions: none → v2")).toBeInTheDocument();
  expect(within(compare).getByRole("list", { name: "Project Instructions changes" })).toHaveTextContent("Be kind.");
  expect(routes(requests, "diff")).toContainEqual({ from: v1.id, to: v2.id });
});

test("a comparison of Versions whose only change is the pinned Instructions shows just that", async () => {
  setUp({
    diff: (from, to) =>
      from === v2.id && to === v1.id
        ? {
            from: { kind: "version", version: { id: v2.id, number: 2 } },
            to: { kind: "version", version: { id: v1.id, number: 1 } },
            changes: [],
            instructions: { before: { id: "b1e00000-0000-4000-8000-000000000002", number: 2 }, after: null, lines: [{ op: "delete", text: "Be kind." }] },
          }
        : emptyDiff(from, to),
  });
  await openAgent();
  await versionsList();
  const compare = screen.getByRole("region", { name: "Compare" });

  await userEvent.selectOptions(within(compare).getByLabelText("To"), v1.id);

  expect(await within(compare).findByText("Project Instructions: v2 → none", {}, { timeout: 5000 })).toBeInTheDocument();
  expect(within(compare).queryByRole("list", { name: /Changes from/ })).not.toBeInTheDocument();
});

test("a comparison that can't be loaded says so", async () => {
  setUp({ diff: (from, to) => (from === "draft" ? HttpResponse.json({ detail: "Boom" }, { status: 500 }) : emptyDiff(from, to)) });
  await openAgent();
  await versionsList();
  const compare = screen.getByRole("region", { name: "Compare" });
  expect(within(compare).getByText("Comparing…")).toBeInTheDocument();

  await userEvent.selectOptions(within(compare).getByLabelText("From"), "draft");

  expect(await within(compare).findByText(/The comparison could not be loaded/, {}, { timeout: 5000 })).toBeInTheDocument();
});

test("an Agent that is not live compares the Draft with itself by default", async () => {
  setUp({ agents: [{ ...liveHelper, live_version: null, has_unpublished_changes: false }] });
  await openAgent();
  await versionsList();
  const compare = screen.getByRole("region", { name: "Compare" });

  expect(within(compare).getByLabelText("From")).toHaveValue("draft");
  expect(await within(compare).findByText(/No differences: the Draft and the Draft/, {}, { timeout: 5000 })).toBeInTheDocument();
});

// Stale saves

test("a save refused because someone else saved first prompts to load their Draft", async () => {
  const { colleagueSaves, requests } = setUp();
  await openAgent();
  colleagueSaves(hrHelper.id, prompted("Colleague's edit"));

  const temperature = within(screen.getByRole("group", { name: "Behaviour" })).getByLabelText("Temperature");
  await userEvent.clear(temperature);
  await userEvent.type(temperature, "0.2");

  const prompt = await screen.findByRole("alert", {}, { timeout: 5000 });
  expect(prompt).toHaveTextContent("Someone else saved this Draft while you were editing");
  expect(screen.getByRole("status", { name: "Draft status" })).toHaveTextContent("Not saved: someone else changed this Draft.");
  expect(routes(requests, "draft")).toHaveLength(1);
  await userEvent.click(within(prompt).getByRole("button", { name: "Load their changes" }));

  expect(await within(screen.getByRole("group", { name: "Behaviour" })).findByText("Colleague's edit", {}, { timeout: 5000 })).toBeInTheDocument();
  expect(within(screen.getByRole("group", { name: "Behaviour" })).getByLabelText("Temperature")).toHaveValue(0.7);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByRole("status", { name: "Draft status" })).toHaveTextContent("All changes saved");
});

test("an Editor can save their Draft over a colleague's on purpose", async () => {
  const { colleagueSaves, requests } = setUp();
  await openAgent();
  colleagueSaves(hrHelper.id, prompted("Colleague's edit"));
  const temperature = within(screen.getByRole("group", { name: "Behaviour" })).getByLabelText("Temperature");
  await userEvent.clear(temperature);
  await userEvent.type(temperature, "0.2");
  const prompt = await screen.findByRole("alert", {}, { timeout: 5000 });

  await userEvent.click(within(prompt).getByRole("button", { name: "Save mine over theirs" }));

  expect(await screen.findByText("All changes saved", {}, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  const sent = routes(requests, "draft") as Draft[];
  expect(sent).toHaveLength(2);
  expect(sent[1]?.behaviour).toEqual({ ...prompted("Draft").behaviour, temperature: 0.2 });
  expect(await systemPrompt()).toHaveTextContent("Draft");
});
