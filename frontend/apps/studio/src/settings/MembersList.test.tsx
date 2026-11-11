import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeInvitesApi, organisationId } from "../test/invites";
import { adaMember, charlesMember, fakeMembersApi, graceMember, LAST_OWNER } from "../test/members";
import { sectionNames } from "../test/navigation";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const membersPath = `/organisations/${organisationId}/settings/members`;

function memberRows() {
  const [, ...body] = within(screen.getByRole("table", { name: "Members" })).getAllByRole("row");
  return body.map((row) => {
    const [name, email, role] = within(row).getAllByRole("cell");
    const select = within(role as HTMLElement).queryByRole("combobox");
    return [name?.textContent, email?.textContent, select ? (select as HTMLSelectElement).value : role?.textContent];
  });
}

beforeEach(() => {
  fakeInvitesApi({ pending: [] });
});

test("Owners see every Member with their role", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeMembersApi({ members: [adaMember, graceMember, charlesMember] });
  renderStudio(membersPath);

  expect(await screen.findByRole("table", { name: "Members" })).toBeInTheDocument();
  expect(memberRows()).toEqual([
    ["Ada Lovelace (you)", "ada@example.test", "owner"],
    ["Grace Hopper", "grace@example.test", "editor"],
    ["Charles Babbage", "charles@example.test", "owner"],
  ]);
});

test("an Owner changes a Member's role", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const api = fakeMembersApi();
  renderStudio(membersPath);
  await screen.findByRole("table", { name: "Members" });

  await userEvent.selectOptions(screen.getByLabelText("Role for Grace Hopper"), "Owner");

  // The change is confirmed by a toast.
  expect(await screen.findByRole("status")).toHaveTextContent("Grace Hopper is now an Owner.");
  expect(api.roleChanges).toEqual([{ memberId: graceMember.id, role: "owner" }]);
  expect(memberRows()[1]).toEqual(["Grace Hopper", "grace@example.test", "owner"]);
});

test("demoting the last Owner is refused and the role stays", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const api = fakeMembersApi();
  renderStudio(membersPath);
  await screen.findByRole("table", { name: "Members" });

  await userEvent.selectOptions(screen.getByLabelText("Role for Ada Lovelace"), "Editor");

  expect(await screen.findByRole("alert")).toHaveTextContent(LAST_OWNER);
  expect(api.roleChanges).toEqual([{ memberId: adaMember.id, role: "editor" }]);
  expect(memberRows()[0]).toEqual(["Ada Lovelace (you)", "ada@example.test", "owner"]);
});

test("an Owner who steps down loses the Owner-only tabs", async () => {
  const session = { ...adaSession };
  fakeAuthApi({ signedInAs: session });
  fakeMembersApi({ members: [adaMember, charlesMember] });
  renderStudio(membersPath);
  await screen.findByRole("table", { name: "Members" });
  // The API now reports Ada as an Editor.
  server.use(
    http.get("*/api/auth/me", () =>
      HttpResponse.json({ ...adaSession, organisations: adaSession.organisations.map((o) => ({ ...o, role: "editor" })) }),
    ),
  );

  await userEvent.selectOptions(screen.getByLabelText("Role for Ada Lovelace"), "Editor");

  expect(await screen.findByText("Only Owners can manage Members and invites.")).toBeInTheDocument();
  const sections = await sectionNames("Organisation settings");
  expect(sections).not.toContain("Members");
  expect(sections).not.toContain("Audit");
});

test("an Owner removes a Member after confirming", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const api = fakeMembersApi();
  renderStudio(membersPath);
  await screen.findByRole("table", { name: "Members" });

  await userEvent.click(screen.getByRole("button", { name: "Remove Grace Hopper" }));
  const dialog = screen.getByRole("alertdialog", { name: "Remove Grace Hopper?" });
  expect(dialog).toHaveTextContent("Grace Hopper loses access to Analytical Engines");
  await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(api.removed).toEqual([]);
  await userEvent.click(screen.getByRole("button", { name: "Remove Grace Hopper" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, remove Grace Hopper" }));

  expect(await screen.findByRole("status")).toHaveTextContent(
    "Grace Hopper was removed and can no longer open this Organisation.",
  );
  expect(api.removed).toEqual([graceMember.id]);
  expect(memberRows()).toEqual([["Ada Lovelace (you)", "ada@example.test", "owner"]]);
});

test("the signed-in Owner isn't offered Remove on their own row", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeMembersApi();
  renderStudio(membersPath);
  await screen.findByRole("table", { name: "Members" });

  expect(screen.queryByRole("button", { name: "Remove Ada Lovelace" })).not.toBeInTheDocument();
});

test("removing the last Owner is refused", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeMembersApi({ members: [adaMember, { ...charlesMember, role: "owner" }] });
  server.use(
    http.delete("*/api/organisations/:organisationId/members/:memberId", () =>
      HttpResponse.json({ detail: LAST_OWNER }, { status: 409 }),
    ),
  );
  renderStudio(membersPath);
  await screen.findByRole("table", { name: "Members" });

  await userEvent.click(screen.getByRole("button", { name: "Remove Charles Babbage" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, remove Charles Babbage" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(LAST_OWNER);
  expect(memberRows()).toHaveLength(2);
});

test.each([
  [500, "Something went wrong. Try again."],
  [404, "Something went wrong. Try again."],
])("a failed role change (%i) says to try again", async (status, message) => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeMembersApi();
  server.use(
    http.patch("*/api/organisations/:organisationId/members/:memberId", () =>
      HttpResponse.json({ detail: "nope" }, { status }),
    ),
  );
  renderStudio(membersPath);
  await screen.findByRole("table", { name: "Members" });

  await userEvent.selectOptions(screen.getByLabelText("Role for Grace Hopper"), "Owner");

  expect(await screen.findByRole("alert")).toHaveTextContent(message);
});

test("an unreachable API while removing says to try again", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeMembersApi();
  server.use(http.delete("*/api/organisations/:organisationId/members/:memberId", () => HttpResponse.error()));
  renderStudio(membersPath);
  await screen.findByRole("table", { name: "Members" });

  await userEvent.click(screen.getByRole("button", { name: "Remove Grace Hopper" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, remove Grace Hopper" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("the Members list shows its loading and error states", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  server.use(
    http.get("*/api/organisations/:organisationId/members", async () => {
      await delay(50);
      return HttpResponse.json({ detail: "boom" }, { status: 500 });
    }),
  );
  renderStudio(membersPath);

  expect(await screen.findByText("Loading Members…")).toBeInTheDocument();
  expect(await screen.findByText("The Members could not be loaded. Try again shortly.")).toBeInTheDocument();
});
