import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { fakeAgentsApi, hrHelper, oldHelper } from "../test/agents";
import { fakeBulkApi, NOTHING_TO_REVERT, rolloutAgent } from "../test/bulk";
import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeProjectsApi, hrProject, oldProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const agentsTab = (projectId: string) => `/organisations/${organisationId}/projects/${projectId}/agents`;

test("the Agents tab lists the Project's Agents, linking to each", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [hrHelper, { ...hrHelper, id: "a9e00000-0000-4000-8000-000000000002", name: "Benefits FAQ" }] });
  renderStudio(agentsTab(hrProject.id));

  await screen.findByRole("heading", { level: 2, name: "Agents" });
  const list = await within(screen.getByRole("main")).findByRole("list", {}, { timeout: 5000 });
  expect(within(list).getAllByRole("link").map((link) => link.textContent)).toEqual(["HR helper", "Benefits FAQ"]);
  expect(within(list).getByRole("link", { name: "HR helper" })).toHaveAttribute(
    "href",
    `${agentsTab(hrProject.id)}/${hrHelper.id}`,
  );
});

test("an Editor creates an Agent and lands on its page", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const { requests } = fakeAgentsApi();
  renderStudio(agentsTab(hrProject.id));
  expect(await screen.findByText(/No Agents yet/, {}, { timeout: 5000 })).toBeInTheDocument();

  const form = screen.getByRole("form", { name: "New Agent" });
  await userEvent.type(within(form).getByLabelText("Name"), "Helper");
  await userEvent.click(within(form).getByRole("button", { name: "Create Agent" }));

  expect(await screen.findByRole("heading", { level: 2, name: "Helper" }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "System prompt" })).toHaveTextContent("");
  expect(requests).toEqual([{ route: "create", body: { name: "Helper" } }]);
});

test("a refused Agent shows why", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi();
  renderStudio(agentsTab(hrProject.id));

  const form = await screen.findByRole("form", { name: "New Agent" }, { timeout: 5000 });
  await userEvent.type(within(form).getByLabelText("Name"), "A very long name");
  await userEvent.click(within(form).getByRole("button", { name: "Create Agent" }));

  expect(await within(form).findByRole("alert")).toHaveTextContent(/a name up to 200 characters/);
});

test("an archived Project's Agents are listed without the create form", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [hrHelper] });
  renderStudio(agentsTab(oldProject.id));

  expect(await screen.findByRole("link", { name: "HR helper" }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.queryByRole("form", { name: "New Agent" })).not.toBeInTheDocument();
});

test("Agents that can't be loaded say so", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  server.use(http.get("*/api/organisations/:organisationId/projects/:projectId/agents", () => HttpResponse.json({ detail: "Not found" }, { status: 404 })));
  renderStudio(agentsTab(hrProject.id));

  expect(await screen.findByText("The Agents could not be loaded. Try again shortly.", {}, { timeout: 5000 })).toBeInTheDocument();
});

// Multi-select bulk revert

const liveHelper = { ...hrHelper, live_version: { id: "a2e00000-0000-4000-8000-000000000103", number: 3 } };
const benefits = { ...hrHelper, id: "a9e00000-0000-4000-8000-000000000002", name: "Benefits FAQ", live_version: { id: "a2e00000-0000-4000-8000-000000000201", number: 1 } };
const rollout = { current_version: null, behind: 0, agents: [rolloutAgent(1, "HR helper", 3, null), rolloutAgent(2, "Benefits FAQ", 1, null)] };

