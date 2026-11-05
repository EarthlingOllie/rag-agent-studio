import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { expiredInvite, fakeInvitesApi, graceInvite, linkFor, organisationId } from "../test/invites";
import { fakeMembersApi } from "../test/members";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const membersPath = `/organisations/${organisationId}/settings/members`;
const editorSession = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};

beforeEach(() => {
  fakeMembersApi();
});

function pendingRows() {
  const [, ...body] = within(screen.getByRole("table", { name: "Pending invites" })).getAllByRole("row");
  return body.map((row) =>
    within(row)
      .getAllByRole("cell")
      .slice(0, 4)
      .map((cell) => cell.textContent),
  );
}

function stubClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
}

async function inviteSomeone(email: string, { role, sendEmail = true }: { role?: string; sendEmail?: boolean } = {}) {
  const form = screen.getByRole("form", { name: "Invite someone" });
  await userEvent.type(within(form).getByLabelText("Email"), email);
  if (role) await userEvent.selectOptions(within(form).getByLabelText("Role"), role);
  if (!sendEmail) await userEvent.click(within(form).getByLabelText("Email the invite link"));
  await userEvent.click(within(form).getByRole("button", { name: "Invite" }));
}

test("Owners open Members from Organisation settings and see pending invites", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeInvitesApi();
  renderStudio(`/organisations/${organisationId}/settings`);

  const tabs = await screen.findByRole("navigation", { name: "Organisation settings" });
  await userEvent.click(within(tabs).getByRole("link", { name: "Members" }));

  expect(await screen.findByRole("table", { name: "Pending invites" })).toBeInTheDocument();
  expect(pendingRows()).toEqual([
    ["grace@example.test", "Editor", "Ada Lovelace", "2026-06-08"],
    ["charles@example.test", "Owner", "Ada Lovelace", "Expired"],
  ]);
});

test("Editors don't see the Members tab, and its address tells them it is for Owners", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  const api = fakeInvitesApi();
  renderStudio(membersPath);

  const tabs = await screen.findByRole("navigation", { name: "Organisation settings" });

  expect(within(tabs).queryByRole("link", { name: "Members" })).not.toBeInTheDocument();
  expect(screen.getByText("Only Owners can manage Members and invites.")).toBeInTheDocument();
  expect(api.created).toEqual([]);
});

test("an Owner invites by email with a role and can copy the link", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const api = fakeInvitesApi({ pending: [] });
  const copied: string[] = [];
  stubClipboard((text) => {
    copied.push(text);
    return Promise.resolve();
  });
  renderStudio(membersPath);
  expect(await screen.findByText("No pending invites.")).toBeInTheDocument();

  await inviteSomeone("grace@example.test", { role: "Owner" });

  const result = await screen.findByRole("status");
  expect(result).toHaveTextContent("We emailed an invite to grace@example.test.");
  expect(result).toHaveTextContent("expires on 2026-06-08");
  expect(within(result).getByLabelText("Invite link for grace@example.test")).toHaveValue(linkFor("new-token-1"));
  expect(api.created).toEqual([{ email: "grace@example.test", role: "owner", send_email: true }]);
  expect(await screen.findByRole("table", { name: "Pending invites" })).toBeInTheDocument();
  expect(pendingRows()).toEqual([["grace@example.test", "Owner", "Ada Lovelace", "2026-06-08"]]);
  expect(screen.getByLabelText("Email")).toHaveValue("");

  await userEvent.click(within(result).getByRole("button", { name: "Copy link" }));

  expect(await within(result).findByText("Link copied.")).toBeInTheDocument();
  expect(copied).toEqual([linkFor("new-token-1")]);
});

test("an Owner can invite by link only, without sending an email", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const api = fakeInvitesApi({ pending: [] });
  renderStudio(membersPath);
  await screen.findByText("No pending invites.");

  await inviteSomeone("grace@example.test", { sendEmail: false });

  expect(await screen.findByRole("status")).toHaveTextContent("Copy the link and send it to grace@example.test.");
  expect(api.created).toEqual([{ email: "grace@example.test", role: "editor", send_email: false }]);
});

test("when the email can't be sent, the Owner is told to copy the link", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeInvitesApi({ pending: [], emailSent: false });
  stubClipboard(() => Promise.reject(new Error("denied")));
  renderStudio(membersPath);
  await screen.findByText("No pending invites.");

  await inviteSomeone("grace@example.test");

  const result = await screen.findByRole("status");
  expect(result).toHaveTextContent("The email to grace@example.test couldn't be sent. Copy the link and send it yourself.");
  await userEvent.click(within(result).getByRole("button", { name: "Copy link" }));
  expect(await within(result).findByText("Couldn't copy. Select the link and copy it yourself.")).toBeInTheDocument();
});

