import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { currentSection, hasMenu, menuButton, openSection, sectionNames } from "../test/navigation";
import { fakeInvitesApi } from "../test/invites";
import { fakeMembersApi } from "../test/members";
import { fakeProjectsApi, hrProject, oldProject, salesProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";

test("a visitor who is not signed in is sent to sign in", async () => {
  renderStudio("/");

  expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
});

test("signed-out visitors cannot open an Organisation page directly", async () => {
  renderStudio(`/organisations/${organisationId}/settings`);

  expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
});

test("one top bar holds the mark, the breadcrumb, the Appearance toggle and the account menu; there is no side menu", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  const bar = within(screen.getByRole("banner"));
  expect(bar.getByRole("link", { name: "Studio home" })).toHaveAttribute("href", "/");
  expect(bar.getByRole("navigation", { name: "Breadcrumb" })).toBeInTheDocument();
  expect(bar.getByRole("button", { name: "Switch to dark mode" })).toBeInTheDocument();
  expect(bar.getByRole("button", { name: "Ada Lovelace, Account" })).toBeInTheDocument();
  expect(screen.queryByRole("navigation", { name: "Organisation" })).not.toBeInTheDocument();
});

test("the section switcher offers the Organisation's sections as links and opens them", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");
  expect(await screen.findByText(/No Projects yet/)).toBeInTheDocument();

  expect(await sectionNames("Organisation sections")).toEqual(["Projects", "Cost", "Settings", "Security", "Profile"]);
  await userEvent.click(await menuButton("Organisation sections"));
  const sections = within(screen.getByRole("menu", { name: "Organisation sections" }));
  expect(sections.getByRole("menuitem", { name: "Settings" })).toHaveAttribute(
    "href",
    `/organisations/${organisationId}/settings`,
  );
  expect(sections.getByRole("menuitem", { name: "Projects" })).toHaveAttribute("aria-current", "page");
  await userEvent.keyboard("{Escape}");

  await openSection("Organisation sections", "Settings");

  expect(await screen.findByRole("heading", { name: "Organisation settings" })).toBeInTheDocument();
  await openSection("Organisation sections", "Projects");
  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
});

test("the breadcrumb follows the route and marks the current page", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(`/organisations/${organisationId}/projects`);
  const breadcrumb = () => within(screen.getByRole("navigation", { name: "Breadcrumb" }));

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  expect(breadcrumb().getByText("Analytical Engines")).not.toHaveAttribute("aria-current");
  expect(breadcrumb().getByRole("button", { name: "Projects, Organisation sections" })).toHaveAttribute("aria-current", "page");

  await userEvent.click(await screen.findByRole("link", { name: "HR handbook" }));

  expect(await breadcrumb().findByRole("button", { name: "Documents, Project sections" })).toHaveAttribute("aria-current", "page");
  expect(breadcrumb().getByRole("button", { name: "HR handbook, Projects" })).not.toHaveAttribute("aria-current");
  expect(breadcrumb().getByRole("button", { name: "Projects, Organisation sections" })).not.toHaveAttribute("aria-current");

  await openSection("Organisation sections", "Security");
  expect(await screen.findByRole("heading", { name: "Security", level: 1 })).toBeInTheDocument();
  expect(breadcrumb().getByRole("button", { name: "Security, Organisation sections" })).toHaveAttribute("aria-current", "page");
});

test("Organisation settings are a Settings switcher crumb: the area is the current crumb, its siblings are links", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeMembersApi();
  fakeInvitesApi();
  renderStudio(`/organisations/${organisationId}/settings`);
  const breadcrumb = () => within(screen.getByRole("navigation", { name: "Breadcrumb" }));

  expect(await screen.findByRole("heading", { name: "Organisation settings", level: 1 })).toBeInTheDocument();
  expect(screen.queryByRole("navigation", { name: "Organisation settings" })).not.toBeInTheDocument();
  expect(breadcrumb().getByRole("button", { name: "Settings, Organisation sections" })).not.toHaveAttribute("aria-current");
  expect(breadcrumb().getByRole("button", { name: "General, Organisation settings" })).toHaveAttribute("aria-current", "page");

  expect(await sectionNames("Organisation settings")).toEqual(["General", "Credentials", "Models", "Theme", "Members", "Audit"]);
  await userEvent.click(await menuButton("Organisation settings"));
  const menu = within(screen.getByRole("menu", { name: "Organisation settings" }));
  expect(menu.getByRole("menuitem", { name: "Members" })).toHaveAttribute("href", `/organisations/${organisationId}/settings/members`);
  expect(menu.getByRole("menuitem", { name: "General" })).toHaveAttribute("aria-current", "page");
  await userEvent.keyboard("{Escape}");

  await openSection("Organisation settings", "Members");

  expect(await screen.findByRole("table", { name: "Members" })).toBeInTheDocument();
  expect(await currentSection("Organisation settings")).toBe("Members");
  expect(breadcrumb().getByRole("button", { name: "Members, Organisation settings" })).toHaveAttribute("aria-current", "page");
});

