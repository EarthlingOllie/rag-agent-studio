import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi, type Session } from "../test/auth";
import { fakeProjectsApi, hrProject, NAME_MISMATCH, oldProject, PROJECT_ARCHIVED } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const projectPage = (projectId: string) => `/organisations/${organisationId}/projects/${projectId}`;
const editorSession: Session = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};

test("a Project page has a tab for each area, each saying what it holds while it is empty", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  fakeProjectsApi();
  renderStudio(projectPage(hrProject.id));

  expect(await screen.findByRole("heading", { level: 1, name: "HR handbook" })).toBeInTheDocument();
  expect(screen.getByText("Policies for the HR Agent")).toBeInTheDocument();
  const tabs = screen.getByRole("navigation", { name: "Project" });
  expect(within(tabs).getAllByRole("link").map((link) => link.textContent)).toEqual([
    "Documents",
    "Instructions",
    "Agents",
    "Conversations",
    "Analytics",
    "Settings",
  ]);
  // Documents is the first tab.
  expect(screen.getByRole("heading", { level: 2, name: "Documents" })).toBeInTheDocument();
  expect(within(tabs).getByRole("link", { name: "Documents" })).toHaveAttribute("aria-current", "page");

  const placeholders: [string, RegExp][] = [
    ["Instructions", /the shared rules every Agent in this Project follows/],
    ["Agents", /No Agents yet/],
    ["Conversations", /No Conversations yet/],
    ["Analytics", /No Agents to measure yet/],
    ["Documents", /No Documents yet\. Upload files/],
  ];
  for (const [tab, placeholder] of placeholders) {
    await userEvent.click(within(tabs).getByRole("link", { name: tab }));
    expect(await screen.findByRole("heading", { level: 2, name: tab })).toBeInTheDocument();
    expect(screen.getByText(placeholder)).toBeInTheDocument();
    expect(within(tabs).getByRole("link", { name: tab })).toHaveAttribute("aria-current", "page");
  }
});

test("opening a Project from the list shows its page", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(`/organisations/${organisationId}/projects`);

  await userEvent.click(await screen.findByRole("link", { name: "HR handbook" }));

  expect(await screen.findByRole("heading", { level: 1, name: "HR handbook" })).toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "Project" })).toBeInTheDocument();
});

test("an Editor renames a Project and edits its description", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  const { requests } = fakeProjectsApi();
  renderStudio(projectPage(hrProject.id));
  await userEvent.click(await screen.findByRole("button", { name: "Edit details" }));
  const form = screen.getByRole("form", { name: "Project details" });
  expect(within(form).getByLabelText("Name")).toHaveValue("HR handbook");

  await userEvent.clear(within(form).getByLabelText("Name"));
  await userEvent.type(within(form).getByLabelText("Name"), "People team");
  await userEvent.clear(within(form).getByLabelText("Description"));
  await userEvent.type(within(form).getByLabelText("Description"), "Policies and benefits");
  await userEvent.click(within(form).getByRole("button", { name: "Save" }));

  expect(await screen.findByRole("heading", { level: 1, name: "People team" })).toBeInTheDocument();
  expect(screen.getByText("Policies and benefits")).toBeInTheDocument();
  expect(screen.queryByRole("form", { name: "Project details" })).not.toBeInTheDocument();
  expect(requests).toEqual([
    { route: "update", projectId: hrProject.id, body: { name: "People team", description: "Policies and benefits" } },
  ]);
});

test("editing can be cancelled, and a failed save says why", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  server.use(
    http.patch("*/api/organisations/:organisationId/projects/:projectId", async () => {
      await delay(300);
      return HttpResponse.json({ detail: PROJECT_ARCHIVED }, { status: 409 });
    }),
  );
  renderStudio(projectPage(hrProject.id));
  await userEvent.click(await screen.findByRole("button", { name: "Edit details" }));
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("form", { name: "Project details" })).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Edit details" }));
  await userEvent.click(screen.getByRole("button", { name: "Save" }));

  expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();
  expect(await screen.findByRole("alert")).toHaveTextContent(PROJECT_ARCHIVED);
  expect(screen.getByRole("heading", { level: 1, name: "HR handbook" })).toBeInTheDocument();
});

