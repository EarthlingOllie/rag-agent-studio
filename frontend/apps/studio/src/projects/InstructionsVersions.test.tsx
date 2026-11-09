import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import {
  fakeProjectsApi,
  hrProject,
  instructionsVersion,
  NOTHING_TO_PUBLISH,
  NOTHING_TO_REVERT,
  oldProject,
  PROJECT_ARCHIVED,
} from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const instructionsTab = (projectId: string) => `/organisations/${organisationId}/projects/${projectId}/instructions`;
const VERSIONS = "*/api/organisations/:organisationId/projects/:projectId/instructions/versions";
const REVERT = "*/api/organisations/:organisationId/projects/:projectId/instructions/revert";

const v1 = instructionsVersion(1, {
  markdown: "Be kind.",
  note: "The Instructions as they were when Versions were introduced.",
  author: null,
  created_at: "2026-11-01T09:00:00Z",
});
const v2 = instructionsVersion(2, {
  markdown: "Be kind.\n\nNever quote salaries.",
  note: "Salaries",
  created_at: "2026-11-02T14:30:00Z",
  previous_version_id: v1.id,
});
const published = { current_version_id: v2.id, versions: [v2, v1] };

function setUp(options: Parameters<typeof fakeProjectsApi>[0] = {}) {
  fakeAuthApi({ signedInAs: adaSession });
  return fakeProjectsApi({ instructions: { [hrProject.id]: v2.markdown }, versions: { [hrProject.id]: published }, ...options });
}

async function versionList() {
  return screen.findByRole("list", { name: "Instructions Versions" }, { timeout: 5000 });
}

async function openMarkdownView() {
  await userEvent.click(await screen.findByRole("button", { name: "Markdown" }, { timeout: 5000 }));
  return screen.getByRole("textbox", { name: "Project Instructions (Markdown)" });
}

test("the history is a timeline of every Version newest first, with the Current one badged", async () => {
  setUp();
  renderStudio(instructionsTab(hrProject.id));

  const items = within(await versionList()).getAllByRole("listitem");
  expect(items.map((item) => item.getAttribute("aria-label"))).toEqual(["v2", "v1"]);
  const [newest, oldest] = items as [HTMLElement, HTMLElement];
  // Each Version is a version chip; the Current one also carries the Current badge.
  expect(within(newest).getByLabelText("Version 2")).toHaveTextContent("v2");
  expect(within(oldest).getByLabelText("Version 1")).toHaveTextContent("v1");
  expect(within(newest).getByText("Current")).toBeInTheDocument();
  expect(newest).toHaveTextContent("Salaries");
  expect(newest).toHaveTextContent("Ada Lovelace · 2026-11-02 14:30 UTC");
  expect(within(oldest).queryByText("Current")).not.toBeInTheDocument();
  // The v1 made from the Instructions already there when Versions arrived has no author.
  expect(oldest).toHaveTextContent("No author · 2026-11-01 09:00 UTC");
  expect(screen.getByText("Current Version: v2.")).toBeInTheDocument();

  await userEvent.click(within(oldest).getByText("Show the Instructions"));
  expect(within(oldest).getByText("Be kind.")).toBeVisible();
});

test("an empty Version shows that it is empty", async () => {
  const cleared = instructionsVersion(1, { markdown: "" });
  setUp({ versions: { [hrProject.id]: { current_version_id: cleared.id, versions: [cleared] } } });
  renderStudio(instructionsTab(hrProject.id));

  expect(within(await versionList()).getByText("(empty)")).toBeInTheDocument();
});

test("unpublished Instructions say how to make v1, and there is nothing to revert", async () => {
  setUp({ versions: {} });
  renderStudio(instructionsTab(hrProject.id));

  expect(
    await screen.findByText("Not published yet. Publish the Draft to make v1, the Current Version.", {}, { timeout: 5000 }),
  ).toBeInTheDocument();
  expect(screen.queryByRole("list", { name: "Instructions Versions" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Revert/ })).not.toBeInTheDocument();
});

