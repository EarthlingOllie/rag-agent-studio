import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { fakeAccountApi } from "../test/account";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

async function requestLink(email = "ada@example.test") {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Email"), email);
  await user.click(screen.getByRole("button", { name: "Send reset link" }));
}

test("a Member who forgot their password asks for a reset link from the sign-in screen", async () => {
  const { requests } = fakeAccountApi();
  renderStudio("/sign-in");

  await userEvent.click(await screen.findByRole("link", { name: "Forgot your password?" }));
  expect(await screen.findByRole("heading", { name: "Reset your password" })).toBeInTheDocument();
  await requestLink();

  expect(await screen.findByRole("status")).toHaveTextContent(
    "If that email is registered, a reset link is on its way. Check your inbox.",
  );
  expect(screen.queryByRole("button", { name: "Send reset link" })).not.toBeInTheDocument();
  expect(requests).toEqual([{ route: "password-reset", body: { email: "ada@example.test" } }]);
  await userEvent.click(screen.getByRole("link", { name: "Back to sign in" }));
  expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
});

test("reports an unexpected failure", async () => {
  server.use(http.post("*/api/auth/password-reset", () => new HttpResponse(null, { status: 502 })));
  renderStudio("/forgot-password");

  await requestLink();

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("asks for a valid email when the API refuses it", async () => {
  server.use(http.post("*/api/auth/password-reset", () => HttpResponse.json({ detail: [] }, { status: 422 })));
  renderStudio("/forgot-password");

  await requestLink("ada@localhost");

  expect(await screen.findByRole("alert")).toHaveTextContent("Enter a valid email address.");
});

test("shows progress while sending", async () => {
  server.use(http.post("*/api/auth/password-reset", () => delay("infinite")));
  renderStudio("/forgot-password");

  await requestLink();

  expect(await screen.findByRole("button", { name: "Sending…" })).toBeDisabled();
});
