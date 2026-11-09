import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { fakeAgentsApi, hrHelper, oldHelper } from "../test/agents";
import { adaSession, fakeAuthApi, type Session } from "../test/auth";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const agentsTab = `/organisations/${organisationId}/projects/${hrProject.id}/agents`;
const agentPage = (agentId: string) => `${agentsTab}/${agentId}`;
const editorSession: Session = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};
const AGENT_ARCHIVED = "This Agent is archived. An Owner can restore it.";

function setUp(session: Session = adaSession, options: Parameters<typeof fakeAgentsApi>[0] = {}) {
  fakeAuthApi({ signedInAs: session });
  fakeProjectsApi();
  return fakeAgentsApi({ agents: [hrHelper, oldHelper], ...options });
}

test("archived Agents are left out of the Agents list and shown on request", async () => {
  setUp(editorSession);
  renderStudio(agentsTab);

  const active = await screen.findByRole("table", { name: "Agents" }, { timeout: 5000 });
  expect(within(active).getAllByRole("link").map((link) => link.textContent)).toEqual(["HR helper"]);

  await userEvent.click(screen.getByRole("radio", { name: "Archived" }));

  const archived = await screen.findByRole("table", { name: "Archived Agents" });
  expect(within(archived).getAllByRole("link").map((link) => link.textContent)).toEqual(["Old helper"]);
  expect(within(archived).getByRole("cell", { name: "2026-11-06" })).toBeInTheDocument();
  expect(screen.getByText(/Only Owners can restore or delete them/)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("radio", { name: "Active" }));
  expect(await screen.findByRole("table", { name: "Agents" })).toBeInTheDocument();
});

test("a Project with no archived Agents says so", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [hrHelper] });
  renderStudio(agentsTab);

  await userEvent.click(await screen.findByRole("radio", { name: "Archived" }, { timeout: 5000 }));

  expect(await screen.findByRole("heading", { name: "No archived Agents" })).toBeInTheDocument();
  expect(screen.getByText(/Open one to restore it or delete it permanently/)).toBeInTheDocument();
});

