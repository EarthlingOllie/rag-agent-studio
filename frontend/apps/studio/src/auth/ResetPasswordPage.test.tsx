import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { fakeAccountApi, VALID_RESET_TOKEN } from "../test/account";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

async function setPassword(password = "a brand new password") {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("New password"), password);
  await user.click(screen.getByRole("button", { name: "Set new password" }));
}

test("a Member sets a new password from the emailed link, then signs in", async () => {
  const { requests } = fakeAccountApi();
  renderStudio(`/reset-password?token=${VALID_RESET_TOKEN}`);

  expect(await screen.findByRole("heading", { name: "Choose a new password" })).toBeInTheDocument();
  await setPassword();

  expect(await screen.findByRole("status")).toHaveTextContent(
    "Your password has been reset and you've been signed out everywhere.",
  );
  expect(requests).toEqual([
    { route: "password-reset/complete", body: { token: VALID_RESET_TOKEN, password: "a brand new password" } },
  ]);
  await userEvent.click(screen.getByRole("link", { name: "Sign in with your new password" }));
  expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
});

test("an expired or used link says so and offers a new one", async () => {
  fakeAccountApi();
  renderStudio("/reset-password?token=used-up");

  await setPassword();

  expect(await screen.findByRole("alert")).toHaveTextContent("This reset link is invalid or has expired.");
  await userEvent.click(screen.getByRole("link", { name: "Request a new link" }));
  expect(await screen.findByRole("heading", { name: "Reset your password" })).toBeInTheDocument();
});

test("a link without a token offers a new one", async () => {
  renderStudio("/reset-password");

  expect(await screen.findByRole("alert")).toHaveTextContent("This reset link is incomplete.");
  expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Request a new link" })).toHaveAttribute("href", "/forgot-password");
});

test("asks for a longer password when the API refuses it", async () => {
  server.use(
    http.post("*/api/auth/password-reset/complete", () => HttpResponse.json({ detail: [] }, { status: 422 })),
  );
  renderStudio(`/reset-password?token=${VALID_RESET_TOKEN}`);

  await setPassword("twelve chars");

  expect(await screen.findByRole("alert")).toHaveTextContent("Choose a password of at least 12 characters.");
});

test("reports an unexpected failure", async () => {
  server.use(http.post("*/api/auth/password-reset/complete", () => new HttpResponse(null, { status: 500 })));
  renderStudio(`/reset-password?token=${VALID_RESET_TOKEN}`);

  await setPassword();

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("shows progress while saving", async () => {
  server.use(http.post("*/api/auth/password-reset/complete", () => delay("infinite")));
  renderStudio(`/reset-password?token=${VALID_RESET_TOKEN}`);

  await setPassword();

  expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();
});
