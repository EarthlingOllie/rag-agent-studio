import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi, type Session } from "../test/auth";
import { fakeAcceptApi, invitedOrganisation, joined, previewFor } from "../test/invites";
import { sidebar } from "../test/navigation";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const TOKEN = "invite-token-1";
const path = `/accept-invite?token=${TOKEN}`;
const INVALID = "This invite link is invalid or has expired. Ask an Owner of the Organisation for a new one.";

const newcomer: Session = {
  member: { id: "6a1b0c58-0d6e-4c1b-9d1e-1f1a6c0f0a77", name: "Grace Hopper", email: "grace@example.test", mfa_enabled: false },
  organisations: [{ ...invitedOrganisation, role: "editor", mfa_required: false }],
  active_organisation_id: invitedOrganisation.id,
};

async function expectProjectsOf(organisationName: string) {
  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  expect(within(await sidebar()).getByText(organisationName)).toBeInTheDocument();
}

test("a person without an account creates one and joins in one step", async () => {
  fakeAuthApi();
  const api = fakeAcceptApi({ token: TOKEN, preview: previewFor("grace@example.test"), accepted: newcomer });
  renderStudio(path);

  expect(await screen.findByRole("heading", { name: "Join Difference Engines" })).toBeInTheDocument();
  expect(screen.getByText(/Charles Babbage invited/)).toHaveTextContent(
    "Charles Babbage invited grace@example.test to join Difference Engines as an Editor.",
  );
  expect(screen.getByText("Role: Editor")).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Your name"), "Grace Hopper");
  await userEvent.type(screen.getByLabelText("Password"), "a long enough password");
  await userEvent.click(screen.getByRole("button", { name: "Create account and join" }));

  await expectProjectsOf("Difference Engines");
  expect(api.requests).toEqual([
    { route: "sign-up", body: { token: TOKEN, name: "Grace Hopper", password: "a long enough password" } },
  ]);
});

