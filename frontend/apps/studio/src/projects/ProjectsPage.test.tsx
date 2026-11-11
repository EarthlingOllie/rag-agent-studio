import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi, type Session } from "../test/auth";
import {
  fakeProjectsApi,
  hrProject,
  oldProject,
  salesProject,
} from "../test/projects";
import { openSection } from "../test/navigation";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const projectsPage = `/organisations/${organisationId}/projects`;
const editorSession: Session = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({
    ...organisation,
    role: "editor" as const,
  })),
};

function rowTexts(table: HTMLElement) {
  return within(table)
    .getAllByRole("row")
    .slice(1)
    .map((row) =>
      within(row)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    );
}

/** Switches the "Projects shown" filter to Archived. */
async function showArchived() {
  const shown = await screen.findByRole("radiogroup", { name: "Projects shown" });
  await userEvent.click(within(shown).getByRole("radio", { name: "Archived" }));
}

test("Members see the active Projects with their Document and Agent counts", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectsPage);

  const table = await screen.findByRole("table", { name: "Projects" });
  expect(screen.getByRole("heading", { level: 1, name: "Projects" })).toBeInTheDocument();
  expect(
    screen.getByText("Each Project holds the Documents its Agents answer from."),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "New Project" })).toBeInTheDocument();
  const shown = screen.getByRole("radiogroup", { name: "Projects shown" });
  expect(
    within(shown)
      .getAllByRole("radio")
      .map((radio) => [radio.textContent, radio.getAttribute("aria-checked")]),
  ).toEqual([
    ["Active", "true"],
    ["Archived", "false"],
  ]);
  expect(
    screen.queryByRole("button", { name: "Show archived Projects" }),
  ).not.toBeInTheDocument();
  expect(
    within(table)
      .getAllByRole("columnheader")
      .map((header) => header.textContent),
  ).toEqual(["Name", "Description", "Documents", "Agents"]);

  expect(rowTexts(table)).toEqual([
    ["HR handbook", "Policies for the HR Agent", "12", "2"],
    ["Sales enablement", "", "0", "0"],
  ]);
  expect(
    within(table).getByRole("link", { name: "HR handbook" }),
  ).toHaveAttribute("href", `${projectsPage}/${hrProject.id}`);
});

test("an Organisation without Projects says so", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(projectsPage);

  expect(
    await screen.findByRole("heading", { name: "No Projects yet" }),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "Create one with New Project to start collecting knowledge for a purpose.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("table", { name: "Projects" }),
  ).not.toBeInTheDocument();
});

test("the Projects list shows its loading and error states", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  server.use(
    http.get("*/api/organisations/:organisationId/projects", async () => {
      await delay(50);
      return HttpResponse.json({ detail: "Boom" }, { status: 500 });
    }),
  );
  renderStudio(projectsPage);

  expect(
    await screen.findByRole("status", { name: "Loading Projects" }),
  ).toBeInTheDocument();
  const failure = await screen.findByRole("alert");
  expect(
    within(failure).getByRole("heading", {
      name: "The Projects could not be loaded",
    }),
  ).toBeInTheDocument();
  expect(failure).toHaveTextContent("Try again shortly.");
});

/** Opens the New Project dialog from the Projects page and returns it. */
async function openNewProject() {
  await userEvent.click(await screen.findByRole("button", { name: "New Project" }));
  return screen.getByRole("dialog", { name: "New Project" });
}

test("an Editor creates a Project in the New Project dialog and lands on its page", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  const { requests } = fakeProjectsApi();
  renderStudio(projectsPage);
  await screen.findByRole("table", { name: "Projects" });
  // No inline form: New Project is a button that opens the dialog.
  expect(screen.queryByRole("form", { name: "New Project" })).not.toBeInTheDocument();
  const dialog = await openNewProject();
  const form = within(dialog).getByRole("form", { name: "New Project" });
  expect(within(form).getByLabelText("Name")).toBeRequired();
  expect(within(form).getByLabelText("Name")).toHaveValue("");
  expect(within(form).getByLabelText("Name")).toHaveFocus();

  await userEvent.type(within(form).getByLabelText("Name"), "Product support");
  await userEvent.type(
    within(form).getByLabelText("Description"),
    "Answers for customers",
  );
  await userEvent.click(
    within(form).getByRole("button", { name: "Create Project" }),
  );

  expect(
    await screen.findByRole("heading", { level: 1, name: "Product support" }),
  ).toBeInTheDocument();
  expect(screen.getByText("Answers for customers")).toBeInTheDocument();
  expect(screen.queryByRole("dialog", { name: "New Project" })).not.toBeInTheDocument();
  expect(requests).toEqual([
    {
      route: "create",
      body: { name: "Product support", description: "Answers for customers" },
    },
  ]);
  await openSection("Projects", "All Projects");
  const table = await screen.findByRole("table", { name: "Projects" });
  expect(
    within(table).getByRole("link", { name: "Product support" }),
  ).toBeInTheDocument();
});

test("Cancel and Escape close the New Project dialog without creating anything, and focus returns to New Project", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const { requests } = fakeProjectsApi();
  renderStudio(projectsPage);

  let dialog = await openNewProject();
  await userEvent.type(within(dialog).getByLabelText("Name"), "Half typed");
  await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog", { name: "New Project" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "New Project" })).toHaveFocus();

  dialog = await openNewProject();
  expect(within(dialog).getByLabelText("Name")).toHaveValue("");
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog", { name: "New Project" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "New Project" })).toHaveFocus();
  expect(requests).toEqual([]);
});

test("New Project is not offered while archived Projects are shown", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectsPage);
  await screen.findByRole("button", { name: "New Project" });

  await showArchived();

  expect(screen.queryByRole("button", { name: "New Project" })).not.toBeInTheDocument();
});

