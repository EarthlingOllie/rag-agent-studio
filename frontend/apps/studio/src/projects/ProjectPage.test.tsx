import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi, type Session } from "../test/auth";
import { fakeProjectsApi, hrProject, NAME_MISMATCH, oldProject, PROJECT_ARCHIVED } from "../test/projects";
import { currentSection, hasMenu, openSection, sectionNames } from "../test/navigation";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const projectPage = (projectId: string, section = "") => `/organisations/${organisationId}/projects/${projectId}${section}`;
const editorSession: Session = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};

test("a Project page has a section for each area, each saying what it holds while it is empty", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  fakeProjectsApi();
  renderStudio(projectPage(hrProject.id));

  expect(await screen.findByRole("heading", { level: 1, name: "HR handbook" })).toBeInTheDocument();
  expect(screen.getByText("Policies for the HR Agent")).toBeInTheDocument();
  expect(await sectionNames("Project sections")).toEqual([
    "Documents",
    "Instructions",
    "Agents",
    "Conversations",
    "Analytics",
    "Settings",
  ]);
  // Documents is the first section.
  expect(screen.getByRole("heading", { level: 2, name: "Documents" })).toBeInTheDocument();
  expect(await currentSection("Project sections")).toBe("Documents");

  const placeholders: [string, RegExp][] = [
    ["Instructions", /the shared rules every Agent in this Project follows/],
    ["Agents", /No Agents yet/],
    ["Conversations", /No Conversations yet/],
    ["Analytics", /No Agents to measure yet/],
    ["Documents", /Upload files to build this Project's Knowledge Base/],
  ];
  for (const [tab, placeholder] of placeholders) {
    await openSection("Project sections", tab);
    expect(await screen.findByRole("heading", { level: 2, name: tab })).toBeInTheDocument();
    expect(screen.getByText(placeholder)).toBeInTheDocument();
    expect(await currentSection("Project sections")).toBe(tab);
  }
});

