import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi, type Session } from "../test/auth";
import { fakeMfaApi } from "../test/mfa";
import { currentSection, hasMenu, menuButton, openSection, sectionNames, sidebar } from "../test/navigation";
import { adaInTwo, fakeSwitcherApi } from "../test/organisations";
import { fakeProjectsApi, hrProject, oldProject, salesProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const organisationPage = (page: string) => `/organisations/${organisationId}/${page}`;
const projectPage = (projectId: string, section = "") => `/organisations/${organisationId}/projects/${projectId}${section}`;
const AGENT_ID = "a1000000-0000-4000-8000-000000000001";
const CONVERSATION_ID = "c7000000-0000-4000-8000-000000000001";
const DOCUMENT_ID = "0e8f6a52-7d2b-4c8e-9f1a-3b5c7d9e1f20";

function as(role: "owner" | "editor", overrides: Partial<Session["organisations"][number]> = {}): Session {
  return { ...adaSession, organisations: adaSession.organisations.map((o) => ({ ...o, role, ...overrides })) };
}

test("the sidebar is a navigation landmark named Studio: the Organisation's name, then Projects, Cost and Settings", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");
  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();

  const nav = within(await sidebar());
  // A Member of one Organisation has nothing to switch to: its name is plain text.
  expect(nav.getByText("Analytical Engines")).toBeInTheDocument();
  expect(nav.queryByRole("button", { name: /, Organisations$/ })).not.toBeInTheDocument();
  expect(await sectionNames("Organisation sections")).toEqual(["Projects", "Cost", "Settings"]);
  const links = within(nav.getByRole("list", { name: "Organisation sections" }));
  expect(links.getByRole("link", { name: "Projects" })).toHaveAttribute("href", organisationPage("projects"));
  expect(links.getByRole("link", { name: "Cost" })).toHaveAttribute("href", organisationPage("cost"));
  expect(links.getByRole("link", { name: "Settings" })).toHaveAttribute("href", organisationPage("settings"));
  // Nothing beside a link looks like a shortcut.
  expect(links.getByRole("link", { name: "Projects" })).toHaveTextContent(/^Projects$/);
  // The current page's link is marked, and only it.
  expect(links.getByRole("link", { name: "Projects" })).toHaveAttribute("aria-current", "page");
  expect(links.getByRole("link", { name: "Cost" })).not.toHaveAttribute("aria-current");
  // Outside a Project there is no Project switcher or Project sections.
  expect(hasMenu("Projects")).toBe(false);
  expect(hasMenu("Project sections")).toBe(false);
});

test("following a sidebar link opens its page, which becomes the current link", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });

  await openSection("Organisation sections", "Settings");

  expect(await screen.findByRole("heading", { name: "Organisation settings", level: 1 })).toBeInTheDocument();
  expect(await currentSection("Organisation sections")).toBe("Settings");

  await openSection("Organisation sections", "Projects");
  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  expect(await currentSection("Organisation sections")).toBe("Projects");
});

test("Settings stays current on every Organisation settings page", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(organisationPage("settings/theme"));

  expect(await currentSection("Organisation sections")).toBe("Settings");
});

test("Cost is for Owners: an Editor's sidebar leaves it out", async () => {
  fakeAuthApi({ signedInAs: as("editor") });
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });

  expect(await sectionNames("Organisation sections")).toEqual(["Projects", "Settings"]);
});

test("an Owner's Cost link is current on the cost page", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(organisationPage("cost"));

  expect(await currentSection("Organisation sections")).toBe("Cost");
});

test("the Profile and Security pages are reached from the account menu; no sidebar link is current on them", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(organisationPage("profile"));
  expect(await screen.findByRole("heading", { name: "Profile" })).toBeInTheDocument();

  expect(await currentSection("Organisation sections")).toBe("");
});

test("a Member of several Organisations switches between them from the top of the sidebar", async () => {
  fakeSwitcherApi(adaInTwo());
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });

  expect(await menuButton("Organisations")).toHaveAccessibleName("Analytical Engines, Organisations");
  expect(await sectionNames("Organisations")).toEqual(["Analytical Engines", "Difference Engines"]);
  await openSection("Organisations", "Difference Engines");

  expect(await within(await sidebar()).findByRole("button", { name: "Difference Engines, Organisations" })).toBeInTheDocument();
});

test("inside a Project the sidebar adds the Project switcher and the Project's six sections", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage(hrProject.id));
  expect(await screen.findByRole("heading", { level: 1, name: "HR handbook" })).toBeInTheDocument();

  expect(await menuButton("Projects")).toHaveAccessibleName("HR handbook, Projects");
  // Open Projects only; archived ones are opened from the Projects list.
  expect(await sectionNames("Projects")).toEqual(["HR handbook", "Sales enablement", "All Projects"]);
  const sections = ["Documents", "Instructions", "Agents", "Conversations", "Analytics", "Settings"];
  const paths = ["", "/instructions", "/agents", "/conversations", "/analytics", "/settings"];
  expect(await sectionNames("Project sections")).toEqual(sections);
  const links = within(within(await sidebar()).getByRole("list", { name: "Project sections" }));
  sections.forEach((section, index) => {
    expect(links.getByRole("link", { name: section })).toHaveAttribute("href", projectPage(hrProject.id, paths[index]));
  });
  expect(await currentSection("Project sections")).toBe("Documents");
  // The Organisation's links stay one click away, none of them current inside a Project.
  expect(await sectionNames("Organisation sections")).toEqual(["Projects", "Cost", "Settings"]);
  expect(await currentSection("Organisation sections")).toBe("");

  await openSection("Project sections", "Conversations");
  expect(await screen.findByRole("heading", { level: 2, name: "Conversations" })).toBeInTheDocument();
  expect(await currentSection("Project sections")).toBe("Conversations");
});