test.each([
  [400, INVALID],
  [409, "An account with this email already exists. Sign in to accept the invite."],
  [422, "Enter your name and a password of at least 12 characters."],
  [500, "Something went wrong. Try again."],
])("creating the account can be refused (%i)", async (status, message) => {
  fakeAuthApi();
  fakeAcceptApi({ token: TOKEN, preview: previewFor("grace@example.test"), accepted: { status } });
  renderStudio(path);

  await userEvent.type(await screen.findByLabelText("Your name"), "Grace Hopper");
  await userEvent.type(screen.getByLabelText("Password"), "a long enough password");
  await userEvent.click(screen.getByRole("button", { name: "Create account and join" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(message);
});

test("an unreachable API while creating the account says to try again", async () => {
  fakeAuthApi();
  fakeAcceptApi({ token: TOKEN, preview: previewFor("grace@example.test") });
  server.use(http.post("*/api/invites/sign-up", () => HttpResponse.error()));
  renderStudio(path);

  await userEvent.type(await screen.findByLabelText("Your name"), "Grace Hopper");
  await userEvent.type(screen.getByLabelText("Password"), "a long enough password");
  await userEvent.click(screen.getByRole("button", { name: "Create account and join" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("a signed-in Member with the invited email joins with one click", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const api = fakeAcceptApi({
    token: TOKEN,
    preview: previewFor(adaSession.member.email, { account_exists: true, role: "owner" }),
    accepted: joined(adaSession, "owner"),
  });
  renderStudio(path);

  expect(await screen.findByText(/as an Owner/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Join Difference Engines" }));

  await expectProjectsOf("Difference Engines");
  expect(api.requests).toEqual([{ route: "accept", body: { token: TOKEN } }]);
});

test.each([
  [400, INVALID],
  [500, "Something went wrong. Try again."],
])("joining can be refused (%i)", async (status, message) => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeAcceptApi({
    token: TOKEN,
    preview: previewFor(adaSession.member.email, { account_exists: true }),
    accepted: { status },
  });
  renderStudio(path);

  await userEvent.click(await screen.findByRole("button", { name: "Join Difference Engines" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(message);
});

test("the join button shows progress", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeAcceptApi({ token: TOKEN, preview: previewFor(adaSession.member.email, { account_exists: true }) });
  server.use(
    http.post("*/api/invites/accept", async () => {
      await delay("infinite");
      return HttpResponse.json({});
    }),
  );
  renderStudio(path);

  await userEvent.click(await screen.findByRole("button", { name: "Join Difference Engines" }));

  expect(await screen.findByRole("button", { name: "Joining…" })).toBeDisabled();
});

test("a Member signed in with another email is told to sign out first", async () => {
  const auth = fakeAuthApi({ signedInAs: adaSession });
  fakeAcceptApi({ token: TOKEN, preview: previewFor("grace@example.test") });
  renderStudio(path);

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "You're signed in as ada@example.test. Sign out, then open the link again to accept as grace@example.test.",
  );
  await userEvent.click(screen.getByRole("button", { name: "Sign out" }));

  expect(await screen.findByRole("button", { name: "Create account and join" })).toBeInTheDocument();
  expect(auth.requests).toEqual([{ route: "sign-out", body: null }]);
});

test("a failed sign-out says so", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeAcceptApi({ token: TOKEN, preview: previewFor("grace@example.test") });
  server.use(http.post("*/api/auth/sign-out", () => new HttpResponse(null, { status: 500 })));
  renderStudio(path);

  await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));

  expect(await screen.findByText("Sign-out failed. Try again.")).toBeInTheDocument();
});

test("a signed-out person with an account signs in on the page, then joins", async () => {
  const auth = fakeAuthApi({ account: adaSession });
  fakeAcceptApi({
    token: TOKEN,
    preview: previewFor(adaSession.member.email, { account_exists: true }),
    accepted: joined(adaSession),
  });
  renderStudio(path);

  expect(await screen.findByText("You already have an account. Sign in to accept.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Forgot your password?" })).toHaveAttribute("href", "/forgot-password");
  await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  await userEvent.click(await screen.findByRole("button", { name: "Join Difference Engines" }));

  await expectProjectsOf("Difference Engines");
  expect(auth.requests).toEqual([
    { route: "sign-in", body: { email: adaSession.member.email, password: "correct horse battery" } },
  ]);
});

test.each([
  [401, { detail: "no" }, "Email or password is incorrect."],
  [429, { detail: "no", locked: true, retry_after_seconds: 900 }, "Too many failed sign-in attempts. Sign-in is locked for 15 minutes."],
  [500, { detail: "no" }, "Something went wrong. Try again."],
])("signing in on the page can fail (%i)", async (status, body, message) => {
  fakeAuthApi();
  fakeAcceptApi({ token: TOKEN, preview: previewFor(adaSession.member.email, { account_exists: true }) });
  server.use(http.post("*/api/auth/sign-in", () => HttpResponse.json(body, { status })));
  renderStudio(path);

  await userEvent.type(await screen.findByLabelText("Password"), "wrong password!");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(message);
});

function mfaSignIn(verify: () => Response | Promise<Response>) {
  let signedIn = false;
  server.use(
    http.get("*/api/auth/me", () =>
      signedIn ? HttpResponse.json(adaSession) : HttpResponse.json({ detail: "Not signed in" }, { status: 401 }),
    ),
    http.post("*/api/auth/sign-in", () => HttpResponse.json({ mfa_required: true }, { status: 202 })),
    http.post("*/api/auth/mfa/verify", async () => {
      const response = await verify();
      if (response.ok) signedIn = true;
      return response;
    }),
  );
}

test("a Member with MFA enters a code on the page before joining", async () => {
  mfaSignIn(() => HttpResponse.json(adaSession));
  fakeAcceptApi({
    token: TOKEN,
    preview: previewFor(adaSession.member.email, { account_exists: true }),
    accepted: joined(adaSession),
  });
  renderStudio(path);

  await userEvent.type(await screen.findByLabelText("Password"), "correct horse battery");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  await userEvent.type(await screen.findByLabelText("Authentication code"), "123456");
  await userEvent.click(screen.getByRole("button", { name: "Verify" }));
  await userEvent.click(await screen.findByRole("button", { name: "Join Difference Engines" }));

  await expectProjectsOf("Difference Engines");
});

test.each([
  [400, "That code is incorrect. Try again."],
  [401, "Your sign-in timed out. Reload the page to sign in again."],
  [500, "Something went wrong. Try again."],
])("a refused MFA code on the page says why (%i)", async (status, message) => {
  mfaSignIn(() => HttpResponse.json({ detail: "no" }, { status }));
  fakeAcceptApi({ token: TOKEN, preview: previewFor(adaSession.member.email, { account_exists: true }) });
  renderStudio(path);

  await userEvent.type(await screen.findByLabelText("Password"), "correct horse battery");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  await userEvent.type(await screen.findByLabelText("Authentication code"), "000000");
  await userEvent.click(screen.getByRole("button", { name: "Verify" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(message);
});

test("an invalid, used, revoked or expired link says so", async () => {
  fakeAuthApi();
  fakeAcceptApi({ token: TOKEN, preview: { status: 404 } });
  renderStudio(path);

  expect(await screen.findByRole("alert")).toHaveTextContent(INVALID);
});

test("a link without a token is incomplete", async () => {
  fakeAuthApi();
  renderStudio("/accept-invite");

  expect(await screen.findByRole("alert")).toHaveTextContent("This invite link is incomplete.");
  expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/sign-in");
});

test("the page shows loading, then a lookup failure", async () => {
  fakeAuthApi();
  server.use(
    http.post("*/api/invites/lookup", async () => {
      await delay(50);
      return new HttpResponse(null, { status: 500 });
    }),
  );
  renderStudio(path);

  expect(await screen.findByRole("status", { name: "Loading the invite" })).toHaveAttribute("aria-busy", "true");
  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("the page says when the API can't be reached for the session", async () => {
  fakeAcceptApi({ token: TOKEN, preview: previewFor("grace@example.test") });
  server.use(http.get("*/api/auth/me", () => new HttpResponse(null, { status: 500 })));
  renderStudio(path);

  expect(await screen.findByRole("alert")).toHaveTextContent("The Studio could not reach the API. Try again shortly.");
});
