import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { breadcrumb, currentSection, menuButton, openSection, sectionNames } from "../test/navigation";
import { fakeInvitesApi } from "../test/invites";
import { fakeMembersApi } from "../test/members";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const projectPage = (projectId: string, section = "") => `/organisations/${organisationId}/projects/${projectId}${section}`;

/** The top bar's breadcrumb: plain links that say where the Member is; the sidebar is the navigation. */
const breadcrumbNav = () => within(screen.getByRole("navigation", { name: "Breadcrumb" }));

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

test("the breadcrumb is a plain path of links with no menus; the current crumb is the page", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(`/organisations/${organisationId}/projects`);

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  expect(await breadcrumb()).toEqual({ crumbs: ["Projects"], current: "Projects" });
  expect(breadcrumbNav().getByRole("link", { name: "Projects" })).toHaveAttribute("href", `/organisations/${organisationId}/projects`);
  // No crumb opens a menu.
  expect(breadcrumbNav().queryAllByRole("button")).toEqual([]);

  await userEvent.click(await screen.findByRole("link", { name: "HR handbook" }));

  expect(await screen.findByRole("heading", { level: 1, name: "HR handbook" })).toBeInTheDocument();
  expect(await breadcrumb()).toEqual({ crumbs: ["HR handbook", "Documents"], current: "Documents" });
  expect(breadcrumbNav().getByRole("link", { name: "HR handbook" })).toHaveAttribute("href", projectPage(hrProject.id));
  expect(breadcrumbNav().getByRole("link", { name: "HR handbook" })).not.toHaveAttribute("aria-current");
  expect(breadcrumbNav().queryAllByRole("button")).toEqual([]);

  await openSection("Project sections", "Conversations");
  expect(await screen.findByRole("heading", { level: 2, name: "Conversations" })).toBeInTheDocument();
  expect(await breadcrumb()).toEqual({ crumbs: ["HR handbook", "Conversations"], current: "Conversations" });
  expect(breadcrumbNav().getByRole("link", { name: "Conversations" })).toHaveAttribute("href", projectPage(hrProject.id, "/conversations"));

  // Going back up a level is one click on a crumb.
  await userEvent.click(breadcrumbNav().getByRole("link", { name: "HR handbook" }));
  expect(await breadcrumb()).toEqual({ crumbs: ["HR handbook", "Documents"], current: "Documents" });
});

test("there is no fold: a long path keeps every crumb as a link, and nothing stands in for them", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/documents/:documentId", () =>
      HttpResponse.json({ detail: "Not found" }, { status: 404 }),
    ),
  );
  renderStudio(projectPage(hrProject.id, "/documents/0e8f6a52-7d2b-4c8e-9f1a-3b5c7d9e1f20"));

  // A Document that can't be loaded is still named by its crumb, as "Document".
  await waitFor(async () => {
    expect(await breadcrumb()).toEqual({ crumbs: ["HR handbook", "Documents", "Document"], current: "Document" });
  });
  expect(breadcrumbNav().getByRole("link", { name: "Documents" })).toHaveAttribute("href", projectPage(hrProject.id));
  expect(breadcrumbNav().getByRole("link", { name: "Documents" })).not.toHaveAttribute("aria-current");
  expect(screen.queryByRole("button", { name: "Show the whole path" })).not.toBeInTheDocument();
  expect(screen.queryByRole("list", { name: "The whole path" })).not.toBeInTheDocument();
});

