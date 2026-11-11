import type { Schemas } from "@studio/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { sidebar } from "../test/navigation";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

async function fillInSignUp() {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Your name"), "Ada Lovelace");
  await user.type(screen.getByLabelText("Email"), "ada@example.test");
  await user.type(screen.getByLabelText("Password"), "correct horse battery");
  await user.type(screen.getByLabelText("Organisation name"), "Analytical Engines");
  await user.click(screen.getByRole("button", { name: "Create account" }));
}

function failSignUp(status: number, body: Schemas["ErrorResponse"] = { detail: "Refused" }) {
  server.use(http.post("*/api/auth/sign-up", () => HttpResponse.json(body, { status })));
}

test("signing up opens the new Organisation in the signed-in shell", async () => {
  const { requests } = fakeAuthApi();
  renderStudio("/sign-up");

  await fillInSignUp();

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  expect(within(await sidebar()).getByText("Analytical Engines")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Ada Lovelace, Account" })).toBeInTheDocument();
  expect(requests).toEqual([
    {
      route: "sign-up",
      body: {
        name: "Ada Lovelace",
        email: "ada@example.test",
        password: "correct horse battery",
        organisation_name: "Analytical Engines",
      },
    },
  ]);
});

test("asks for a password of at least 12 characters", async () => {
  renderStudio("/sign-up");

  const password = await screen.findByLabelText("Password");

  expect(password).toHaveAttribute("minLength", "12");
  expect(password).toBeRequired();
  expect(screen.getByText("At least 12 characters.")).toBeInTheDocument();
});

test("says when the email already has an account", async () => {
  failSignUp(409, { detail: "Email already registered" });
  renderStudio("/sign-up");

  await fillInSignUp();

  expect(await screen.findByRole("alert")).toHaveTextContent("An account with this email already exists. Sign in instead.");
});

test("asks the visitor to check their details when the API rejects them", async () => {
  failSignUp(422);
  renderStudio("/sign-up");

  await fillInSignUp();

  expect(await screen.findByRole("alert")).toHaveTextContent("Check your details");
});

test("reports an unexpected failure without losing what was typed", async () => {
  server.use(http.post("*/api/auth/sign-up", () => HttpResponse.error()));
  renderStudio("/sign-up");

  await fillInSignUp();

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
  expect(screen.getByLabelText("Organisation name")).toHaveValue("Analytical Engines");
});

test("shows progress while the account is being created", async () => {
  server.use(http.post("*/api/auth/sign-up", () => delay("infinite")));
  renderStudio("/sign-up");

  await fillInSignUp();

  expect(await screen.findByRole("button", { name: "Creating account…" })).toBeDisabled();
});

test("links to sign-in for people who already have an account", async () => {
  renderStudio("/sign-up");

  await userEvent.click(await screen.findByRole("link", { name: "Sign in" }));

  expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
});

test("a signed-up Member is shown the shell when they come back", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio("/");

  await waitFor(() => {
    expect(screen.getByRole("heading", { name: "Projects" })).toBeInTheDocument();
  });
});
