import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { menuButton, openSection, sectionNames } from "../test/navigation";
import { fakeProjectsApi } from "../test/projects";
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

  expect(await sectionNames("Organisation sections")).toEqual(["Projects", "Cost", "Settings", "Security"]);
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

  expect(await breadcrumb().findByText("HR handbook")).toHaveAttribute("aria-current", "page");
  expect(breadcrumb().getByRole("button", { name: "Projects, Organisation sections" })).not.toHaveAttribute("aria-current");

  await openSection("Organisation sections", "Security");
  expect(await screen.findByRole("heading", { name: "Security", level: 1 })).toBeInTheDocument();
  expect(breadcrumb().getByRole("button", { name: "Security, Organisation sections" })).toHaveAttribute("aria-current", "page");
});

test("a Project that can't be loaded is a plain crumb", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(`/organisations/${organisationId}/projects/00000000-0000-4000-8000-000000000000`);

  expect(await screen.findByRole("heading", { name: "Project not found" })).toBeInTheDocument();
  expect(within(screen.getByRole("navigation", { name: "Breadcrumb" })).getByText("Project")).toHaveAttribute(
    "aria-current",
    "page",
  );
});

test("the account menu opens the Profile, which is then the current crumb", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });

  expect(await sectionNames("Account")).toEqual(["Profile", "Sign out"]);
  await openSection("Account", "Profile");

  expect(await screen.findByRole("heading", { name: "Profile" })).toBeInTheDocument();
  expect(within(screen.getByRole("navigation", { name: "Breadcrumb" })).getByText("Profile")).toHaveAttribute(
    "aria-current",
    "page",
  );
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

  expect(await screen.findByRole("status")).toHaveTextContent("Loading…");
});

test("says when the API cannot be reached", async () => {
  server.use(http.get("*/api/auth/me", () => new HttpResponse(null, { status: 500 })));
  renderStudio("/");

  expect(await screen.findByRole("alert")).toHaveTextContent("The Studio could not reach the API.");
});

test("tells a Member with no Organisation that they don't belong to one", async () => {
  fakeAuthApi({ signedInAs: { ...adaSession, organisations: [], active_organisation_id: null } });
  renderStudio("/");

  expect(await screen.findByText("You don't belong to any Organisation yet.")).toHaveRole("status");
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

  await userEvent.click(await screen.findByRole("link", { name: "RAG Agent Studio" }));

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
});
