import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { fakeAgentsApi, hrHelper } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeProjectsApi, hrProject, oldProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const agentsTab = (projectId: string) =>
  `/organisations/${organisationId}/projects/${projectId}/agents`;

test("the Agents tab lists the Project's Agents, linking to each", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({
    agents: [
      hrHelper,
      {
        ...hrHelper,
        id: "a9e00000-0000-4000-8000-000000000002",
        name: "Benefits FAQ",
      },
    ],
  });
  renderStudio(agentsTab(hrProject.id));

  const list = await screen.findByRole("list", {}, { timeout: 5000 });
  expect(
    within(list)
      .getAllByRole("link")
      .map((link) => link.textContent),
  ).toEqual(["HR helper", "Benefits FAQ"]);
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
  expect(
    await screen.findByText(/No Agents yet/, {}, { timeout: 5000 }),
  ).toBeInTheDocument();

  const form = screen.getByRole("form", { name: "New Agent" });
  await userEvent.type(within(form).getByLabelText("Name"), "Helper");
  await userEvent.click(
    within(form).getByRole("button", { name: "Create Agent" }),
  );

  expect(
    await screen.findByRole(
      "heading",
      { level: 2, name: "Helper" },
      { timeout: 5000 },
    ),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("System prompt")).toHaveValue("");
  expect(requests).toEqual([{ route: "create", body: { name: "Helper" } }]);
});

test("a refused Agent shows why", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi();
  renderStudio(agentsTab(hrProject.id));

  const form = await screen.findByRole(
    "form",
    { name: "New Agent" },
    { timeout: 5000 },
  );
  await userEvent.type(within(form).getByLabelText("Name"), "A very long name");
  await userEvent.click(
    within(form).getByRole("button", { name: "Create Agent" }),
  );

  expect(await within(form).findByRole("alert")).toHaveTextContent(
    /a name up to 200 characters/,
  );
});

test("an archived Project's Agents are listed without the create form", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [hrHelper] });
  renderStudio(agentsTab(oldProject.id));

  expect(
    await screen.findByRole("link", { name: "HR helper" }, { timeout: 5000 }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("form", { name: "New Agent" }),
  ).not.toBeInTheDocument();
});

test("Agents that can't be loaded say so", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  server.use(
    http.get(
      "*/api/organisations/:organisationId/projects/:projectId/agents",
      () => HttpResponse.json({ detail: "Not found" }, { status: 404 }),
    ),
  );
  renderStudio(agentsTab(hrProject.id));

  expect(
    await screen.findByText(
      "The Agents could not be loaded. Try again shortly.",
      {},
      { timeout: 5000 },
    ),
  ).toBeInTheDocument();
});