test("an Editor's Settings crumb leaves out Members and Audit", async () => {
  fakeAuthApi({
    signedInAs: { ...adaSession, organisations: adaSession.organisations.map((o) => ({ ...o, role: "editor" as const })) },
  });
  renderStudio(`/organisations/${organisationId}/settings/theme`);

  expect(await currentSection("Organisation settings")).toBe("Theme");
  expect(await sectionNames("Organisation settings")).toEqual(["General", "Credentials", "Models", "Theme"]);
});

test("an unknown settings address says so in the Settings crumb, which still offers every area", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(`/organisations/${organisationId}/settings/bogus`);

  expect(await currentSection("Organisation settings")).toBe("Not found");
  expect(await sectionNames("Organisation settings")).toEqual(["General", "Credentials", "Models", "Theme", "Members", "Audit"]);
});

const projectPage = (projectId: string, section = "") => `/organisations/${organisationId}/projects/${projectId}${section}`;

test("inside a Project the breadcrumb is the Organisation's sections, a Project switcher and a section switcher", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage(hrProject.id));
  const breadcrumb = within(await screen.findByRole("navigation", { name: "Breadcrumb" }));

  expect(await breadcrumb.findByRole("button", { name: "HR handbook, Projects" })).toBeInTheDocument();
  expect(breadcrumb.getAllByRole("listitem").map((crumb) => crumb.textContent)).toEqual([
    "Analytical Engines",
    "/Projects",
    "/HR handbook",
    "/Documents",
  ]);
  // The Organisation's sections stay one click away from any Project.
  expect(await sectionNames("Organisation sections")).toEqual(["Projects", "Cost", "Settings", "Security", "Profile"]);
});

test("the Project switcher lists the open Projects as links, plus All Projects", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage(hrProject.id, "/agents"));
  await screen.findByRole("button", { name: "HR handbook, Projects" });

  // Archived Projects are not offered: they are opened from the Projects list.
  expect(await sectionNames("Projects")).toEqual(["HR handbook", "Sales enablement", "All Projects"]);
  await userEvent.click(await menuButton("Projects"));
  const projects = within(screen.getByRole("menu", { name: "Projects" }));
  expect(projects.getByRole("menuitem", { name: "HR handbook" })).toHaveAttribute("aria-current", "page");
  expect(projects.getByRole("menuitem", { name: "Sales enablement" })).toHaveAttribute("href", projectPage(salesProject.id));
  expect(projects.getByRole("menuitem", { name: "Sales enablement" })).not.toHaveAttribute("aria-current");
  expect(projects.getByRole("menuitem", { name: "All Projects" })).toHaveAttribute("href", `/organisations/${organisationId}/projects`);
  await userEvent.keyboard("{Escape}");

  await openSection("Projects", "Sales enablement");
  expect(await screen.findByRole("heading", { level: 1, name: "Sales enablement" })).toBeInTheDocument();
  expect(await currentSection("Project sections")).toBe("Documents");

  await openSection("Projects", "All Projects");
  expect(await screen.findByRole("table", { name: "Projects" })).toBeInTheDocument();
  expect(hasMenu("Project sections")).toBe(false);
});

test("the section switcher lists the Project's sections with icons and number hints, as links", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage(hrProject.id));
  await screen.findByRole("button", { name: "Documents, Project sections" });

  await userEvent.click(await menuButton("Project sections"));
  const menu = within(screen.getByRole("menu", { name: "Project sections" }));
  const sections = ["Documents", "Instructions", "Agents", "Conversations", "Analytics", "Settings"];
  const paths = ["", "/instructions", "/agents", "/conversations", "/analytics", "/settings"];
  sections.forEach((section, index) => {
    const item = menu.getByRole("menuitem", { name: section });
    expect(item).toHaveAttribute("href", projectPage(hrProject.id, paths[index]));
    // The number hint is a visual label: it is not part of the item's name.
    expect(within(item).getByText(String(index + 1))).toHaveAttribute("aria-hidden", "true");
    expect(item.querySelector("svg")).not.toBeNull();
  });
  expect(menu.getByRole("menuitem", { name: "Documents" })).toHaveAttribute("aria-current", "page");
  await userEvent.keyboard("{Escape}");

  await openSection("Project sections", "Conversations");
  expect(await screen.findByRole("heading", { level: 2, name: "Conversations" })).toBeInTheDocument();
  expect(await currentSection("Project sections")).toBe("Conversations");
});