test("archiving asks first, then shows the Project as archived; Owners restore it", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const { requests } = fakeProjectsApi();
  renderStudio(projectPage(hrProject.id));

  await userEvent.click(await screen.findByRole("button", { name: "Archive" }));
  expect(screen.getByText(/HR handbook will be hidden from the Projects list and stop serving/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(requests).toEqual([]);
  await userEvent.click(screen.getByRole("button", { name: "Archive" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, archive HR handbook" }));

  const notice = await screen.findByRole("status");
  expect(notice).toHaveTextContent("This Project is archived. It is hidden from the Projects list and doesn't serve.");
  expect(screen.queryByRole("button", { name: "Edit details" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Archive" })).not.toBeInTheDocument();

  await userEvent.click(within(notice).getByRole("button", { name: "Restore HR handbook" }));

  expect(await screen.findByRole("button", { name: "Archive" })).toBeInTheDocument();
  expect(screen.queryByText(/This Project is archived/)).not.toBeInTheDocument();
  expect(requests).toEqual([
    { route: "archive", projectId: hrProject.id },
    { route: "restore", projectId: hrProject.id },
  ]);
  await userEvent.click(screen.getByRole("link", { name: "All Projects" }));
  expect(await screen.findByRole("link", { name: "HR handbook" })).toBeInTheDocument();
});

test("an Editor sees an archived Project but can't restore it", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  fakeProjectsApi();
  renderStudio(projectPage(oldProject.id));

  const notice = (await screen.findByText(/This Project is archived/)).closest("[role=status]") as HTMLElement;

  expect(notice).toHaveTextContent("Only Owners can restore it.");
  expect(within(notice).queryByRole("button")).not.toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "Project" })).toBeInTheDocument();
});

test("a refused archive or restore shows the API's reason", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  server.use(
    http.post("*/api/organisations/:organisationId/projects/:projectId/archive", () =>
      HttpResponse.json({ detail: PROJECT_ARCHIVED }, { status: 409 }),
    ),
    http.post("*/api/organisations/:organisationId/projects/:projectId/restore", () =>
      HttpResponse.json({ detail: "This Project isn't archived." }, { status: 409 }),
    ),
  );
  renderStudio(projectPage(hrProject.id));
  await userEvent.click(await screen.findByRole("button", { name: "Archive" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, archive HR handbook" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(PROJECT_ARCHIVED);
  expect(screen.getByRole("button", { name: "Archive" })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("link", { name: "All Projects" }));
  await userEvent.click(await screen.findByRole("link", { name: "HR handbook" }));
  await screen.findByRole("heading", { level: 1, name: "HR handbook" });
  renderStudio(projectPage(oldProject.id));
  await userEvent.click(await screen.findByRole("button", { name: "Restore Old launch" }));
  expect(await screen.findByText("This Project isn't archived.")).toBeInTheDocument();
});

test("an Owner permanently deletes an archived Project after typing its name", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const { requests } = fakeProjectsApi();
  renderStudio(projectPage(oldProject.id));

  const notice = (await screen.findByText(/This Project is archived/)).closest("[role=status]") as HTMLElement;
  await userEvent.click(within(notice).getByRole("button", { name: "Delete permanently" }));
  const form = screen.getByRole("form", { name: "Delete Old launch permanently" });
  expect(form).toHaveTextContent(
    "Deleting Old launch removes its Documents, stored files, Agents and Conversations for good. This can't be undone.",
  );
  const confirm = within(form).getByRole("button", { name: "Delete Old launch permanently" });
  const typed = within(form).getByLabelText("Type Old launch to confirm");
  // Nothing happens until the name is typed exactly.
  expect(confirm).toBeDisabled();
  await userEvent.type(typed, "old launch");
  expect(confirm).toBeDisabled();
  await userEvent.clear(typed);
  await userEvent.type(typed, "Old launch");
  expect(confirm).toBeEnabled();

  await userEvent.click(confirm);

  // Back on the Projects list, where the Project is gone, archived or not.
  expect(await screen.findByRole("heading", { level: 1, name: "Projects" })).toBeInTheDocument();
  expect(await screen.findByText("Old launch is being deleted permanently.")).toHaveAttribute("role", "status");
  expect(requests).toEqual([{ route: "delete", projectId: oldProject.id, body: { confirm_name: "Old launch" } }]);
  await userEvent.click(screen.getByRole("button", { name: "Show archived Projects" }));
  expect(await screen.findByText("No archived Projects.")).toBeInTheDocument();
});

test("deleting can be cancelled, and a refused deletion says why", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const { requests } = fakeProjectsApi();
  renderStudio(projectPage(oldProject.id));

  await userEvent.click(await screen.findByRole("button", { name: "Delete permanently" }));
  await userEvent.type(screen.getByLabelText("Type Old launch to confirm"), "Old");
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("form", { name: "Delete Old launch permanently" })).not.toBeInTheDocument();
  expect(requests).toEqual([]);

  server.use(
    http.delete("*/api/organisations/:organisationId/projects/:projectId", () =>
      HttpResponse.json({ detail: NAME_MISMATCH }, { status: 400 }),
    ),
  );
  // The form starts empty again.
  await userEvent.click(screen.getByRole("button", { name: "Delete permanently" }));
  const typed = screen.getByLabelText("Type Old launch to confirm");
  expect(typed).toHaveValue("");
  await userEvent.type(typed, "Old launch");
  await userEvent.click(screen.getByRole("button", { name: "Delete Old launch permanently" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(NAME_MISMATCH);
  expect(screen.getByRole("heading", { level: 1, name: "Old launch" })).toBeInTheDocument();
});

test("only Owners are offered permanent deletion", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  fakeProjectsApi();
  renderStudio(projectPage(oldProject.id));

  await screen.findByText(/This Project is archived/);

  expect(screen.queryByRole("button", { name: "Delete permanently" })).not.toBeInTheDocument();
});

test("an active Project offers no permanent deletion", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage(hrProject.id));

  await screen.findByRole("button", { name: "Archive" });

  expect(screen.queryByRole("button", { name: "Delete permanently" })).not.toBeInTheDocument();
});

test("an unknown Project is not found", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage("00000000-0000-4000-8000-000000000000"));

  expect(await screen.findByRole("heading", { level: 1, name: "Project not found" })).toBeInTheDocument();
  expect(screen.queryByRole("navigation", { name: "Project" })).not.toBeInTheDocument();
});

test("a Project page shows its loading and error states", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId", async () => {
      await delay(50);
      return HttpResponse.json({ detail: "Boom" }, { status: 500 });
    }),
  );
  renderStudio(projectPage(hrProject.id));

  expect(await screen.findByText("Loading the Project…")).toBeInTheDocument();
  expect(await screen.findByText("The Project could not be loaded. Try again shortly.")).toBeInTheDocument();
});
