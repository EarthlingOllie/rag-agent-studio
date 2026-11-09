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

const liveHelper = { ...hrHelper, live_version: { id: "a2e00000-0000-4000-8000-000000000103", number: 3 } };
const benefits = {
  ...hrHelper,
  id: "a9e00000-0000-4000-8000-000000000002",
  name: "Benefits FAQ",
  live_version: { id: "a2e00000-0000-4000-8000-000000000201", number: 1 },
};

/** Each body row of a table, as the cells' text. */
function rows(table: HTMLElement): string[][] {
  return within(table)
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell").map((cell) => cell.textContent));
}

async function agentsTable(name = "Agents") {
  return screen.findByRole("table", { name }, { timeout: 5000 });
}

test("the Agents section is a table card of the Project's Agents, linking to each, with its Live state as badges", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const drafted = { ...liveHelper, has_unpublished_changes: true };
  const notLive = { ...hrHelper, id: "a9e00000-0000-4000-8000-000000000004", name: "Payroll" };
  fakeAgentsApi({ agents: [drafted, benefits, notLive] });
  renderStudio(agentsTab(hrProject.id));

  expect(await screen.findByRole("heading", { level: 2, name: "Agents" }, { timeout: 5000 })).toBeInTheDocument();
  const table = await agentsTable();
  expect(within(table).getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
    "",
    "Name",
    "Live",
    "Draft",
    "Alerts",
    "Draft saved",
  ]);
  expect(rows(table)).toEqual([
    ["", "HR helper", "Live v3", "Draft", "—", "2026-11-05"],
    ["", "Benefits FAQ", "Live v1", "—", "—", "2026-11-05"],
    ["", "Payroll", "Not live", "—", "—", "2026-11-05"],
  ]);
  expect(within(table).getByRole("link", { name: "HR helper" })).toHaveAttribute("href", `${agentsTab(hrProject.id)}/${hrHelper.id}`);
  // The Live Version reads in full; the Draft badge says what it means on hover.
  expect(within(table).getByLabelText("Version 3")).toHaveTextContent("v3");
  expect(within(table).getByText("Draft", { selector: "span" })).toHaveAttribute(
    "title",
    "Unpublished changes: the Draft differs from the Live Version.",
  );
});

test("New Agent opens from the primary button in the page header, and the new Agent's page opens", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const { requests } = fakeAgentsApi();
  renderStudio(agentsTab(hrProject.id));
  await screen.findByRole("heading", { level: 2, name: "No Agents yet" }, { timeout: 5000 });
  expect(screen.queryByRole("form", { name: "New Agent" })).not.toBeInTheDocument();

  const open = screen.getByRole("button", { name: "New Agent" });
  expect(open.className).toContain("bg-accent");
  await userEvent.click(open);
  const dialog = screen.getByRole("dialog", { name: "New Agent" });
  await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(open).toHaveFocus();

  await userEvent.click(open);
  const form = screen.getByRole("form", { name: "New Agent" });
  expect(within(form).getByLabelText("Name")).toHaveFocus();
  await userEvent.type(within(form).getByLabelText("Name"), "Helper{Enter}");

  expect(await screen.findByRole("heading", { level: 2, name: "Helper" }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "System prompt" })).toHaveTextContent("");
  expect(requests).toEqual([{ route: "create", body: { name: "Helper" } }]);
});

test("a refused Agent shows why in the New Agent dialog", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi();
  renderStudio(agentsTab(hrProject.id));

  await userEvent.click(await screen.findByRole("button", { name: "New Agent" }, { timeout: 5000 }));
  const form = screen.getByRole("form", { name: "New Agent" });
  await userEvent.type(within(form).getByLabelText("Name"), "A very long name");
  await userEvent.click(within(form).getByRole("button", { name: "Create Agent" }));

  expect(await within(form).findByRole("alert")).toHaveTextContent(/a name up to 200 characters/);
  expect(screen.getByRole("dialog", { name: "New Agent" })).toBeInTheDocument();
});

test("the empty states use EmptyState, pointing to New Agent", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [] });
  renderStudio(agentsTab(hrProject.id));

  expect(await screen.findByRole("heading", { level: 2, name: "No Agents yet" }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.getByText("Create one with New Agent to answer questions from this Project's Documents.")).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("radio", { name: "Archived" }));
  expect(await screen.findByRole("heading", { level: 2, name: "No archived Agents" })).toBeInTheDocument();
});

