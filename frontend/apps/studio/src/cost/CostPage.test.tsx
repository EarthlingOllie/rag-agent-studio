import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { adaSession, fakeAuthApi, type Session } from "../test/auth";
import { fakeCostApi } from "../test/cost";
import { fakeProjectsApi } from "../test/projects";
import { openSection, sectionNames } from "../test/navigation";
import { renderStudio } from "../test/render";

const organisationId = adaSession.organisations[0]?.id ?? "";
const costPage = `/organisations/${organisationId}/cost`;
const editorSession: Session = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};

/** The table's rows as the Owner reads them, cell by cell, header and total included. */
function table(name: string): string[][] {
  return within(screen.getByRole("table", { name }))
    .getAllByRole("row")
    .map((row) => [...row.querySelectorAll("th, td")].map((cell) => cell.textContent));
}

test("an Owner sees what each Project cost over the last 30 days, with the Playground in its own column", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const { queries } = fakeCostApi();
  renderStudio(costPage);

  expect(await screen.findByRole("table", { name: "Cost by Project" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 1, name: "Organisation cost" })).toBeInTheDocument();
  expect(screen.getByText(/2026-10-08 to 2026-11-06 \(UTC days\), including today so far/)).toBeInTheDocument();
  expect(table("Cost by Project")).toEqual([
    ["Project", "Visitors", "Playground", "Total"],
    ["Handbook", "$12.50", "$0.0042", "$12.50"],
    ["Payroll", "$0.003", "$0.00", "$0.003"],
    ["All Projects", "$12.50", "$0.0042", "$12.51"],
  ]);
  expect(screen.getByLabelText("Break down by")).toHaveDisplayValue("Project");
  expect(queries.map((query) => query.toString())).toEqual(["group_by=project"]);
  // On a narrow screen the table scrolls sideways in a box that takes keyboard focus.
  const box = screen.getByRole("region", { name: "Cost by Project" });
  expect(box).toHaveAttribute("tabindex", "0");
  expect(within(box).getByRole("table", { name: "Cost by Project" })).toBeInTheDocument();
});

test("the Owner breaks the cost down by Agent, each with its Project", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const { queries } = fakeCostApi();
  renderStudio(costPage);
  await screen.findByRole("table", { name: "Cost by Project" });

  await userEvent.selectOptions(screen.getByLabelText("Break down by"), "Agent");

  expect(await screen.findByRole("table", { name: "Cost by Agent" })).toBeInTheDocument();
  expect(table("Cost by Agent")).toEqual([
    ["Agent", "Project", "Visitors", "Playground", "Total"],
    ["HR helper", "Handbook", "$12.50", "$0.00", "$12.50"],
    ["Tried once", "Handbook", "$0.00", "$0.0042", "$0.0042"],
    ["Payroll helper", "Payroll", "$0.003", "$0.00", "$0.003"],
    ["All Agents", "", "$12.50", "$0.0042", "$12.51"],
  ]);
  expect(queries.at(-1)?.toString()).toBe("group_by=agent");
});

test("the Owner chooses the period, and a period the API refuses is explained", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const { queries } = fakeCostApi();
  renderStudio(costPage);
  await screen.findByRole("table", { name: "Cost by Project" });

  await userEvent.type(screen.getByLabelText("From (UTC)"), "2026-11-01");
  await userEvent.type(screen.getByLabelText("To (UTC)"), "2026-11-03");

  expect(await screen.findByText(/2026-11-01 to 2026-11-03 \(UTC days\)/)).toBeInTheDocument();
  expect(queries.at(-1)?.toString()).toBe("group_by=project&start=2026-11-01&end=2026-11-03");

  await userEvent.clear(screen.getByLabelText("To (UTC)"));
  await userEvent.type(screen.getByLabelText("To (UTC)"), "2026-10-01");

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Check the dates: From can't be after To, and the period can be at most 366 days.",
  );

  await userEvent.clear(screen.getByLabelText("To (UTC)"));
  await userEvent.clear(screen.getByLabelText("From (UTC)"));

  expect(await screen.findByText(/2026-10-08 to 2026-11-06 \(UTC days\)/)).toBeInTheDocument();
  expect(queries.at(-1)?.toString()).toBe("group_by=project");
});

test("a period with no spending says so", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeCostApi({ rows: { project: [], agent: [] } });
  renderStudio(costPage);

  expect(await screen.findByText("Nothing was spent in this period.")).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

test("the page says so while the cost loads and when it can't be loaded", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeCostApi({ status: 500 });
  renderStudio(costPage);

  expect(await screen.findByText("Loading the cost…")).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent("The cost could not be loaded. Try again shortly.");
});

test("Owners find the cost page in the navigation; Editors neither see it nor can open it", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeCostApi();
  const { unmount } = renderStudio(`/organisations/${organisationId}/projects`);
  await screen.findByRole("heading", { name: "Projects" });

  await openSection("Organisation sections", "Cost");

  expect(await screen.findByRole("table", { name: "Cost by Project" })).toBeInTheDocument();
  unmount();

  fakeAuthApi({ signedInAs: editorSession });
  const { queries } = fakeCostApi();
  const editor = renderStudio(`/organisations/${organisationId}/projects`);
  await screen.findByRole("heading", { name: "Projects" });
  expect(await sectionNames("Organisation sections")).not.toContain("Cost");
  editor.unmount();
  renderStudio(costPage);

  expect(await screen.findByText("Only Owners can see what the Organisation spends.")).toBeInTheDocument();
  expect(within(screen.getByRole("navigation", { name: "Breadcrumb" })).getByText("Cost")).toHaveAttribute("aria-current", "page");
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(queries).toEqual([]);
});