test.each([
  [409, { detail: "That person is already a Member of this Organisation" }, "That person is already a Member of this Organisation"],
  [409, {}, "Something went wrong. Try again."],
  [422, { detail: [] }, "Enter a valid email address."],
  [500, null, "Something went wrong. Try again."],
])("a refused invite (%i) shows why", async (status, body, message) => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeInvitesApi({ pending: [] });
  server.use(
    http.post("*/api/organisations/:organisationId/invites", () =>
      body === null ? new HttpResponse(null, { status }) : HttpResponse.json(body, { status }),
    ),
  );
  renderStudio(membersPath);
  await screen.findByText("No pending invites.");

  await inviteSomeone("grace@example.test");

  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

test("an unreachable API while inviting says to try again", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeInvitesApi({ pending: [] });
  server.use(http.post("*/api/organisations/:organisationId/invites", () => HttpResponse.error()));
  renderStudio(membersPath);
  await screen.findByText("No pending invites.");

  await inviteSomeone("grace@example.test");

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("a duplicate invite says there is one pending already", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeInvitesApi();
  renderStudio(membersPath);
  await screen.findByRole("table", { name: "Pending invites" });

  await inviteSomeone("grace@example.test");

  expect(await screen.findByRole("alert")).toHaveTextContent("That email already has a pending invite.");
});

test("the invite button shows progress while the invite is sent", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeInvitesApi({ pending: [] });
  server.use(
    http.post("*/api/organisations/:organisationId/invites", async () => {
      await delay("infinite");
      return HttpResponse.json({});
    }),
  );
  renderStudio(membersPath);
  await screen.findByText("No pending invites.");

  await inviteSomeone("grace@example.test");

  expect(await screen.findByRole("button", { name: "Inviting…" })).toBeDisabled();
});

test("an Owner revokes a pending invite", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const api = fakeInvitesApi();
  renderStudio(membersPath);
  await screen.findByRole("table", { name: "Pending invites" });

  await userEvent.click(screen.getByRole("button", { name: "Revoke invite for grace@example.test" }));

  expect(api.revoked).toEqual([graceInvite.id]);
  await within(screen.getByRole("table", { name: "Pending invites" })).findByRole("cell", { name: "Owner" });
  await expect.poll(pendingRows).toEqual([["charles@example.test", "Owner", "Ada Lovelace", "Expired"]]);
});

test("an Owner gets a new link for an expired invite", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const api = fakeInvitesApi();
  renderStudio(membersPath);
  await screen.findByRole("table", { name: "Pending invites" });

  await userEvent.click(screen.getByRole("button", { name: "New link for charles@example.test" }));

  const result = await screen.findByRole("status");
  expect(result).toHaveTextContent("Copy the link and send it to charles@example.test.");
  expect(within(result).getByLabelText("Invite link for charles@example.test")).toHaveValue(linkFor("renewed-token-1"));
  expect(result).toHaveTextContent("expires on 2026-06-20");
  expect(api.renewed).toEqual([expiredInvite.id]);
  await expect.poll(pendingRows).toEqual([
    ["grace@example.test", "Editor", "Ada Lovelace", "2026-06-08"],
    ["charles@example.test", "Owner", "Ada Lovelace", "2026-06-20"],
  ]);
});

test.each(["renew", "revoke"])("a failed %s says the invite may have changed", async (action) => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeInvitesApi();
  server.use(
    http.post("*/api/organisations/:organisationId/invites/:inviteId/renew", () =>
      HttpResponse.json({ detail: "Not found" }, { status: 404 }),
    ),
    http.delete("*/api/organisations/:organisationId/invites/:inviteId", () =>
      HttpResponse.json({ detail: "Not found" }, { status: 404 }),
    ),
  );
  renderStudio(membersPath);
  await screen.findByRole("table", { name: "Pending invites" });

  const name = action === "renew" ? "New link for grace@example.test" : "Revoke invite for grace@example.test";
  await userEvent.click(screen.getByRole("button", { name }));

  expect(await screen.findByRole("alert")).toHaveTextContent("The invite may have been accepted or revoked already.");
});

test("the pending list shows its loading and error states", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  server.use(
    http.get("*/api/organisations/:organisationId/invites", async () => {
      await delay(50);
      return HttpResponse.json({ detail: "boom" }, { status: 500 });
    }),
  );
  renderStudio(membersPath);

  expect(await screen.findByText("Loading invites…")).toBeInTheDocument();
  expect(await screen.findByText("The pending invites could not be loaded. Try again shortly.")).toBeInTheDocument();
});
