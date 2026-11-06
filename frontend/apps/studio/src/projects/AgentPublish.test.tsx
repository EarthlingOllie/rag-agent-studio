import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { fakeAgentsApi, hrHelper, oldHelper } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeProjectsApi, hrProject, instructionsVersion } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const agentsTab = `/organisations/${organisationId}/projects/${hrProject.id}/agents`;
const agentPage = (agentId: string) => `${agentsTab}/${agentId}`;

const v1 = instructionsVersion(1);
const v2 = instructionsVersion(2, { previous_version_id: v1.id });
const liveHelper = { ...hrHelper, live_version: { id: "a1e00000-0000-4000-8000-000000000003", number: 3 } };

function setUp(
  options: Parameters<typeof fakeAgentsApi>[0] = {},
  versions: Parameters<typeof fakeProjectsApi>[0] = {
    versions: { [hrProject.id]: { current_version_id: v2.id, versions: [v2, v1] } },
  },
) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi(versions);
  return fakeAgentsApi({
    agents: [hrHelper],
    currentInstructions: { id: v2.id, number: 2 },
    ...options,
  });
}

async function publishForm() {
  return screen.findByRole("form", { name: "Publish" }, { timeout: 5000 });
}

test("an Agent that has never been published is shown as not live", async () => {
  setUp({ agents: [hrHelper, liveHelper] });
  renderStudio(agentPage(hrHelper.id));

  expect(await screen.findByText("Not live", {}, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.getByText(/Visitors can't use it until you publish it/)).toBeInTheDocument();
});

test("the Agents list shows which Agents are live and which aren't", async () => {
  const other = { ...liveHelper, id: "a9e00000-0000-4000-8000-000000000002", name: "Benefits FAQ" };
  setUp({ agents: [hrHelper, other] });
  renderStudio(agentsTab);

  const list = await screen.findByRole("list", { name: "Agents" }, { timeout: 5000 });
  const [first, second] = within(list).getAllByRole("listitem") as [HTMLElement, HTMLElement];
  expect(first).toHaveTextContent("HR helper");
  expect(first).toHaveTextContent("Not live");
  expect(second).toHaveTextContent("Benefits FAQ");
  expect(second).toHaveTextContent("Live v3");
});

test("publishing with a note makes the Draft the Live Version, pinning the Current Instructions", async () => {
  const { requests } = setUp();
  renderStudio(agentPage(hrHelper.id));
  const form = await publishForm();
  const picker = within(form).getByRole("combobox", { name: "Project Instructions" });
  expect(picker).toHaveValue("");
  expect(await within(picker).findByRole("option", { name: "Current Version (v2)" })).toBeInTheDocument();
  expect(within(picker).getAllByRole("option").map((option) => option.textContent)).toEqual([
    "Current Version (v2)",
    "v2 · Note 2",
    "v1 · Note 1",
  ]);

  await userEvent.type(within(form).getByLabelText("Note"), "First release");
  await userEvent.click(within(form).getByRole("button", { name: "Publish" }));

  expect(await within(form).findByRole("status")).toHaveTextContent("Published v1 with Instructions v2. It is now Live.");
  expect(await screen.findByText("Live v1")).toBeInTheDocument();
  expect(screen.queryByText("Not live")).not.toBeInTheDocument();
  expect(within(form).getByLabelText("Note")).toHaveValue("");
  expect(requests.filter((r) => r.route === "publish")).toEqual([{ route: "publish", body: { note: "First release" } }]);
});

test("an Editor can pin an older Instructions Version", async () => {
  const { requests } = setUp({ agents: [liveHelper] });
  renderStudio(agentPage(liveHelper.id));
  const form = await publishForm();
  expect(screen.getByText("Live v3")).toBeInTheDocument();
  await within(form).findByRole("option", { name: "v1 · Note 1" });

  await userEvent.selectOptions(within(form).getByRole("combobox", { name: "Project Instructions" }), "v1 · Note 1");
  await userEvent.type(within(form).getByLabelText("Note"), "Hold on v1");
  await userEvent.click(within(form).getByRole("button", { name: "Publish" }));

  expect(await within(form).findByRole("status")).toHaveTextContent("Published v4 with Instructions v1. It is now Live.");
  expect(requests.filter((r) => r.route === "publish")).toEqual([
    { route: "publish", body: { note: "Hold on v1", instructions_version_id: v1.id } },
  ]);
});

test("a Project with no published Instructions publishes without any", async () => {
  setUp({ currentInstructions: null }, { versions: {} });
  renderStudio(agentPage(hrHelper.id));
  const form = await publishForm();
  const picker = within(form).getByRole("combobox", { name: "Project Instructions" });
  expect(await within(picker).findByRole("option", { name: "None (no Instructions published)" })).toBeInTheDocument();

  await userEvent.type(within(form).getByLabelText("Note"), "First");
  await userEvent.click(within(form).getByRole("button", { name: "Publish" }));

  expect(await within(form).findByRole("status")).toHaveTextContent("Published v1 without Project Instructions. It is now Live.");
});

test("the note is required and limited to 500 characters", async () => {
  const { requests } = setUp();
  renderStudio(agentPage(hrHelper.id));
  const form = await publishForm();
  const note = within(form).getByLabelText("Note");
  expect(note).toBeRequired();
  expect(note).toHaveAttribute("maxLength", "500");

  await userEvent.type(note, "   ");
  await userEvent.click(within(form).getByRole("button", { name: "Publish" }));

  expect(await within(form).findByRole("alert")).toHaveTextContent("Add a note of up to 500 characters.");
  expect(requests.filter((r) => r.route === "publish")).toEqual([]);
});

test.each([
  [409, "This Agent is archived. An Owner can restore it.", "This Agent is archived. An Owner can restore it."],
  [422, undefined, "Add a note of up to 500 characters."],
  [500, undefined, "Something went wrong. Try again."],
])("a refused publish (%i) says why and changes nothing", async (status, detail, message) => {
  setUp({ publish: () => HttpResponse.json({ detail: detail ?? [] }, { status }) });
  renderStudio(agentPage(hrHelper.id));
  const form = await publishForm();

  await userEvent.type(within(form).getByLabelText("Note"), "First release");
  await userEvent.click(within(form).getByRole("button", { name: "Publish" }));

  expect(await within(form).findByRole("alert")).toHaveTextContent(message);
  expect(screen.getByText("Not live")).toBeInTheDocument();
  expect(within(form).getByLabelText("Note")).toHaveValue("First release");
});

test("the Instructions picker says when the Versions can't be loaded", async () => {
  setUp();
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/instructions/versions", () =>
      HttpResponse.json({ detail: "Something broke" }, { status: 500 }),
    ),
  );
  renderStudio(agentPage(hrHelper.id));

  expect(await screen.findByText("The Instructions Versions could not be loaded.", {}, { timeout: 5000 })).toBeInTheDocument();
});

test("an archived Agent can't be published", async () => {
  setUp({ agents: [oldHelper] });
  renderStudio(agentPage(oldHelper.id));

  expect(await screen.findByRole("status", { name: "Archived" }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.queryByRole("form", { name: "Publish" })).not.toBeInTheDocument();
  expect(screen.getByText("Not live")).toBeInTheDocument();
});