test("the sidebar's Project switcher opens another Project, or All Projects", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage(hrProject.id, "/agents"));
  await screen.findByRole("heading", { level: 1, name: "HR handbook" });

  await userEvent.click(await menuButton("Projects"));
  const menu = within(screen.getByRole("menu", { name: "Projects" }));
  expect(menu.getByRole("menuitem", { name: "HR handbook" })).toHaveAttribute("aria-current", "page");
  expect(menu.getByRole("menuitem", { name: "Sales enablement" })).toHaveAttribute("href", projectPage(salesProject.id));
  expect(menu.getByRole("menuitem", { name: "All Projects" })).toHaveAttribute("href", organisationPage("projects"));
  await userEvent.click(menu.getByRole("menuitem", { name: "Sales enablement" }));

  expect(await screen.findByRole("heading", { level: 1, name: "Sales enablement" })).toBeInTheDocument();
  expect(await currentSection("Project sections")).toBe("Documents");

  await openSection("Projects", "All Projects");
  expect(await screen.findByRole("table", { name: "Projects" })).toBeInTheDocument();
  expect(hasMenu("Project sections")).toBe(false);
  expect(await currentSection("Organisation sections")).toBe("Projects");
});

test.each([
  ["the Document viewer", `/documents/${DOCUMENT_ID}`, "Documents"],
  ["an Agent", `/agents/${AGENT_ID}`, "Agents"],
  ["an Agent's view", `/agents/${AGENT_ID}/versions`, "Agents"],
  ["a Conversation", `/conversations/${CONVERSATION_ID}`, "Conversations"],
  ["Project Settings", "/settings", "Settings"],
])("a section stays current on its inner pages: %s", async (_, section, current) => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  server.use(http.get("*/api/organisations/:organisationId/projects/:projectId/*", () => HttpResponse.json({ detail: "Not found" }, { status: 404 })));
  renderStudio(projectPage(hrProject.id, section));

  expect(await currentSection("Project sections")).toBe(current);
  const links = within(within(await sidebar()).getByRole("list", { name: "Project sections" })).getAllByRole("link");
  expect(links.filter((link) => link.getAttribute("aria-current") === "page")).toHaveLength(1);
});

test("an archived Project keeps its sections and switcher", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage(oldProject.id, "/settings"));

  expect(await currentSection("Project sections")).toBe("Settings");
  expect(await menuButton("Projects")).toHaveAccessibleName("Old launch, Projects");
});

test("a Project that can't be loaded has a switcher but no sections", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage("00000000-0000-4000-8000-000000000000"));

  expect(await screen.findByRole("heading", { name: "Project not found" })).toBeInTheDocument();
  expect(await menuButton("Projects")).toHaveAccessibleName("Project, Projects");
  expect(hasMenu("Project sections")).toBe(false);
});

test("under the Require MFA policy the sidebar offers only Security until the Member enrols", async () => {
  fakeMfaApi();
  fakeAuthApi({ signedInAs: { ...as("owner", { mfa_required: true }), member: { ...adaSession.member, mfa_enabled: false } } });
  renderStudio(organisationPage("projects"));

  expect(await screen.findByRole("heading", { name: "Security", level: 1 })).toBeInTheDocument();
  expect(await sectionNames("Organisation sections")).toEqual(["Security"]);
  expect(await currentSection("Organisation sections")).toBe("Security");
  const link = within(within(await sidebar()).getByRole("list", { name: "Organisation sections" })).getByRole("link", { name: "Security" });
  expect(link).toHaveAttribute("href", organisationPage("security"));
});

test("an Organisation the Member doesn't belong to has no sections in the sidebar", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/organisations/00000000-0000-4000-8000-000000000000/projects");

  expect(await screen.findByRole("heading", { name: "Organisation not found" })).toBeInTheDocument();
  expect(await sidebar()).toBeInTheDocument();
  expect(hasMenu("Organisation sections")).toBe(false);
  expect(hasMenu("Organisations")).toBe(false);
});

test("the main content sits beside the sidebar, not inside it", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");
  const heading = await screen.findByRole("heading", { name: "Projects", level: 1 });

  const nav = await sidebar();
  const main = screen.getByRole("main");
  expect(main).toContainElement(heading);
  expect(main).not.toContainElement(nav);
  expect(nav).not.toContainElement(main);
});