test("a section's inner pages keep their section current", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage(hrProject.id, "/documents/0e8f6a52-7d2b-4c8e-9f1a-3b5c7d9e1f20"));

  expect(await screen.findByRole("button", { name: "Documents, Project sections" })).toHaveAttribute("aria-current", "page");
});

test("an archived Project still has its switchers; the Project switcher offers the open Projects", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage(oldProject.id, "/settings"));

  expect(await screen.findByRole("button", { name: "Settings, Project sections" })).toHaveAttribute("aria-current", "page");
  expect(await sectionNames("Projects")).toEqual(["HR handbook", "Sales enablement", "All Projects"]);
});

test("a Project that can't be loaded keeps the Project switcher as the current crumb, with no sections", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage("00000000-0000-4000-8000-000000000000"));

  expect(await screen.findByRole("heading", { name: "Project not found" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Project, Projects" })).toHaveAttribute("aria-current", "page");
  expect(hasMenu("Project sections")).toBe(false);
});

test("the account menu opens the Profile and Security, which are then the current section", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });

  expect(await sectionNames("Account")).toEqual(["Profile", "Security", "Sign out"]);
  await openSection("Account", "Profile");

  expect(await screen.findByRole("heading", { name: "Profile" })).toBeInTheDocument();
  expect(await currentSection("Organisation sections")).toBe("Profile");
  expect(await menuButton("Organisation sections")).toHaveAttribute("aria-current", "page");

  await openSection("Account", "Security");

  expect(await screen.findByRole("heading", { name: "Security", level: 1 })).toBeInTheDocument();
  expect(await currentSection("Organisation sections")).toBe("Security");
});

test("the breadcrumb's section switcher reaches the Profile", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });

  await openSection("Organisation sections", "Profile");

  expect(await screen.findByRole("heading", { name: "Profile" })).toBeInTheDocument();
});

test("signing out ends the session and returns to sign-in", async () => {
  const { requests } = fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });

  await openSection("Account", "Sign out");

  expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  expect(requests).toEqual([{ route: "sign-out", body: null }]);
  // Coming back to the Studio no longer shows the shell.
  renderStudio("/");
  expect((await screen.findAllByRole("heading", { name: "Sign in" })).length).toBeGreaterThan(0);
});

test("says when signing out failed and stays signed in", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  server.use(http.post("*/api/auth/sign-out", () => new HttpResponse(null, { status: 500 })));
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });

  await openSection("Account", "Sign out");

  expect(await screen.findByRole("alert")).toHaveTextContent("Sign-out failed. Try again.");
  expect(screen.getByRole("heading", { name: "Projects" })).toBeInTheDocument();
});

test("the account menu can't sign out twice at once", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  server.use(http.post("*/api/auth/sign-out", () => delay("infinite")));
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });

  await openSection("Account", "Sign out");
  await userEvent.click(await menuButton("Account"));

  expect(screen.getByRole("menuitem", { name: "Sign out" })).toBeDisabled();
});

test("shows a loading state while the session is checked", async () => {
  server.use(http.get("*/api/auth/me", () => delay("infinite")));
  renderStudio("/");

  expect(await screen.findByRole("status", { name: "Loading the Studio" })).toHaveAttribute("aria-busy", "true");
});

test("says when the API cannot be reached", async () => {
  server.use(http.get("*/api/auth/me", () => new HttpResponse(null, { status: 500 })));
  renderStudio("/");

  expect(await screen.findByRole("alert")).toHaveTextContent("The Studio could not reach the API.");
});

test("tells a Member with no Organisation that they don't belong to one", async () => {
  fakeAuthApi({ signedInAs: { ...adaSession, organisations: [], active_organisation_id: null } });
  renderStudio("/");

  expect(await screen.findByRole("heading", { name: "You don't belong to any Organisation yet." })).toBeInTheDocument();
  expect(screen.getByText(/Ask an Owner to invite you/)).toBeInTheDocument();
});

test("an Organisation the Member doesn't belong to is not found", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/organisations/00000000-0000-4000-8000-000000000000/projects");

  expect(await screen.findByRole("heading", { name: "Organisation not found" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /, Organisation sections$/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /, Organisations$/ })).not.toBeInTheDocument();
  expect(await sectionNames("Account")).toEqual(["Sign out"]);

  await userEvent.click(screen.getByRole("link", { name: "Go to your Organisation" }));

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
});

test("the status page links back to the Studio", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/status");

  expect(screen.queryByRole("banner")).not.toBeInTheDocument();
  await userEvent.click(await screen.findByRole("link", { name: "Studio home" }));

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
});
