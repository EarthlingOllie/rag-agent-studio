import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { GOOD_CODE, fakeMfaSignIn } from "../test/mfa";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

async function passwordStep() {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Email"), "ada@example.test");
  await user.type(screen.getByLabelText("Password"), "correct horse battery");
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  return user;
}

async function enterCode(code: string, label = "Authentication code") {
  const user = userEvent.setup();
  const input = await screen.findByLabelText(label);
  await user.clear(input);
  await user.type(input, code);
  await user.click(screen.getByRole("button", { name: "Verify" }));
}

test("a Member with MFA is asked for a code after the password, then signed in", async () => {
  const { requests } = fakeMfaSignIn();
  renderStudio("/sign-in");

  await passwordStep();

  expect(await screen.findByRole("heading", { name: "Two-factor authentication" })).toBeInTheDocument();
  expect(screen.getByText("Enter the 6-digit code from your authenticator app.")).toBeInTheDocument();
  expect(screen.getByLabelText("Authentication code")).toHaveAttribute("autocomplete", "one-time-code");
  await enterCode(GOOD_CODE);

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  expect(requests).toEqual([
    { route: "sign-in", body: { email: "ada@example.test", password: "correct horse battery" } },
    { route: "verify", body: { code: GOOD_CODE } },
  ]);
});

test("a wrong code says so and lets the Member try again", async () => {
  fakeMfaSignIn();
  renderStudio("/sign-in/mfa");

  await enterCode("000000");

  expect(await screen.findByRole("alert")).toHaveTextContent("That code is incorrect. Try again.");
  await enterCode(GOOD_CODE);
  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
});

test("a recovery code can be used instead, and the Member can switch back", async () => {
  const { requests } = fakeMfaSignIn();
  renderStudio("/sign-in/mfa");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "Use a recovery code instead" }));
  expect(screen.getByText(/Enter one of the recovery codes you saved/)).toBeInTheDocument();
  await enterCode("ZZZZ-ZZZZ-ZZZZ-ZZZZ", "Recovery code");
  expect(await screen.findByRole("alert")).toHaveTextContent("That recovery code is incorrect or already used.");

  await user.click(screen.getByRole("button", { name: "Use your authenticator app instead" }));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Authentication code")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Use a recovery code instead" }));
  await enterCode("AAAA-BBBB-CCCC-DDDD", "Recovery code");

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  expect(requests.at(-1)).toEqual({ route: "verify", body: { code: "AAAA-BBBB-CCCC-DDDD" } });
});

test("an expired sign-in sends the Member back to sign in", async () => {
  server.use(
    http.post("*/api/auth/mfa/verify", () => HttpResponse.json({ detail: "Sign in again" }, { status: 401 })),
  );
  renderStudio("/sign-in/mfa");

  await enterCode(GOOD_CODE);

  expect(await screen.findByRole("heading", { name: "Sign-in expired" })).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent(/timed out or had too many wrong codes/);
  await userEvent.click(screen.getByRole("link", { name: "Sign in again" }));
  expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
});

test("reports an unexpected failure", async () => {
  server.use(http.post("*/api/auth/mfa/verify", () => new HttpResponse("Bad gateway", { status: 502 })));
  renderStudio("/sign-in/mfa");

  await enterCode(GOOD_CODE);

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("shows progress while verifying", async () => {
  server.use(http.post("*/api/auth/mfa/verify", () => delay("infinite")));
  renderStudio("/sign-in/mfa");

  await enterCode(GOOD_CODE);

  expect(await screen.findByRole("button", { name: "Verifying…" })).toBeDisabled();
});

test("a Member on the wrong account can go back to sign in", async () => {
  renderStudio("/sign-in/mfa");

  await userEvent.click(await screen.findByRole("link", { name: "Sign in again" }));

  expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
});
