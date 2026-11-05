import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { type AuditEvent, fakeAuditApi, grace, lockedOut, organisationCreated, roleChanged } from "../test/audit";
import { adaSession, fakeAuthApi } from "../test/auth";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const auditPath = `/organisations/${organisationId}/settings/audit`;
const editorSession = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};

function rows() {
  const [, ...body] = within(screen.getByRole("table", { name: "Audit Events" })).getAllByRole("row");
  return body.map((row) => within(row).getAllByRole("cell").map((cell) => cell.textContent));
}

test("Owners open the Audit tab from Organisation settings and see who changed what, and when", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeAuditApi();
  renderStudio(`/organisations/${organisationId}/settings`);

  const tabs = await screen.findByRole("navigation", { name: "Organisation settings" });
  await userEvent.click(within(tabs).getByRole("link", { name: "Audit" }));

  expect(await screen.findByRole("heading", { name: "Audit" })).toBeInTheDocument();
  expect(await screen.findByRole("cell", { name: "member.locked_out" })).toBeInTheDocument();
  expect(rows()).toEqual([
    ["2026-06-03 00:00 UTC", "System", "member.locked_out", "settings", "—", "—"],
    ["2026-06-02 14:05 UTC", "Grace Hopper", "member.role_changed", "member m-42", '{"role":"editor"}', '{"role":"owner"}'],
    [
      "2026-06-01 09:30 UTC",
      "Ada Lovelace",
      "organisation.created",
      `organisation ${organisationId}`,
      "—",
      '{"name":"Analytical Engines"}',
    ],
  ]);
  expect(screen.getByText("Page 1 of 1 · 3 events")).toBeInTheDocument();
});

test("Editors don't see the Audit tab", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  renderStudio(`/organisations/${organisationId}/settings`);

  const tabs = await screen.findByRole("navigation", { name: "Organisation settings" });

  expect(within(tabs).getByRole("link", { name: "General" })).toBeInTheDocument();
  expect(within(tabs).queryByRole("link", { name: "Audit" })).not.toBeInTheDocument();
  expect(screen.getByText(/Members, roles and security settings/)).toBeInTheDocument();
});

test("an Editor who opens the Audit address is told it is for Owners, and nothing is requested", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  const { queries } = fakeAuditApi();
  renderStudio(auditPath);

  expect(await screen.findByText("Only Owners can view Audit Events.")).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(queries).toEqual([]);
});

test("Owners filter by actor, action and a date range", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const { queries } = fakeAuditApi();
  renderStudio(auditPath);
  await screen.findByRole("cell", { name: "member.locked_out" });

  await userEvent.selectOptions(screen.getByLabelText("Actor"), "Grace Hopper");
  expect(await screen.findByText("Page 1 of 1 · 1 event")).toBeInTheDocument();
  expect(rows().map((row) => row[2])).toEqual(["member.role_changed"]);

  await userEvent.selectOptions(screen.getByLabelText("Actor"), "Anyone");
  await userEvent.selectOptions(screen.getByLabelText("Action"), "organisation.created");
  await userEvent.type(screen.getByLabelText("From (UTC)"), "2026-06-01");
  await userEvent.type(screen.getByLabelText("To (UTC)"), "2026-06-01");

  expect(await screen.findByText("Page 1 of 1 · 1 event")).toBeInTheDocument();
  expect(rows().map((row) => row[2])).toEqual(["organisation.created"]);
  const last = Object.fromEntries(queries.at(-1) ?? []);
  // The To date is inclusive in the Studio, so the API gets the start of the next day.
  expect(last).toEqual({
    action: "organisation.created",
    start: "2026-06-01T00:00:00.000Z",
    end: "2026-06-02T00:00:00.000Z",
    page: "1",
    page_size: "25",
  });
  expect(queries.some((query) => query.get("actor_id") === grace.id)).toBe(true);

  await userEvent.clear(screen.getByLabelText("From (UTC)"));
  await userEvent.clear(screen.getByLabelText("To (UTC)"));
  await userEvent.selectOptions(screen.getByLabelText("Action"), "Any action");
  expect(await screen.findByText("Page 1 of 1 · 3 events")).toBeInTheDocument();
});

test("filters that match nothing say so", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeAuditApi();
  renderStudio(auditPath);
  await screen.findByRole("cell", { name: "member.locked_out" });

  await userEvent.type(screen.getByLabelText("From (UTC)"), "2030-01-01");

  expect(await screen.findByText("No Audit Events match these filters.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Next page" })).not.toBeInTheDocument();
});

test("Owners page through long histories, and changing a filter goes back to the first page", async () => {
  const many: AuditEvent[] = Array.from({ length: 30 }, (_, index) => ({
    ...roleChanged,
    id: `b0000000-0000-4000-8000-${String(index).padStart(12, "0")}`,
    action: index % 2 === 0 ? "member.role_changed" : "member.invited",
    occurred_at: new Date(Date.UTC(2026, 5, 30, 0, 59 - index)).toISOString(),
  }));
  fakeAuthApi({ signedInAs: adaSession });
  const { queries } = fakeAuditApi(many);
  renderStudio(auditPath);

  expect(await screen.findByText("Page 1 of 2 · 30 events")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Next page" }));

  expect(await screen.findByText("Page 2 of 2 · 30 events")).toBeInTheDocument();
  expect(rows()).toHaveLength(5);
  expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Previous page" }));
  expect(await screen.findByText("Page 1 of 2 · 30 events")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Next page" }));
  await screen.findByText("Page 2 of 2 · 30 events");

  await userEvent.selectOptions(screen.getByLabelText("Action"), "member.invited");

  expect(await screen.findByText("Page 1 of 1 · 15 events")).toBeInTheDocument();
  expect(queries.at(-1)?.get("page")).toBe("1");
});

test("shows a loading state, then an error if the Audit Events can't be loaded", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeAuditApi([lockedOut, organisationCreated]);
  server.use(http.get("*/api/organisations/:organisationId/audit-events", () => delay("infinite")));
  const { unmount } = renderStudio(auditPath);

  expect(await screen.findByText("Loading Audit Events…")).toHaveRole("status");
  unmount();

  server.use(
    http.get("*/api/organisations/:organisationId/audit-events", () => new HttpResponse(null, { status: 500 })),
    http.get("*/api/organisations/:organisationId/audit-events/facets", () => new HttpResponse(null, { status: 500 })),
  );
  renderStudio(auditPath);

  expect(await screen.findByRole("alert")).toHaveTextContent("Audit Events could not be loaded. Try again shortly.");
  // Without the filter options the filters still work, offering only "any".
  expect(screen.getByLabelText("Actor")).toHaveDisplayValue("Anyone");
});