test("opening a Project from the list shows its page", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(`/organisations/${organisationId}/projects`);

  await userEvent.click(await screen.findByRole("link", { name: "HR handbook" }));

  expect(await screen.findByRole("heading", { level: 1, name: "HR handbook" })).toBeInTheDocument();
  expect(hasMenu("Project sections")).toBe(true);
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

/** The page header's ⋯ menu: what it offers, then closed again. */
async function projectActions(): Promise<string[]> {
  await userEvent.click(await screen.findByRole("button", { name: "More Project actions" }));
  const items = within(screen.getByRole("menu", { name: "Project actions" }))
    .getAllByRole("menuitem")
    .map((item) => item.textContent);
  await userEvent.keyboard("{Escape}");
  return items;
}

async function chooseProjectAction(action: string) {
  await userEvent.click(await screen.findByRole("button", { name: "More Project actions" }));
  await userEvent.click(within(screen.getByRole("menu", { name: "Project actions" })).getByRole("menuitem", { name: action }));
}

test("the Project frame has no tab row and no All Projects link: the breadcrumb does both", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage(hrProject.id));
  await screen.findByRole("heading", { level: 1, name: "HR handbook" });

  expect(screen.queryByRole("navigation", { name: "Project" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "All Projects" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Edit details" })).toBeInTheDocument();
});

test("archiving is in the ⋯ menu and asks first, then shows the Project as archived; Owners restore it", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const { requests } = fakeProjectsApi();
  renderStudio(projectPage(hrProject.id));

  // An active Project offers no permanent deletion.
  expect(await projectActions()).toEqual(["Archive"]);
  await chooseProjectAction("Archive");
  const dialog = screen.getByRole("alertdialog", { name: "Archive HR handbook?" });
  expect(dialog).toHaveAccessibleDescription(
    "HR handbook will be hidden from the Projects list and stop serving. An Owner can restore it.",
  );
  expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
  await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(requests).toEqual([]);
  await chooseProjectAction("Archive");
  await userEvent.click(screen.getByRole("button", { name: "Yes, archive HR handbook" }));

  // The Documents section's toasts have their own status region, so the notice is found by what it says.
  const notice = await waitFor(() => {
    const found = screen.getAllByRole("status").find((status) => status.textContent.includes("This Project is archived."));
    expect(found).toBeDefined();
    return found as HTMLElement;
  });
  expect(notice).toHaveTextContent("This Project is archived. It is hidden from the Projects list and doesn't serve.");
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Edit details" })).not.toBeInTheDocument();
  expect(await projectActions()).toEqual(["Delete permanently"]);

  await userEvent.click(within(notice).getByRole("button", { name: "Restore HR handbook" }));

  expect(await screen.findByRole("button", { name: "Edit details" })).toBeInTheDocument();
  expect(screen.queryByText(/This Project is archived/)).not.toBeInTheDocument();
  expect(await projectActions()).toEqual(["Archive"]);
  expect(requests).toEqual([
    { route: "archive", projectId: hrProject.id },
    { route: "restore", projectId: hrProject.id },
  ]);
  await openSection("Projects", "All Projects");
  expect(await screen.findByRole("link", { name: "HR handbook" })).toBeInTheDocument();
});

test("an Editor sees an archived Project but can't restore or delete it", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  fakeProjectsApi();
  renderStudio(projectPage(oldProject.id));

  const notice = (await screen.findByText(/This Project is archived/)).closest("[role=status]") as HTMLElement;

  expect(notice).toHaveTextContent("Only Owners can restore it.");
  expect(within(notice).queryByRole("button")).not.toBeInTheDocument();
  // Nothing is left for the ⋯ menu to offer.
  expect(screen.queryByRole("button", { name: "More Project actions" })).not.toBeInTheDocument();
  expect(hasMenu("Project sections")).toBe(true);
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
  await chooseProjectAction("Archive");
  await userEvent.click(screen.getByRole("button", { name: "Yes, archive HR handbook" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(PROJECT_ARCHIVED);
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(await projectActions()).toEqual(["Archive"]);
  // Asking again starts without the old error.
  await chooseProjectAction("Archive");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

  renderStudio(projectPage(oldProject.id));
  await userEvent.click(await screen.findByRole("button", { name: "Restore Old launch" }));
  expect(await screen.findByText("This Project isn't archived.")).toBeInTheDocument();
});

test("an Owner permanently deletes an archived Project from the ⋯ menu after typing its name", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const { requests } = fakeProjectsApi();
  renderStudio(projectPage(oldProject.id));

  await screen.findByText(/This Project is archived/);
  await chooseProjectAction("Delete permanently");
  const dialog = screen.getByRole("alertdialog", { name: "Delete Old launch permanently" });
  expect(dialog).toHaveAccessibleDescription(
    "Deleting Old launch removes its Documents, stored files, Agents and Conversations for good. This can't be undone.",
  );
  const confirm = within(dialog).getByRole("button", { name: "Delete Old launch permanently" });
  const typed = within(dialog).getByLabelText("Type Old launch to confirm");
  expect(typed).toHaveFocus();
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

test("typing the name and pressing Enter deletes, too", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const { requests } = fakeProjectsApi();
  renderStudio(projectPage(oldProject.id));

  await chooseProjectAction("Delete permanently");
  await userEvent.type(screen.getByLabelText("Type Old launch to confirm"), "Old{Enter}");
  expect(requests).toEqual([]);
  await userEvent.type(screen.getByLabelText("Type Old launch to confirm"), " launch{Enter}");

  expect(await screen.findByRole("heading", { level: 1, name: "Projects" })).toBeInTheDocument();
  expect(requests).toEqual([{ route: "delete", projectId: oldProject.id, body: { confirm_name: "Old launch" } }]);
});

test("deleting can be cancelled, and a refused deletion says why", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const { requests } = fakeProjectsApi();
  renderStudio(projectPage(oldProject.id));

  await chooseProjectAction("Delete permanently");
  await userEvent.type(screen.getByLabelText("Type Old launch to confirm"), "Old");
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("alertdialog", { name: "Delete Old launch permanently" })).not.toBeInTheDocument();
  expect(requests).toEqual([]);

  server.use(
    http.delete("*/api/organisations/:organisationId/projects/:projectId", () =>
      HttpResponse.json({ detail: NAME_MISMATCH }, { status: 400 }),
    ),
  );
  // The dialog starts empty again.
  await chooseProjectAction("Delete permanently");
  const typed = screen.getByLabelText("Type Old launch to confirm");
  expect(typed).toHaveValue("");
  await userEvent.type(typed, "Old launch");
  await userEvent.click(screen.getByRole("button", { name: "Delete Old launch permanently" }));

  const dialog = screen.getByRole("alertdialog", { name: "Delete Old launch permanently" });
  expect(await within(dialog).findByRole("alert")).toHaveTextContent(NAME_MISMATCH);
  expect(screen.getByRole("heading", { level: 1, name: "Old launch" })).toBeInTheDocument();
});

test("the Embedding Model is set in the Project's Settings section, not on every page", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage(hrProject.id));
  await screen.findByRole("heading", { level: 2, name: "Documents" });

  expect(screen.queryByRole("region", { name: "Embedding Model" })).not.toBeInTheDocument();
  await openSection("Project sections", "Settings");

  expect(await screen.findByRole("region", { name: "Embedding Model" })).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "OCR" })).toBeInTheDocument();
});

test("an archived Project's Settings section has no Embedding Model to change", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage(oldProject.id, "/settings"));

  expect(await screen.findByRole("region", { name: "OCR" })).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Embedding Model" })).not.toBeInTheDocument();
});

test("an unknown Project is not found", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage("00000000-0000-4000-8000-000000000000"));

  expect(await screen.findByRole("heading", { level: 1, name: "Project not found" })).toBeInTheDocument();
  expect(screen.getByText("It doesn't exist in this Organisation.")).toBeInTheDocument();
  expect(hasMenu("Project sections")).toBe(false);
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

  expect(await screen.findByRole("status", { name: "Loading the Project" })).toHaveAttribute("aria-busy", "true");
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("The Project could not be loaded");
  expect(alert).toHaveTextContent("Try again shortly.");
  expect(screen.queryByRole("status", { name: "Loading the Project" })).not.toBeInTheDocument();
});