test("a refused new Project says what to fix inside the dialog and keeps what was typed; other failures say to try again", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  let answer = 422;
  server.use(
    http.post("*/api/organisations/:organisationId/projects", async () => {
      if (answer === 422) {
        await delay(300);
        return HttpResponse.json(
          { detail: [{ loc: ["body", "name"], msg: "too long" }] },
          { status: 422 },
        );
      }
      // A refusal without a reason, and then a body that isn't JSON at all.
      return answer === 409
        ? HttpResponse.json({}, { status: 409 })
        : new HttpResponse("Bad gateway", { status: 502 });
    }),
  );
  renderStudio(projectsPage);
  const dialog = await openNewProject();
  await userEvent.type(within(dialog).getByLabelText("Name"), "x");
  await userEvent.type(within(dialog).getByLabelText("Description"), "kept");

  await userEvent.click(
    within(dialog).getByRole("button", { name: "Create Project" }),
  );

  expect(
    await within(dialog).findByRole("button", { name: "Creating…" }),
  ).toBeDisabled();
  expect(await within(dialog).findByRole("alert")).toHaveTextContent(
    "Give the Project a name of up to 200 characters, and a description of up to 2,000.",
  );
  expect(within(dialog).getByLabelText("Name")).toHaveValue("x");
  expect(within(dialog).getByLabelText("Description")).toHaveValue("kept");
  const tooLong =
    "Give the Project a name of up to 200 characters, and a description of up to 2,000.";
  // Each answer's message replaces the one before, so each wait sees the new one.
  for (const [next, message] of [
    [502, "Something went wrong. Try again."],
    [422, tooLong],
    [409, "Something went wrong. Try again."],
  ] as const) {
    answer = next;
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Create Project" }),
    );
    expect(await within(dialog).findByText(message)).toBeInTheDocument();
  }
});

test("archived Projects are listed apart, and Owners restore them to the main list", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const { requests } = fakeProjectsApi();
  renderStudio(projectsPage);
  await screen.findByRole("table", { name: "Projects" });

  await showArchived();

  const archived = await screen.findByRole("table", {
    name: "Archived Projects",
  });
  expect(
    screen.getByText(/Archived Projects are hidden from the Projects list/),
  ).toHaveTextContent("Restore one to bring it back.");
  expect(
    within(archived)
      .getAllByRole("columnheader")
      .map((header) => header.textContent),
  ).toEqual(["Name", "Archived", "Actions"]);
  expect(rowTexts(archived)).toEqual([["Old launch", "2026-10-20", "Restore"]]);
  await userEvent.click(
    within(archived).getByRole("button", { name: "Restore Old launch" }),
  );
  // A toast confirms it, and the Project leaves the archived list.
  expect(await screen.findByText("Old launch was restored.")).toHaveAttribute(
    "aria-live",
    "polite",
  );
  expect(
    await screen.findByRole("heading", { name: "No archived Projects" }),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "A Project you archive is kept here, with its Documents and Agents.",
    ),
  ).toBeInTheDocument();
  expect(requests).toEqual([{ route: "restore", projectId: oldProject.id }]);

  await userEvent.click(screen.getByRole("radio", { name: "Active" }));
  const table = await screen.findByRole("table", { name: "Projects" });
  expect(
    within(table)
      .getAllByRole("link")
      .map((link) => link.textContent),
  ).toEqual(["HR handbook", "Old launch", "Sales enablement"]);
});

test("Editors see archived Projects but can't restore them", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  fakeProjectsApi();
  renderStudio(projectsPage);
  await showArchived();

  const archived = await screen.findByRole("table", {
    name: "Archived Projects",
  });

  expect(
    within(archived).getByRole("link", { name: "Old launch" }),
  ).toBeInTheDocument();
  expect(within(archived).queryByRole("button")).not.toBeInTheDocument();
  expect(screen.getByText(/Only Owners can restore them/)).toHaveTextContent(
    "Archived Projects are hidden from the Projects list and don't serve. Only Owners can restore them.",
  );
});

test("a restore that never reaches the API says to try again", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi({ projects: [salesProject, oldProject] });
  server.use(
    // The request never reaches the API.
    http.post(
      "*/api/organisations/:organisationId/projects/:projectId/restore",
      () => HttpResponse.error(),
    ),
  );
  renderStudio(projectsPage);
  await showArchived();

  await userEvent.click(
    await screen.findByRole("button", { name: "Restore Old launch" }),
  );

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Something went wrong. Try again.",
  );
  expect(
    screen.getByRole("table", { name: "Archived Projects" }),
  ).toBeInTheDocument();
});

test("the archived list shows its loading and error states", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  server.use(
    http.get(
      "*/api/organisations/:organisationId/projects",
      async ({ request }) => {
        if (new URL(request.url).searchParams.get("archived") !== "true")
          return HttpResponse.json([]);
        await delay(50);
        return HttpResponse.json({ detail: "Boom" }, { status: 500 });
      },
    ),
  );
  renderStudio(projectsPage);

  await showArchived();

  expect(
    await screen.findByRole("status", { name: "Loading archived Projects" }),
  ).toBeInTheDocument();
  const failure = await screen.findByRole("alert");
  expect(
    within(failure).getByRole("heading", {
      name: "The archived Projects could not be loaded",
    }),
  ).toBeInTheDocument();
  expect(failure).toHaveTextContent("Try again shortly.");
});

test("the Projects page leaves button and field styling to the design system's recipes", async () => {
  const module: Record<string, unknown> = await import("./ProjectsPage");
  expect(Object.keys(module)).not.toContain("BUTTON");
  expect(Object.keys(module)).not.toContain("INPUT");
});