test("an Editor publishes the Draft as written with a note, and it becomes the Current Version", async () => {
  const { requests } = setUp();
  renderStudio(instructionsTab(hrProject.id));
  const source = await openMarkdownView();
  await userEvent.clear(source);
  await userEvent.type(source, "Be curt.");

  const form = screen.getByRole("form", { name: "Publish Instructions" });
  await userEvent.type(within(form).getByRole("textbox", { name: "Note" }), "Shorter answers");
  await userEvent.click(within(form).getByRole("button", { name: "Publish Instructions" }));

  expect(await within(form).findByRole("status")).toHaveTextContent("Published v3");
  // The Draft is saved exactly as written, then published.
  expect(requests).toEqual([
    { route: "instructions", projectId: hrProject.id, body: { markdown: "Be curt." } },
    { route: "publish", projectId: hrProject.id, body: { note: "Shorter answers" } },
  ]);
  expect(within(form).getByRole("textbox", { name: "Note" })).toHaveValue("");
  const items = within(await versionList()).getAllByRole("listitem");
  await screen.findByText("Current Version: v3.");
  expect(items.map((item) => item.getAttribute("aria-label"))).toEqual(["v3", "v2", "v1"]);
  expect(within(screen.getByRole("listitem", { name: "v3" })).getByText("Current")).toBeInTheDocument();
});

test("the note is required", async () => {
  const { requests } = setUp();
  renderStudio(instructionsTab(hrProject.id));
  const form = await screen.findByRole("form", { name: "Publish Instructions" }, { timeout: 5000 });

  const note = within(form).getByRole("textbox", { name: "Note" });
  expect(note).toBeRequired();
  expect(note).toHaveAttribute("maxlength", "500");
  await userEvent.click(within(form).getByRole("button", { name: "Publish Instructions" }));

  expect(requests).toEqual([]);
});

test("a publish the API refuses shows why", async () => {
  setUp();
  renderStudio(instructionsTab(hrProject.id));
  const form = await screen.findByRole("form", { name: "Publish Instructions" }, { timeout: 5000 });

  // The Draft is still v2's text, so there is nothing to publish.
  await userEvent.type(within(form).getByRole("textbox", { name: "Note" }), "Again");
  await userEvent.click(within(form).getByRole("button", { name: "Publish Instructions" }));
  expect(await within(form).findByRole("alert")).toHaveTextContent(NOTHING_TO_PUBLISH);

  // A note the API refuses (only spaces get past the browser).
  await userEvent.type(within(form).getByRole("textbox", { name: "Note" }), "   ");
  await userEvent.clear(within(form).getByRole("textbox", { name: "Note" }));
  await userEvent.type(within(form).getByRole("textbox", { name: "Note" }), "  ");
  await userEvent.click(within(form).getByRole("button", { name: "Publish Instructions" }));
  expect(await within(form).findByText("Add a note of up to 500 characters.")).toBeInTheDocument();
  expect(within(form).queryByRole("status")).not.toBeInTheDocument();
});

test("a Draft the API refuses to save is not published", async () => {
  const { requests } = setUp();
  server.use(
    http.put("*/api/organisations/:organisationId/projects/:projectId/instructions", () =>
      HttpResponse.json({ detail: PROJECT_ARCHIVED }, { status: 409 }),
    ),
  );
  renderStudio(instructionsTab(hrProject.id));
  const form = await screen.findByRole("form", { name: "Publish Instructions" }, { timeout: 5000 });

  await userEvent.type(within(form).getByRole("textbox", { name: "Note" }), "Shorter");
  await userEvent.click(within(form).getByRole("button", { name: "Publish Instructions" }));

  expect(await within(form).findByRole("alert")).toHaveTextContent(PROJECT_ARCHIVED);
  expect(requests.filter((request) => request.route === "publish")).toEqual([]);
});

test("a Draft the API refuses as too long says the save failed, not the note", async () => {
  const { requests } = setUp();
  server.use(
    http.put("*/api/organisations/:organisationId/projects/:projectId/instructions", () =>
      HttpResponse.json({ detail: [{ msg: "too long" }] }, { status: 422 }),
    ),
  );
  renderStudio(instructionsTab(hrProject.id));
  const form = await screen.findByRole("form", { name: "Publish Instructions" }, { timeout: 5000 });

  await userEvent.type(within(form).getByRole("textbox", { name: "Note" }), "Longer");
  await userEvent.click(within(form).getByRole("button", { name: "Publish Instructions" }));

  expect(await within(form).findByRole("alert")).toHaveTextContent(
    "The Draft could not be saved, so nothing was published. Instructions can be up to 20,000 characters.",
  );
  expect(within(form).queryByText("Add a note of up to 500 characters.")).not.toBeInTheDocument();
  expect(requests.filter((request) => request.route === "publish")).toEqual([]);
});

