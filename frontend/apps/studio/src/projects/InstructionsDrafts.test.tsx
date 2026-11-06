import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeProjectsApi, hrProject, instructionsVersion } from "../test/projects";
import { renderStudio } from "../test/render";

const organisationId = adaSession.organisations[0]?.id ?? "";
const instructionsTab = `/organisations/${organisationId}/projects/${hrProject.id}/instructions`;

const v1 = instructionsVersion(1, { markdown: "Be kind." });
const v2 = instructionsVersion(2, { markdown: "Be kind.\nNever quote salaries.", previous_version_id: v1.id });

function setUp(options: Parameters<typeof fakeProjectsApi>[0] = {}) {
  fakeAuthApi({ signedInAs: adaSession });
  return fakeProjectsApi({
    instructions: { [hrProject.id]: "Be kind.\nAsk HR." },
    versions: { [hrProject.id]: { current_version_id: v2.id, versions: [v2, v1] } },
    ...options,
  });
}

async function compare() {
  await screen.findByRole("list", { name: "Instructions Versions" }, { timeout: 5000 });
  return screen.getByRole("region", { name: "Compare" });
}

function lines(list: HTMLElement) {
  return within(list)
    .getAllByRole("listitem")
    .map((line) => line.textContent);
}

test("by default the saved Draft is compared with the Current Version", async () => {
  setUp();
  renderStudio(instructionsTab);
  const region = await compare();

  expect(within(region).getByLabelText("From")).toHaveValue(v2.id);
  expect(within(region).getByLabelText("To")).toHaveValue("draft");
  expect(within(within(region).getByLabelText("From")).getAllByRole("option").map((option) => option.textContent)).toEqual([
    "Draft (saved)",
    "v2 (Current)",
    "v1",
  ]);
  const diff = await within(region).findByRole("list", { name: "Changes from v2 to the Draft" }, { timeout: 5000 });
  expect(lines(diff)).toEqual(["Unchanged:   Be kind.", "Removed: − Never quote salaries.", "Added: + Ask HR."]);
});

test("an Editor compares any two Instructions Versions", async () => {
  setUp();
  renderStudio(instructionsTab);
  const region = await compare();

  await userEvent.selectOptions(within(region).getByLabelText("From"), v1.id);
  await userEvent.selectOptions(within(region).getByLabelText("To"), v2.id);

  const diff = await within(region).findByRole("list", { name: "Changes from v1 to v2" }, { timeout: 5000 });
  expect(lines(diff)).toEqual(["Unchanged:   Be kind.", "Added: + Never quote salaries."]);
});

test("identical sides have no differences", async () => {
  setUp();
  renderStudio(instructionsTab);
  const region = await compare();

  await userEvent.selectOptions(within(region).getByLabelText("To"), v2.id);

  expect(await within(region).findByText("No differences: v2 and v2 are the same.", {}, { timeout: 5000 })).toBeInTheDocument();
});

test("Instructions that were never published compare from the Draft", async () => {
  setUp({ versions: { [hrProject.id]: { current_version_id: null, versions: [v1] } } });
  renderStudio(instructionsTab);
  const region = await compare();

  expect(within(region).getByLabelText("From")).toHaveValue("draft");
  expect(await within(region).findByText("No differences: the Draft and the Draft are the same.", {}, { timeout: 5000 })).toBeInTheDocument();
});

test("a comparison that can't be loaded says so", async () => {
  setUp({ diffStatus: 500 });
  renderStudio(instructionsTab);
  const region = await compare();

  expect(await within(region).findByText(/The comparison could not be loaded/, {}, { timeout: 5000 })).toBeInTheDocument();
});