test("an Editor selects several Agents and reverts them together after confirming", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [liveHelper, benefits] });
  const { requests } = fakeBulkApi({ rollout });
  renderStudio(agentsTab(hrProject.id));

  const revertSelected = await screen.findByRole("button", { name: "Revert selected (0)" }, { timeout: 5000 });
  expect(revertSelected).toBeDisabled();
  await userEvent.click(screen.getByRole("checkbox", { name: "Select HR helper" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "Select Benefits FAQ" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "Select Benefits FAQ" }));
  await userEvent.click(screen.getByRole("button", { name: "Revert selected (1)" }));
  expect(screen.getByRole("group", { name: "Bulk actions" })).toHaveTextContent(
    "Revert 1 Agent? Each one's Live Version moves back one step in its Live History. Drafts aren't changed.",
  );
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(requests).toEqual([]);

  await userEvent.click(screen.getByRole("checkbox", { name: "Select Benefits FAQ" }));
  await userEvent.click(screen.getByRole("button", { name: "Revert selected (2)" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, revert 2 Agents" }));

  expect(requests).toEqual([{ route: "bulk-revert", body: { agent_ids: [liveHelper.id, benefits.id] } }]);
  const results = await screen.findByRole("list", { name: "Results" });
  expect(within(results).getAllByRole("listitem").map((row) => row.textContent)).toEqual([
    "HR helper — Done: Reverted to v2 without Project Instructions. It is now Live.",
    `Benefits FAQ — Skipped: ${NOTHING_TO_REVERT}`,
  ]);
  // The selection is cleared once it's done.
  expect(screen.getByRole("checkbox", { name: "Select HR helper" })).not.toBeChecked();
  expect(screen.getByRole("button", { name: "Revert selected (0)" })).toBeDisabled();
});

test("a bulk revert refused as a whole says why", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [liveHelper] });
  server.use(
    http.post("*/api/organisations/:organisationId/projects/:projectId/agents/bulk-revert", async () => {
      await delay(100);
      return HttpResponse.json({ detail: "This Project is archived. An Owner can restore it." }, { status: 409 });
    }),
  );
  renderStudio(agentsTab(hrProject.id));

  await userEvent.click(await screen.findByRole("checkbox", { name: "Select HR helper" }, { timeout: 5000 }));
  await userEvent.click(screen.getByRole("button", { name: "Revert selected (1)" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, revert 1 Agent" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("This Project is archived. An Owner can restore it.");
  expect(screen.getByRole("checkbox", { name: "Select HR helper" })).toBeChecked();
});

test("archived Agents and an archived Project's Agents can't be selected", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [liveHelper, oldHelper] });
  const { unmount } = renderStudio(agentsTab(oldProject.id));
  expect(await screen.findByRole("link", { name: "HR helper" }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  unmount();

  renderStudio(agentsTab(hrProject.id));
  await userEvent.click(await screen.findByRole("button", { name: "Show archived Agents" }, { timeout: 5000 }));
  expect(await screen.findByRole("link", { name: "Old helper" })).toBeInTheDocument();
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
});

test("an Agent whose Token Budget is spent shows an alert badge in the list and on its page", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const spent = { ...hrHelper, budget_exhausted: true };
  const other = { ...hrHelper, id: "a9e00000-0000-4000-8000-000000000002", name: "Benefits FAQ" };
  fakeAgentsApi({ agents: [spent, other] });
  renderStudio(agentsTab(hrProject.id));

  const list = await screen.findByRole("list", { name: "Agents" }, { timeout: 5000 });
  const [first, second] = within(list).getAllByRole("listitem");
  expect(within(first as HTMLElement).getByText("Budget spent")).toHaveAttribute(
    "title",
    "Today's Token Budget is spent, so Visitors see the unavailable text until midnight UTC.",
  );
  expect(within(second as HTMLElement).queryByText("Budget spent")).not.toBeInTheDocument();

  await userEvent.click(within(list).getByRole("link", { name: "HR helper" }));

  expect(await screen.findByRole("heading", { level: 2, name: "HR helper" }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.getByText("Budget spent")).toBeInTheDocument();
});

test("an Agent whose Guardrail block rate spiked shows an alert badge in the list and on its page", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const attacked = { ...hrHelper, block_rate_alert: true };
  const other = { ...hrHelper, id: "a9e00000-0000-4000-8000-000000000002", name: "Benefits FAQ" };
  fakeAgentsApi({ agents: [attacked, other] });
  renderStudio(agentsTab(hrProject.id));

  const list = await screen.findByRole("list", { name: "Agents" }, { timeout: 5000 });
  const [first, second] = within(list).getAllByRole("listitem");
  expect(within(first as HTMLElement).getByText("Block rate spike")).toHaveAttribute(
    "title",
    "In the last hour, the input Guardrail blocked an unusual share of Visitor messages, as in an attack. Review the blocked Conversations.",
  );
  expect(within(second as HTMLElement).queryByText("Block rate spike")).not.toBeInTheDocument();

  await userEvent.click(within(list).getByRole("link", { name: "HR helper" }));

  expect(await screen.findByRole("heading", { level: 2, name: "HR helper" }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.getByText("Block rate spike")).toBeInTheDocument();
});
