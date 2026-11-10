import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { adaSession, fakeAuthApi } from "../test/auth";
import { navigationButton, openDrawer, sidebar } from "../test/navigation";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";

const organisationId = adaSession.organisations[0]?.id ?? "";
const projectPage = (projectId: string) => `/organisations/${organisationId}/projects/${projectId}`;

test("the top bar's Open navigation button opens the sidebar as a drawer, focused on the current link", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });

  const button = await navigationButton();
  expect(screen.getByRole("banner")).toContainElement(button);
  expect(button).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("dialog", { name: "Navigation" })).not.toBeInTheDocument();

  const drawer = await openDrawer();

  expect(button).toHaveAttribute("aria-expanded", "true");
  expect(drawer).toHaveAttribute("aria-modal", "true");
  const nav = within(drawer).getByRole("navigation", { name: "Studio" });
  const projects = within(nav).getByRole("link", { name: "Projects" });
  expect(projects).toHaveAttribute("aria-current", "page");
  expect(projects).toHaveFocus();
});

test("Escape closes the drawer and focus returns to the Open navigation button", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });

  await openDrawer();
  await userEvent.keyboard("{Escape}");

  expect(screen.queryByRole("dialog", { name: "Navigation" })).not.toBeInTheDocument();
  const button = await navigationButton();
  expect(button).toHaveFocus();
  expect(button).toHaveAttribute("aria-expanded", "false");
});

test("Tab and Shift+Tab keep focus inside the open drawer", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });

  const drawer = await openDrawer();
  const links = within(drawer).getAllByRole("link");
  expect(links.map((link) => link.textContent)).toEqual(["Projects", "Cost", "Settings"]);

  await userEvent.tab();
  expect(links[1]).toHaveFocus();
  await userEvent.tab();
  expect(links[2]).toHaveFocus();
  // Past the last link, back to the first.
  await userEvent.tab();
  expect(links[0]).toHaveFocus();
  // And before the first, round to the last.
  await userEvent.tab({ shift: true });
  expect(links[2]).toHaveFocus();
  await userEvent.tab({ shift: true });
  expect(links[1]).toHaveFocus();
});

test("a press outside the drawer closes it and focus returns to the button", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });

  await openDrawer();
  await userEvent.click(screen.getByTestId("drawer-scrim"));

  expect(screen.queryByRole("dialog", { name: "Navigation" })).not.toBeInTheDocument();
  expect(await navigationButton()).toHaveFocus();
});

test("following a link in the drawer opens its page, closes the drawer and returns focus to the button", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });

  const drawer = await openDrawer();
  await userEvent.click(within(drawer).getByRole("link", { name: "Settings" }));

  expect(await screen.findByRole("heading", { name: "Organisation settings", level: 1 })).toBeInTheDocument();
  expect(screen.queryByRole("dialog", { name: "Navigation" })).not.toBeInTheDocument();
  expect(await navigationButton()).toHaveFocus();
  // Opened again, it starts from the new current link.
  const again = await openDrawer();
  expect(within(again).getByRole("link", { name: "Settings" })).toHaveFocus();
});

test("on a page with no current link, opening the drawer focuses its first link", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(`/organisations/${organisationId}/profile`);
  await screen.findByRole("heading", { name: "Profile" });

  const drawer = await openDrawer();

  expect(within(drawer).getByRole("link", { name: "Projects" })).not.toHaveAttribute("aria-current");
  expect(within(drawer).getByRole("link", { name: "Projects" })).toHaveFocus();
});

test("inside the drawer the Project switcher's menu takes Escape first; choosing a Project closes the drawer", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(projectPage(hrProject.id));
  await screen.findByRole("heading", { level: 1, name: "HR handbook" });

  const drawer = within(await openDrawer());
  expect(drawer.getByRole("link", { name: "Documents" })).toHaveFocus();
  const switcher = drawer.getByRole("button", { name: "HR handbook, Projects" });
  await userEvent.click(switcher);
  expect(drawer.getByRole("menu", { name: "Projects" })).toBeInTheDocument();

  // Escape closes the menu, not the drawer.
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("menu", { name: "Projects" })).not.toBeInTheDocument();
  expect(switcher).toHaveFocus();
  expect(screen.getByRole("dialog", { name: "Navigation" })).toBeInTheDocument();

  await userEvent.click(switcher);
  await userEvent.click(drawer.getByRole("menuitem", { name: "Sales enablement" }));

  expect(await screen.findByRole("heading", { level: 1, name: "Sales enablement" })).toBeInTheDocument();
  expect(screen.queryByRole("dialog", { name: "Navigation" })).not.toBeInTheDocument();
  expect(await navigationButton()).toHaveFocus();
});

test("closed, the sidebar is no dialog and keeps no keys: Tab and Escape behave as on any page", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });

  const nav = within(await sidebar());
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  nav.getByRole("link", { name: "Settings" }).focus();
  await userEvent.keyboard("{Escape}");
  expect(nav.getByRole("link", { name: "Settings" })).toHaveFocus();
  // Tab leaves the sidebar for the page instead of going round to its first link.
  await userEvent.tab();
  expect(nav.getByRole("link", { name: "Projects" })).not.toHaveFocus();
  expect(screen.getByRole("main")).toContainElement(document.activeElement as HTMLElement);
});