test("an archived Project's Agents are listed without New Agent or selection", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [liveHelper] });
  renderStudio(agentsTab(oldProject.id));

  const table = await agentsTable();
  expect(within(table).getByRole("link", { name: "HR helper" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "New Agent" })).not.toBeInTheDocument();
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  expect(within(table).getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
    "Name",
    "Live",
    "Draft",
    "Alerts",
    "Draft saved",
  ]);
});

test("Agents loading show a skeleton, and Agents that can't be loaded say so", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/agents", async () => {
      await delay(150);
      return HttpResponse.json({ detail: "Not found" }, { status: 404 });
    }),
  );
  renderStudio(agentsTab(hrProject.id));

  expect(await screen.findByRole("status", { name: "Loading Agents" }, { timeout: 5000 })).toBeInTheDocument();
  const error = await screen.findByRole("alert", {}, { timeout: 5000 });
  expect(within(error).getByRole("heading", { name: "The Agents could not be loaded" })).toBeInTheDocument();
  expect(error).toHaveTextContent("Try again shortly.");
});

test("archived Agents are behind the Archived filter, without selection", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [liveHelper, oldHelper] });
  renderStudio(agentsTab(hrProject.id));

  const filter = await screen.findByRole("radiogroup", { name: "Agents shown" }, { timeout: 5000 });
  expect(within(filter).getByRole("radio", { name: "Active" })).toBeChecked();
  expect(within(await agentsTable()).getAllByRole("link").map((link) => link.textContent)).toEqual(["HR helper"]);

  await userEvent.click(within(filter).getByRole("radio", { name: "Archived" }));
  const archived = await agentsTable("Archived Agents");
  expect(rows(archived)).toEqual([["Old helper", "Not live", "—", "—", "2026-11-06"]]);
  expect(within(archived).getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
    "Name",
    "Live",
    "Draft",
    "Alerts",
    "Archived",
  ]);
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  expect(screen.getByText(/Open one to restore it or delete it permanently/)).toBeInTheDocument();
  // New Agent stays in the header: a new Agent is active.
  expect(screen.getByRole("button", { name: "New Agent" })).toBeInTheDocument();

  await userEvent.click(within(filter).getByRole("radio", { name: "Active" }));
  expect(await agentsTable()).toBeInTheDocument();
});

// Bulk revert, through the bulk bar

const rollout = { current_version: null, behind: 0, agents: [rolloutAgent(1, "HR helper", 3, null), rolloutAgent(2, "Benefits FAQ", 1, null)] };

test("selecting Agents shows the bulk bar; Revert asks first, then reports each Agent's result", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [liveHelper, benefits] });
  const { requests } = fakeBulkApi({ rollout });
  renderStudio(agentsTab(hrProject.id));

  await agentsTable();
  expect(screen.queryByRole("toolbar", { name: "Bulk actions" })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("checkbox", { name: "Select HR helper" }));
  const bar = screen.getByRole("toolbar", { name: "Bulk actions" });
  expect(within(bar).getByRole("status")).toHaveTextContent("1 Agent selected");

  await userEvent.click(within(bar).getByRole("button", { name: "Revert" }));
  const confirm = screen.getByRole("alertdialog", { name: "Revert 1 Agent?" });
  expect(confirm).toHaveTextContent("Each one's Live Version moves back one step in its Live History. Drafts aren't changed.");
  await userEvent.click(within(confirm).getByRole("button", { name: "Cancel" }));
  expect(requests).toEqual([]);

  await userEvent.click(screen.getByRole("checkbox", { name: "Select Benefits FAQ" }));
  expect(within(bar).getByRole("status")).toHaveTextContent("2 Agents selected");
  await userEvent.click(within(bar).getByRole("button", { name: "Revert" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, revert 2 Agents" }));

  expect(requests).toEqual([{ route: "bulk-revert", body: { agent_ids: [liveHelper.id, benefits.id] } }]);
  const results = await screen.findByRole("list", { name: "Results" });
  expect(within(results).getAllByRole("listitem").map((row) => row.textContent)).toEqual([
    "HR helper — Done: Reverted to v2 without Project Instructions. It is now Live.",
    `Benefits FAQ — Skipped: ${NOTHING_TO_REVERT}`,
  ]);
  // The selection is cleared once it's done, and the bar goes with it.
  expect(screen.getByRole("checkbox", { name: "Select HR helper" })).not.toBeChecked();
  expect(screen.queryByRole("toolbar", { name: "Bulk actions" })).not.toBeInTheDocument();
});

test("Select all selects every Agent, and Clear selection or Escape clears it", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [liveHelper, benefits] });
  renderStudio(agentsTab(hrProject.id));

  await agentsTable();
  const all = screen.getByRole("checkbox", { name: "Select all Agents" });
  await userEvent.click(screen.getByRole("checkbox", { name: "Select Benefits FAQ" }));
  expect(all).toBePartiallyChecked();
  await userEvent.click(all);
  expect(all).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "Select HR helper" })).toBeChecked();
  expect(within(screen.getByRole("toolbar", { name: "Bulk actions" })).getByRole("status")).toHaveTextContent("2 Agents selected");

  await userEvent.click(screen.getByRole("button", { name: "Clear selection" }));
  expect(all).not.toBeChecked();
  expect(screen.queryByRole("toolbar", { name: "Bulk actions" })).not.toBeInTheDocument();

  await userEvent.click(all);
  await userEvent.click(screen.getByRole("checkbox", { name: "Select HR helper" }));
  expect(all).toBePartiallyChecked();
  expect(within(screen.getByRole("toolbar", { name: "Bulk actions" })).getByRole("status")).toHaveTextContent("1 Agent selected");
  await userEvent.click(all);
  await userEvent.click(all);
  expect(screen.getByRole("checkbox", { name: "Select HR helper" })).not.toBeChecked();

  await userEvent.click(all);
  within(screen.getByRole("toolbar", { name: "Bulk actions" })).getByRole("button", { name: "Revert" }).focus();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("toolbar", { name: "Bulk actions" })).not.toBeInTheDocument();
});

