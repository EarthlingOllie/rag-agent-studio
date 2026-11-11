import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { adaInTwo, analyticalEngines, differenceEngines, fakeSwitcherApi } from "../test/organisations";
import { openSection, sectionNames } from "../test/navigation";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

/** The sidebar's Organisation switcher. */
function switcher() {
  return within(screen.getByRole("navigation", { name: "Studio" })).getByRole("button", { name: /, Organisations$/ });
}

async function openMembers() {
  await openSection("Organisation sections", "Settings");
  await openSection("Organisation settings", "Members");
  return screen.findByRole("table", { name: "Pending invites" });
}

test("a Member of one Organisation sees its name, not a switcher", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  expect(within(screen.getByRole("navigation", { name: "Studio" })).getByText("Analytical Engines")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /, Organisations$/ })).not.toBeInTheDocument();
});

test("a Member of several Organisations sees a switcher listing them, with the open one chosen", async () => {
  fakeSwitcherApi(adaInTwo());
  renderStudio("/");

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  expect(switcher()).toHaveAccessibleName("Analytical Engines, Organisations");
  expect(await sectionNames("Organisations")).toEqual(["Analytical Engines", "Difference Engines"]);
  await userEvent.click(switcher());
  expect(screen.getByRole("menuitem", { name: "Analytical Engines" })).toHaveAttribute("aria-current", "page");
});

test("the Studio opens the Organisation the Member last switched to", async () => {
  fakeSwitcherApi(adaInTwo(differenceEngines.id));
  renderStudio("/");

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  expect(switcher()).toHaveAccessibleName("Difference Engines, Organisations");
});

test("switching opens the other Organisation, remembers it, and shows only its data", async () => {
  const { switches } = fakeSwitcherApi(adaInTwo());
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });
  const before = await openMembers();
  expect(within(before).getByText("grace@example.test")).toBeInTheDocument();

  await openSection("Organisations", "Difference Engines");

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  expect(switcher()).toHaveAccessibleName("Difference Engines, Organisations");
  expect(switches).toEqual([{ organisation_id: differenceEngines.id }]);
  const after = await openMembers();
  expect(within(after).getByText("charles@example.test")).toBeInTheDocument();
  expect(screen.queryByText("grace@example.test")).not.toBeInTheDocument();

  // A reload (a fresh Studio) opens the remembered Organisation.
  renderStudio("/");
  const reloaded = await screen.findAllByRole("button", { name: "Difference Engines, Organisations" });
  expect(reloaded.length).toBeGreaterThan(0);
});

test("an Organisation's address keeps it open across reloads, whichever one is remembered", async () => {
  fakeSwitcherApi(adaInTwo(analyticalEngines.id));
  renderStudio(`/organisations/${differenceEngines.id}/projects`);

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  expect(switcher()).toHaveAccessibleName("Difference Engines, Organisations");
});

test("says when switching failed and stays in the same Organisation", async () => {
  fakeSwitcherApi(adaInTwo(), { failWith: 500 });
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });

  await openSection("Organisations", "Difference Engines");

  expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't switch Organisation. Try again.");
  expect(switcher()).toHaveAccessibleName("Analytical Engines, Organisations");
  expect(screen.getByText("Projects", { selector: "h1" })).toBeInTheDocument();
});

test("the switcher is disabled while a switch is under way", async () => {
  fakeSwitcherApi(adaInTwo());
  server.use(http.put("*/api/auth/me/active-organisation", () => delay("infinite")));
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });

  await openSection("Organisations", "Difference Engines");

  expect(switcher()).toBeDisabled();
});

test("on an Organisation the Member doesn't belong to, the switcher offers their own", async () => {
  fakeSwitcherApi(adaInTwo());
  renderStudio("/organisations/00000000-0000-4000-8000-000000000000/projects");

  expect(await screen.findByRole("heading", { name: "Organisation not found" })).toBeInTheDocument();
  expect(switcher()).toHaveAccessibleName("Choose an Organisation, Organisations");

  await openSection("Organisations", "Difference Engines");

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  expect(switcher()).toHaveAccessibleName("Difference Engines, Organisations");
});

test("after switching, nothing from the previous Organisation is shown while the new one's data loads", async () => {
  fakeSwitcherApi(adaInTwo());
  renderStudio("/");
  await screen.findByRole("heading", { name: "Projects" });
  expect(within(await openMembers()).getByText("grace@example.test")).toBeInTheDocument();
  await openSection("Organisations", "Difference Engines");
  await screen.findByRole("heading", { name: "Projects" });
  server.use(http.get(`*/api/organisations/${differenceEngines.id}/invites`, () => delay("infinite")));

  await openSection("Organisation sections", "Settings");
  await openSection("Organisation settings", "Members");

  expect(await screen.findByText("Loading invites…")).toHaveRole("status");
  expect(screen.queryByText("grace@example.test")).not.toBeInTheDocument();
});

test("choosing the open Organisation again changes nothing", async () => {
  const { switches } = fakeSwitcherApi(adaInTwo());
  renderStudio(`/organisations/${analyticalEngines.id}/settings`);
  await screen.findByRole("heading", { name: "Organisation settings" });

  await openSection("Organisations", "Analytical Engines");

  expect(screen.getByRole("heading", { name: "Organisation settings" })).toBeInTheDocument();
  expect(switches).toEqual([]);
});
