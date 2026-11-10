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

/** The summary cards as the Owner reads them: each label with its figure. */
function stats(): string[] {
  return within(screen.getByRole("list", { name: "Spend for the period" }))
    .getAllByRole("listitem")
    .map((card) => card.textContent);
}

test("an Owner sees what each Project cost over the last 30 days, with the Playground in its own column", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const { queries } = fakeCostApi();
  renderStudio(costPage);

  expect(await screen.findByRole("table", { name: "Cost by Project" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 1, name: "Organisation cost" })).toBeInTheDocument();
  expect(
    screen.getByText("What Visitors' Conversations and Playground testing cost, at the prices frozen when each reply was made."),
  ).toBeInTheDocument();
  expect(stats()).toEqual(["Total$12.51", "Visitors$12.50", "Playground$0.0042"]);
  expect(screen.getByText(/2026-10-08 to 2026-11-06 \(UTC days\), including today so far/)).toBeInTheDocument();
  expect(table("Cost by Project")).toEqual([
    ["Project", "Visitors", "Playground", "Total"],
    ["Handbook", "$12.50", "$0.0042", "$12.50"],
    ["Payroll", "$0.003", "$0.00", "$0.003"],
    ["All Projects", "$12.50", "$0.0042", "$12.51"],
  ]);
  const breakdown = screen.getByRole("radiogroup", { name: "Break down by" });
  expect(within(breakdown).getAllByRole("radio").map((radio) => radio.textContent)).toEqual(["Project", "Agent"]);
  expect(within(breakdown).getByRole("radio", { name: "Project" })).toBeChecked();
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

  await userEvent.click(screen.getByRole("radio", { name: "Agent" }));

  expect(await screen.findByRole("table", { name: "Cost by Agent" })).toBeInTheDocument();
  expect(table("Cost by Agent")).toEqual([
    ["Agent", "Project", "Visitors", "Playground", "Total"],
    ["HR helper", "Handbook", "$12.50", "$0.00", "$12.50"],
    ["Tried once", "Handbook", "$0.00", "$0.0042", "$0.0042"],
    ["Payroll helper", "Payroll", "$0.003", "$0.00", "$0.003"],
    ["All Agents", "", "$12.50", "$0.0042", "$12.51"],
  ]);
  expect(screen.getByRole("radio", { name: "Agent" })).toBeChecked();
  expect(stats()).toEqual(["Total$12.51", "Visitors$12.50", "Playground$0.0042"]);
  expect(queries.at(-1)?.toString()).toBe("group_by=agent");

  // The arrow keys move the choice back, as in every segmented control.
  await userEvent.keyboard("{ArrowLeft}");

  expect(await screen.findByRole("table", { name: "Cost by Project" })).toBeInTheDocument();
  expect(queries.at(-1)?.toString()).toBe("group_by=project");
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

  expect(await screen.findByRole("heading", { name: "Nothing was spent in this period" })).toBeInTheDocument();
  expect(screen.getByText(/Visitors' Conversations and Playground testing in any Project show up here/)).toBeInTheDocument();
  expect(screen.getByText(/2026-10-08 to 2026-11-06 \(UTC days\)/)).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(screen.queryByRole("list", { name: "Spend for the period" })).not.toBeInTheDocument();
});

test("the page says so while the cost loads and when it can't be loaded", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeCostApi({ status: 500 });
  renderStudio(costPage);

  expect(await screen.findByRole("status", { name: "Loading the cost" })).toBeInTheDocument();
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

  expect(await screen.findByRole("heading", { level: 2, name: "Only Owners see the Organisation's spend" })).toBeInTheDocument();
  expect(screen.getByText("Ask an Owner of this Organisation if you need to know what it spent.")).toBeInTheDocument();
  expect(screen.queryByRole("radiogroup", { name: "Break down by" })).not.toBeInTheDocument();
  expect(within(screen.getByRole("navigation", { name: "Breadcrumb" })).getByText("Cost")).toHaveAttribute("aria-current", "page");
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(queries).toEqual([]);
});