test("a bulk revert refused as a whole says why and keeps the selection", async () => {
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
  await userEvent.click(screen.getByRole("button", { name: "Revert" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, revert 1 Agent" }));
  expect(screen.getByRole("button", { name: "Yes, revert 1 Agent" })).toBeDisabled();

  expect(await screen.findByRole("alert")).toHaveTextContent("This Project is archived. An Owner can restore it.");
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: "Select HR helper" })).toBeChecked();
  // Trying again clears the old refusal.
  await userEvent.click(screen.getByRole("button", { name: "Revert" }));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("an Agent whose Token Budget is spent is badged in the list, and still on its page", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const spent = { ...hrHelper, budget_exhausted: true };
  const other = { ...hrHelper, id: "a9e00000-0000-4000-8000-000000000002", name: "Benefits FAQ" };
  fakeAgentsApi({ agents: [spent, other] });
  renderStudio(agentsTab(hrProject.id));

  const table = await agentsTable();
  const [first, second] = within(table).getAllByRole("row").slice(1) as [HTMLElement, HTMLElement];
  expect(within(first).getByText("Budget spent")).toHaveAttribute(
    "title",
    "Today's Token Budget is spent, so Visitors see the unavailable text until midnight UTC.",
  );
  expect(within(second).queryByText("Budget spent")).not.toBeInTheDocument();

  await userEvent.click(within(table).getByRole("link", { name: "HR helper" }));

  expect(await screen.findByRole("heading", { level: 2, name: "HR helper" }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.getByText("Budget exhausted")).toBeInTheDocument();
});

test("an Agent whose Guardrail block rate spiked is badged in the list, and still on its page", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const attacked = { ...hrHelper, block_rate_alert: true };
  const other = { ...hrHelper, id: "a9e00000-0000-4000-8000-000000000002", name: "Benefits FAQ" };
  fakeAgentsApi({ agents: [attacked, other] });
  renderStudio(agentsTab(hrProject.id));

  const table = await agentsTable();
  const [first, second] = within(table).getAllByRole("row").slice(1) as [HTMLElement, HTMLElement];
  expect(within(first).getByText("Blocked by guardrail")).toHaveAttribute(
    "title",
    "Block rate spike: in the last hour, the input Guardrail blocked an unusual share of Visitor messages, as in an attack. Review the blocked Conversations.",
  );
  expect(within(second).queryByText("Blocked by guardrail")).not.toBeInTheDocument();

  await userEvent.click(within(table).getByRole("link", { name: "HR helper" }));

  expect(await screen.findByRole("heading", { level: 2, name: "HR helper" }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.getByText("Block rate spike")).toBeInTheDocument();
});