test("an Editor archives an Agent after confirming; its page turns read-only without the Playground", async () => {
  const { requests } = setUp(editorSession);
  renderStudio(agentPage(hrHelper.id));

  await userEvent.click(await screen.findByRole("button", { name: "Archive Agent" }, { timeout: 5000 }));
  expect(screen.getByText(/HR helper will be hidden from the Agents list/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(requests).toEqual([]);
  await userEvent.click(screen.getByRole("button", { name: "Archive Agent" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, archive HR helper" }));

  const notice = await screen.findByRole("status", { name: "Archived" });
  expect(notice).toHaveTextContent("This Agent is archived. It is hidden from the Agents list and the Playground is off. Only Owners can restore it.");
  expect(within(notice).queryByRole("button")).not.toBeInTheDocument();
  expect(requests).toEqual([{ route: "archive" }]);
  expect(screen.queryByRole("heading", { name: "Playground" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Chunks per answer (top-k)")).toBeDisabled();
  expect(screen.getByRole("textbox", { name: "System prompt" })).toHaveAttribute("contenteditable", "false");
  expect(screen.getByRole("status", { name: "Draft status" })).toHaveTextContent("Read only while archived.");
});

test("a refused archive shows why", async () => {
  setUp(adaSession, { refuse: { archive: "This Project is archived. An Owner can restore it." } });
  renderStudio(agentPage(hrHelper.id));

  await userEvent.click(await screen.findByRole("button", { name: "Archive Agent" }, { timeout: 5000 }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, archive HR helper" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("This Project is archived. An Owner can restore it.");
  expect(screen.getByRole("button", { name: "Archive Agent" })).toBeInTheDocument();
});

test("an Owner restores an archived Agent and the Playground returns", async () => {
  const { requests } = setUp();
  renderStudio(agentPage(oldHelper.id));

  const notice = await screen.findByRole("status", { name: "Archived" }, { timeout: 5000 });
  expect(notice).toHaveTextContent("Restore it to use it again.");
  await userEvent.click(within(notice).getByRole("button", { name: "Restore Old helper" }));

  expect(await screen.findByRole("heading", { name: "Playground" })).toBeInTheDocument();
  expect(screen.queryByRole("status", { name: "Archived" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Archive Agent" })).toBeInTheDocument();
  expect(requests).toEqual([{ route: "restore" }]);
});

test("a refused restore shows why", async () => {
  setUp(adaSession, { refuse: { restore: "This Agent isn't archived." } });
  renderStudio(agentPage(oldHelper.id));

  const notice = await screen.findByRole("status", { name: "Archived" }, { timeout: 5000 });
  await userEvent.click(within(notice).getByRole("button", { name: "Restore Old helper" }));

  expect(await within(notice).findByRole("alert")).toHaveTextContent("This Agent isn't archived.");
});

test("an Owner deletes an archived Agent permanently after typing its name", async () => {
  const { requests } = setUp();
  renderStudio(agentPage(oldHelper.id));

  await userEvent.click(await screen.findByRole("button", { name: "Delete permanently" }, { timeout: 5000 }));
  const form = screen.getByRole("form", { name: "Delete Old helper permanently" });
  expect(form).toHaveTextContent("removes its Draft and Conversations for good");
  const submit = within(form).getByRole("button", { name: "Delete Old helper permanently" });
  expect(submit).toBeDisabled();
  await userEvent.type(within(form).getByLabelText("Type Old helper to confirm"), "old helper");
  expect(submit).toBeDisabled();
  await userEvent.clear(within(form).getByLabelText("Type Old helper to confirm"));
  await userEvent.type(within(form).getByLabelText("Type Old helper to confirm"), "Old helper");
  await userEvent.click(submit);

  expect(await screen.findByText("Old helper was deleted permanently.")).toBeInTheDocument();
  expect(requests).toEqual([{ route: "delete", body: { confirm_name: "Old helper" } }]);
  const active = await screen.findByRole("table", { name: "Agents" }, { timeout: 5000 });
  expect(within(active).getAllByRole("link").map((link) => link.textContent)).toEqual(["HR helper"]);
});

test("deleting can be cancelled, and a refusal shows why", async () => {
  setUp();
  // Restored elsewhere since the page loaded: the API refuses the deletion.
  server.use(
    http.delete("*/api/organisations/:organisationId/projects/:projectId/agents/:agentId", () =>
      HttpResponse.json({ detail: "Only an archived Agent can be deleted. Archive it first." }, { status: 409 }),
    ),
  );
  renderStudio(agentPage(oldHelper.id));

  await userEvent.click(await screen.findByRole("button", { name: "Delete permanently" }, { timeout: 5000 }));
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("form", { name: "Delete Old helper permanently" })).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Delete permanently" }));
  const form = screen.getByRole("form", { name: "Delete Old helper permanently" });
  await userEvent.type(within(form).getByLabelText("Type Old helper to confirm"), "Old helper");
  // Submitting by Enter works too.
  await userEvent.keyboard("{Enter}");

  expect(await within(form).findByRole("alert")).toHaveTextContent("Only an archived Agent can be deleted. Archive it first.");
});

test("Editors see no restore or delete on an archived Agent", async () => {
  setUp(editorSession);
  renderStudio(agentPage(oldHelper.id));

  const notice = await screen.findByRole("status", { name: "Archived" }, { timeout: 5000 });
  expect(within(notice).queryByRole("button")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Archive Agent" })).not.toBeInTheDocument();
});

test("a Playground refused because the Agent was archived elsewhere says so", async () => {
  setUp(adaSession, { startStatus: 409, startDetail: AGENT_ARCHIVED });
  renderStudio(agentPage(hrHelper.id));

  await userEvent.type(await screen.findByLabelText("Question", {}, { timeout: 5000 }), "How much leave?");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(AGENT_ARCHIVED);
});