test("Instructions without Versions offer nothing to compare", async () => {
  setUp({ versions: { [hrProject.id]: { current_version_id: null, versions: [] } } });
  renderStudio(instructionsTab);

  expect(await screen.findByText(/Not published yet/, {}, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Compare" })).not.toBeInTheDocument();
});

// Stale saves

async function openMarkdownView() {
  await userEvent.click(await screen.findByRole("button", { name: "Markdown" }, { timeout: 5000 }));
  return screen.getByRole("textbox", { name: "Project Instructions (Markdown)" });
}

test("a save refused because someone else saved first prompts to load their Instructions", async () => {
  const { colleagueSavesInstructions } = setUp();
  renderStudio(instructionsTab);
  const source = await openMarkdownView();
  colleagueSavesInstructions(hrProject.id, "Theirs.");

  await userEvent.clear(source);
  await userEvent.type(source, "Mine.");
  await userEvent.click(screen.getByRole("button", { name: "Save Instructions" }));

  const prompt = await screen.findByRole("alert", {}, { timeout: 5000 });
  expect(prompt).toHaveTextContent("Someone else saved these Instructions while you were editing");
  expect(screen.queryByText("Instructions saved")).not.toBeInTheDocument();
  await userEvent.click(within(prompt).getByRole("button", { name: "Load their changes" }));

  expect(await openMarkdownView()).toHaveValue("Theirs.");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("an Editor can save their Instructions over a colleague's on purpose", async () => {
  const { colleagueSavesInstructions, requests } = setUp();
  renderStudio(instructionsTab);
  const source = await openMarkdownView();
  colleagueSavesInstructions(hrProject.id, "Theirs.");
  await userEvent.clear(source);
  await userEvent.type(source, "Mine.");
  await userEvent.click(screen.getByRole("button", { name: "Save Instructions" }));
  const prompt = await screen.findByRole("alert", {}, { timeout: 5000 });

  await userEvent.click(within(prompt).getByRole("button", { name: "Save mine over theirs" }));

  expect(await screen.findByText("Instructions saved", {}, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(requests.filter((request) => request.route === "instructions").map((request) => request.body)).toEqual([
    { markdown: "Mine." },
    { markdown: "Mine." },
  ]);
  // Saving again works on the revision just saved.
  await userEvent.type(source, " Again.");
  await userEvent.click(screen.getByRole("button", { name: "Save Instructions" }));
  await screen.findByText("Instructions saved", {}, { timeout: 5000 });
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("publishing Instructions someone else has changed publishes nothing and prompts the same way", async () => {
  const { colleagueSavesInstructions, requests } = setUp();
  renderStudio(instructionsTab);
  const source = await openMarkdownView();
  colleagueSavesInstructions(hrProject.id, "Theirs.");
  await userEvent.clear(source);
  await userEvent.type(source, "Mine.");

  const publish = screen.getByRole("form", { name: "Publish Instructions" });
  await userEvent.type(within(publish).getByLabelText("Note"), "Mine");
  await userEvent.click(within(publish).getByRole("button", { name: "Publish Instructions" }));

  expect(await screen.findByRole("alert", {}, { timeout: 5000 })).toHaveTextContent("Someone else saved these Instructions");
  expect(requests.filter((request) => request.route === "publish")).toEqual([]);
  expect(within(publish).queryByText(/could not be saved/)).not.toBeInTheDocument();
});

test("publishing twice in a row works on the revision the first publish saved", async () => {
  const { requests } = setUp();
  renderStudio(instructionsTab);
  const source = await openMarkdownView();
  const publish = screen.getByRole("form", { name: "Publish Instructions" });

  for (const [markdown, note] of [
    ["First.", "One"],
    ["Second.", "Two"],
  ] as const) {
    await userEvent.clear(source);
    await userEvent.type(source, markdown);
    await userEvent.type(within(publish).getByLabelText("Note"), note);
    await userEvent.click(within(publish).getByRole("button", { name: "Publish Instructions" }));
    await within(publish).findByRole("status", {}, { timeout: 5000 });
  }

  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(requests.filter((request) => request.route === "publish")).toHaveLength(2);
  // A save afterwards is on the latest revision too.
  await userEvent.click(screen.getByRole("button", { name: "Save Instructions" }));
  expect(await screen.findByText("Instructions saved", {}, { timeout: 5000 })).toBeInTheDocument();
});
