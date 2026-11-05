import type { Schemas } from "@studio/api-client";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { fakeAuthApi } from "../test/auth";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

async function signIn(password = "correct horse battery") {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Email"), "ada@example.test");
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

test("signing in opens the Member's Organisation", async () => {
  const { requests } = fakeAuthApi();
  renderStudio("/sign-in");

  await signIn();

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  expect(requests).toEqual([
    { route: "sign-in", body: { email: "ada@example.test", password: "correct horse battery" } },
  ]);
});

test("says the email or password is incorrect without saying which", async () => {
  server.use(
    http.post("*/api/auth/sign-in", () =>
      HttpResponse.json({ detail: "Email or password is incorrect" }, { status: 401 }),
    ),
  );
  renderStudio("/sign-in");

  await signIn("wrong password");

  expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
  expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
});

function throttle(body: Schemas["ThrottledResponse"]) {
  server.use(
    http.post("*/api/auth/sign-in", () =>
      HttpResponse.json(body, { status: 429, headers: { "Retry-After": String(body.retry_after_seconds) } }),
    ),
  );
}

test("explains a lockout and how long it lasts", async () => {
  throttle({ detail: "Too many failed sign-in attempts", locked: true, retry_after_seconds: 900 });
  renderStudio("/sign-in");

  await signIn();

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Too many failed sign-in attempts. Sign-in is locked for 15 minutes. Try again after that.",
  );
  expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
});

test("rounds a lockout's remaining time up to whole minutes", async () => {
  throttle({ detail: "Too many failed sign-in attempts", locked: true, retry_after_seconds: 61 });
  renderStudio("/sign-in");

  await signIn();

  expect(await screen.findByRole("alert")).toHaveTextContent("Sign-in is locked for 2 minutes.");
});

test("says a lockout ending within the minute lasts 1 minute", async () => {
  throttle({ detail: "Too many failed sign-in attempts", locked: true, retry_after_seconds: 5 });
  renderStudio("/sign-in");

  await signIn();

  expect(await screen.findByRole("alert")).toHaveTextContent("Sign-in is locked for 1 minute.");
});

test("asks the Member to wait out a short delay", async () => {
  throttle({ detail: "Too many failed sign-in attempts", locked: false, retry_after_seconds: 4 });
  renderStudio("/sign-in");

  await signIn();

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Too many failed sign-in attempts. Wait 4 seconds, then try again.",
  );
});

test("says 1 second for a one-second delay", async () => {
  throttle({ detail: "Too many failed sign-in attempts", locked: false, retry_after_seconds: 1 });
  renderStudio("/sign-in");

  await signIn();

  expect(await screen.findByRole("alert")).toHaveTextContent("Wait 1 second, then try again.");
});

test("reports a 429 without the throttling details as an unexpected failure", async () => {
  server.use(http.post("*/api/auth/sign-in", () => new HttpResponse("Slow down", { status: 429 })));
  renderStudio("/sign-in");

  await signIn();

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("reports a 429 with other JSON as an unexpected failure", async () => {
  server.use(http.post("*/api/auth/sign-in", () => HttpResponse.json({ detail: "Slow down" }, { status: 429 })));
  renderStudio("/sign-in");

  await signIn();

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("reports an unreachable API as an unexpected failure", async () => {
  server.use(http.post("*/api/auth/sign-in", () => HttpResponse.error()));
  renderStudio("/sign-in");

  await signIn();

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("reports an unexpected failure", async () => {
  server.use(http.post("*/api/auth/sign-in", () => new HttpResponse("Bad gateway", { status: 502 })));
  renderStudio("/sign-in");

  await signIn();

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("shows progress while signing in", async () => {
  server.use(http.post("*/api/auth/sign-in", () => delay("infinite")));
  renderStudio("/sign-in");

  await signIn();

  expect(await screen.findByRole("button", { name: "Signing in…" })).toBeDisabled();
});

test("links to sign-up and to the system status page", async () => {
  renderStudio("/sign-in");

  expect(await screen.findByRole("link", { name: "Create an account" })).toHaveAttribute("href", "/sign-up");
  await userEvent.click(screen.getByRole("link", { name: "System status" }));

  expect(await screen.findByRole("heading", { name: "System status" })).toBeInTheDocument();
});
