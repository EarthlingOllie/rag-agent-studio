import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
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

test("the shell links the Projects list and Organisation settings", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  expect(await screen.findByText(/No Projects yet/)).toBeInTheDocument();
  const nav = screen.getByRole("navigation", { name: "Organisation" });

  await userEvent.click(within(nav).getByRole("link", { name: "Organisation settings" }));

  expect(await screen.findByRole("heading", { name: "Organisation settings" })).toBeInTheDocument();
  await userEvent.click(within(nav).getByRole("link", { name: "Projects" }));
  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
});

test("signing out ends the session and returns to sign-in", async () => {
  const { requests } = fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");

  await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));

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

  await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Sign-out failed. Try again.");
  expect(screen.getByRole("heading", { name: "Projects" })).toBeInTheDocument();
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
  expect(screen.queryByRole("navigation", { name: "Organisation" })).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("link", { name: "Go to your Organisation" }));

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
});

test("the status page links back to the Studio", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/status");

  await userEvent.click(await screen.findByRole("link", { name: "RAG Agent Studio" }));

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
});