test("a publish shows its progress", async () => {
  setUp();
  server.use(
    http.post(VERSIONS, async () => {
      await delay(100);
      return HttpResponse.json({ detail: "boom" }, { status: 500 });
    }),
  );
  renderStudio(instructionsTab(hrProject.id));
  const form = await screen.findByRole("form", { name: "Publish Instructions" }, { timeout: 5000 });
  await userEvent.type(within(form).getByRole("textbox", { name: "Note" }), "Shorter");

  await userEvent.click(within(form).getByRole("button", { name: "Publish Instructions" }));

  expect(await within(form).findByRole("button", { name: "Publishing…" })).toBeDisabled();
  expect(await within(form).findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("an Editor reverts the Current Version after confirming, and the Draft is untouched", async () => {
  const { requests } = setUp();
  renderStudio(instructionsTab(hrProject.id));
  await versionList();

  await userEvent.click(screen.getByRole("button", { name: "Revert to v1" }));
  // A ConfirmDialog asks first, with focus on Cancel.
  const confirmation = screen.getByRole("alertdialog", { name: "Revert to v1?" });
  expect(confirmation).toHaveAccessibleDescription("Revert the Current Version to v1? Agents published from now on use v1. The Draft isn't changed.");
  expect(within(confirmation).getByRole("button", { name: "Cancel" })).toHaveFocus();
  await userEvent.click(within(confirmation).getByRole("button", { name: "Yes, revert to v1" }));

  expect(await screen.findByRole("status")).toHaveTextContent("Reverted to v1");
  expect(await screen.findByText("Current Version: v1.")).toBeInTheDocument();
  expect(within(screen.getByRole("listitem", { name: "v1" })).getByText("Current")).toBeInTheDocument();
  // v1 has nothing before it.
  expect(screen.queryByRole("button", { name: /Revert to/ })).not.toBeInTheDocument();
  expect(requests).toEqual([{ route: "revert", projectId: hrProject.id }]);
});

test("cancelling a revert changes nothing", async () => {
  const { requests } = setUp();
  renderStudio(instructionsTab(hrProject.id));
  await versionList();

  await userEvent.click(screen.getByRole("button", { name: "Revert to v1" }));
  await userEvent.click(within(screen.getByRole("alertdialog", { name: "Revert to v1?" })).getByRole("button", { name: "Cancel" }));

  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Revert to v1" })).toHaveFocus();
  expect(requests).toEqual([]);
});

test("a revert the API refuses shows why", async () => {
  setUp();
  server.use(http.post(REVERT, () => HttpResponse.json({ detail: NOTHING_TO_REVERT }, { status: 409 })));
  renderStudio(instructionsTab(hrProject.id));
  await versionList();

  await userEvent.click(screen.getByRole("button", { name: "Revert to v1" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, revert to v1" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(NOTHING_TO_REVERT);
  // Trying again clears the old message.
  await userEvent.click(screen.getByRole("button", { name: "Revert to v1" }));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("an archived Project's history can be read but not published or reverted", async () => {
  setUp({ instructions: { [oldProject.id]: v2.markdown }, versions: { [oldProject.id]: published } });
  renderStudio(instructionsTab(oldProject.id));

  expect(within(await versionList()).getAllByRole("listitem")).toHaveLength(2);
  expect(screen.queryByRole("form", { name: "Publish Instructions" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Revert/ })).not.toBeInTheDocument();
});

test("Versions that can't be loaded say so", async () => {
  setUp();
  server.use(http.get(VERSIONS, () => HttpResponse.json({ detail: "boom" }, { status: 500 })));
  renderStudio(instructionsTab(hrProject.id));

  expect(await screen.findByText("The Versions could not be loaded. Try again shortly.", {}, { timeout: 5000 })).toBeInTheDocument();
});

test("only the latest publish or revert shows its outcome", async () => {
  setUp();
  renderStudio(instructionsTab(hrProject.id));
  await versionList();

  await userEvent.click(screen.getByRole("button", { name: "Revert to v1" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, revert to v1" }));
  expect(await screen.findByText("Reverted to v1")).toBeInTheDocument();

  const source = await openMarkdownView();
  await userEvent.clear(source);
  await userEvent.type(source, "Be curt.");
  const form = screen.getByRole("form", { name: "Publish Instructions" });
  await userEvent.type(within(form).getByRole("textbox", { name: "Note" }), "Shorter answers");
  await userEvent.click(within(form).getByRole("button", { name: "Publish Instructions" }));

  expect(await within(form).findByText("Published v3")).toBeInTheDocument();
  expect(screen.queryByText("Reverted to v1")).not.toBeInTheDocument();

  // v3 was published on top of v1, so reverting goes back to v1.
  await screen.findByText("Current Version: v3.");
  await userEvent.click(screen.getByRole("button", { name: "Revert to v1" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, revert to v1" }));
  expect(await screen.findByText("Reverted to v1")).toBeInTheDocument();
  expect(screen.queryByText("Published v3")).not.toBeInTheDocument();
});