test("Organisation settings' areas are a tab row under its header; the breadcrumb is Settings, then the area", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeMembersApi();
  fakeInvitesApi();
  renderStudio(`/organisations/${organisationId}/settings`);

  expect(await screen.findByRole("heading", { name: "Organisation settings", level: 1 })).toBeInTheDocument();
  expect(await sectionNames("Organisation settings")).toEqual(["General", "Credentials", "Models", "Theme", "Members", "Audit"]);
  expect(await currentSection("Organisation settings")).toBe("General");
  const tabs = within(screen.getByRole("navigation", { name: "Organisation settings" }));
  expect(tabs.getByRole("link", { name: "Members" })).toHaveAttribute("href", `/organisations/${organisationId}/settings/members`);
  expect(screen.getByRole("main")).toContainElement(tabs.getByRole("link", { name: "Members" }));
  expect(await breadcrumb()).toEqual({ crumbs: ["Settings", "General"], current: "General" });

  await openSection("Organisation settings", "Members");

  expect(await screen.findByRole("table", { name: "Members" })).toBeInTheDocument();
  expect(await currentSection("Organisation settings")).toBe("Members");
  expect(await breadcrumb()).toEqual({ crumbs: ["Settings", "Members"], current: "Members" });
  expect(breadcrumbNav().getByRole("link", { name: "Settings" })).toHaveAttribute("href", `/organisations/${organisationId}/settings`);
});

test("an Editor's settings tabs leave out Members and Audit", async () => {
  fakeAuthApi({
    signedInAs: { ...adaSession, organisations: adaSession.organisations.map((o) => ({ ...o, role: "editor" as const })) },
  });
  renderStudio(`/organisations/${organisationId}/settings/theme`);

  expect(await currentSection("Organisation settings")).toBe("Theme");
  expect(await sectionNames("Organisation settings")).toEqual(["General", "Credentials", "Models", "Theme"]);
});

test("an unknown settings address marks no tab and no crumb; every area is still offered", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(`/organisations/${organisationId}/settings/bogus`);

  expect(await sectionNames("Organisation settings")).toEqual(["General", "Credentials", "Models", "Theme", "Members", "Audit"]);
  expect(await currentSection("Organisation settings")).toBe("");
  expect(await breadcrumb()).toEqual({ crumbs: ["Settings"], current: "" });
});

test("a Project that can't be loaded is the current crumb, named Project", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage("00000000-0000-4000-8000-000000000000"));

  expect(await screen.findByRole("heading", { name: "Project not found" })).toBeInTheDocument();
  expect(await breadcrumb()).toEqual({ crumbs: ["Project"], current: "Project" });
});

test("Profile, Security and Sign out are only in the account menu; their pages are the current crumb", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage(hrProject.id));
  await screen.findByRole("heading", { level: 1, name: "HR handbook" });

  expect(await sectionNames("Account")).toEqual(["Profile", "Security", "Sign out"]);
  // With the account menu closed, nothing else on the page leads to them.
  for (const name of ["Profile", "Security", "Sign out"]) {
    expect(screen.queryByRole("link", { name })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name })).not.toBeInTheDocument();
  }

  await openSection("Account", "Profile");
  expect(await screen.findByRole("heading", { name: "Profile" })).toBeInTheDocument();
  expect(await breadcrumb()).toEqual({ crumbs: ["Profile"], current: "Profile" });

  await openSection("Account", "Security");
  expect(await screen.findByRole("heading", { name: "Security", level: 1 })).toBeInTheDocument();
  expect(await breadcrumb()).toEqual({ crumbs: ["Security"], current: "Security" });
});

test("Cost is the current crumb on the cost page", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(`/organisations/${organisationId}/cost`);

  expect(await breadcrumb()).toEqual({ crumbs: ["Cost"], current: "Cost" });
});

test("no navigation item carries a number hint", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage(hrProject.id));
  await screen.findByRole("heading", { level: 1, name: "HR handbook" });

  const sections = ["Documents", "Instructions", "Agents", "Conversations", "Analytics", "Settings"];
  expect(await sectionNames("Project sections")).toEqual(sections);
  const links = within(screen.getByRole("list", { name: "Project sections" })).getAllByRole("link");
  // Hidden text counts too: a hint hidden from assistive technology is still on screen.
  expect(links.map((link) => link.textContent)).toEqual(sections);
  expect(screen.getByRole("banner").textContent).not.toMatch(/[0-9]/);
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
