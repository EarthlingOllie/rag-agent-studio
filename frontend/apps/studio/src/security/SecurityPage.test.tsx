import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeMfaApi, GOOD_CODE, PASSWORD, QR_CODE, recoveryCodes, SECRET } from "../test/mfa";
import { openSection } from "../test/navigation";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const securityPath = `/organisations/${organisationId}/security`;

function openSecurity() {
  fakeAuthApi({ signedInAs: adaSession });
  renderStudio(securityPath);
}

async function fillAndSubmit(form: string, values: Record<string, string>, button: string) {
  const user = userEvent.setup();
  const scope = within(await screen.findByRole("form", { name: form }));
  for (const [label, value] of Object.entries(values)) {
    const input = scope.getByLabelText(label);
    await user.clear(input);
    await user.type(input, value);
  }
  await user.click(scope.getByRole("button", { name: button }));
}

test("the Security page is in the account menu", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeMfaApi();
  renderStudio("/");

  await screen.findByRole("heading", { name: "Projects" });
  await openSection("Account", "Security");

  expect(await screen.findByRole("heading", { name: "Security", level: 1 })).toBeInTheDocument();
});

test("a Member enrols with a QR code and a confirming code, and sees the recovery codes once", async () => {
  const { requests } = fakeMfaApi();
  openSecurity();
  const user = userEvent.setup();

  expect(await screen.findByText(/Protect your account/)).toHaveTextContent("Off.");
  await user.click(screen.getByRole("button", { name: "Set up two-factor authentication" }));

  expect(await screen.findByRole("img", { name: "QR code for your authenticator app" })).toHaveAttribute("src", QR_CODE);
  // The QR code and its fallback key sit on their own card inside the set-up card.
  const qrCard = within(
    within(screen.getByRole("region", { name: "Set up your authenticator app" })).getByRole("figure", { name: /Can't scan it/ }),
  );
  expect(qrCard.getByRole("img", { name: "QR code for your authenticator app" })).toBeInTheDocument();
  expect(qrCard.getByText(SECRET)).toBeInTheDocument();
  await fillAndSubmit("Confirm your authenticator app", { "Code from your app": GOOD_CODE }, "Turn on");

  const list = within(await screen.findByRole("region", { name: "Save your recovery codes" })).getByRole("list", {
    name: "Recovery codes",
  });
  expect(within(list).getAllByRole("listitem").map((item) => item.textContent)).toEqual(recoveryCodes("A"));
  expect(screen.getByText(/they won't be shown again/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "I've saved my recovery codes" }));

  expect(await screen.findByText(/Signing in asks for a code/)).toHaveTextContent("On.");
  expect(screen.getByText(/10 recovery codes left/)).toBeInTheDocument();
  expect(screen.queryByText(recoveryCodes("A")[0] ?? "")).not.toBeInTheDocument();
  expect(requests).toEqual([
    { route: "enrolment", body: null },
    { route: "confirm", body: { code: GOOD_CODE } },
  ]);
});

test("a wrong confirming code is refused, and enrolment can be cancelled", async () => {
  fakeMfaApi();
  openSecurity();
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Set up two-factor authentication" }));

  await fillAndSubmit("Confirm your authenticator app", { "Code from your app": "000000" }, "Turn on");

  expect(await screen.findByRole("alert")).toHaveTextContent("That code is incorrect. Check your app and try again.");
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(await screen.findByRole("button", { name: "Set up two-factor authentication" })).toBeInTheDocument();
});

test("shows progress while turning MFA on", async () => {
  fakeMfaApi();
  server.use(http.post("*/api/auth/mfa/enrolment/confirm", () => delay("infinite")));
  openSecurity();
  await userEvent.click(await screen.findByRole("button", { name: "Set up two-factor authentication" }));

  await fillAndSubmit("Confirm your authenticator app", { "Code from your app": GOOD_CODE }, "Turn on");

  expect(await screen.findByRole("button", { name: "Turning on…" })).toBeDisabled();
});

test("reports a failure to start enrolment", async () => {
  fakeMfaApi();
  server.use(http.post("*/api/auth/mfa/enrolment", () => new HttpResponse(null, { status: 500 })));
  openSecurity();

  await userEvent.click(await screen.findByRole("button", { name: "Set up two-factor authentication" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("says when the security settings cannot be loaded", async () => {
  server.use(http.get("*/api/auth/mfa", () => new HttpResponse(null, { status: 500 })));
  openSecurity();

  expect(await screen.findByRole("alert")).toHaveTextContent("Your security settings could not be loaded.");
});

test("shows that the settings are loading", async () => {
  server.use(http.get("*/api/auth/mfa", () => delay("infinite")));
  openSecurity();

  expect(await screen.findByRole("status", { name: "Loading your security settings" })).toHaveAttribute("aria-busy", "true");
});

test("a Member with MFA makes new recovery codes with a code", async () => {
  const { requests } = fakeMfaApi({ enabled: true, remaining: 1 });
  openSecurity();

  expect(await screen.findByText(/1 recovery code left\./)).toBeInTheDocument();
  await fillAndSubmit("Make new recovery codes", { "Code from your app": "000000" }, "Make new recovery codes");
  expect(await screen.findByRole("alert")).toHaveTextContent("That code is incorrect. Try again.");
  await fillAndSubmit("Make new recovery codes", { "Code from your app": GOOD_CODE }, "Make new recovery codes");

  const list = await screen.findByRole("list", { name: "Recovery codes" });
  expect(within(list).getAllByRole("listitem")).toHaveLength(10);
  expect(list).toHaveTextContent(recoveryCodes("C")[0] ?? "");
  await userEvent.click(screen.getByRole("button", { name: "I've saved my recovery codes" }));
  expect(await screen.findByText(/10 recovery codes left/)).toBeInTheDocument();
  expect(requests.map((request) => request.route)).toEqual(["recovery-codes", "recovery-codes"]);
});

test("turning MFA off needs the password and a code", async () => {
  const { requests } = fakeMfaApi({ enabled: true });
  openSecurity();
  const form = "Turn off two-factor authentication";
  const codeLabel = "Code from your app or a recovery code";

  await fillAndSubmit(form, { Password: "wrong password", [codeLabel]: GOOD_CODE }, "Turn off");
  expect(await screen.findByRole("alert")).toHaveTextContent("Your password or code is incorrect.");
  await fillAndSubmit(form, { Password: PASSWORD, [codeLabel]: GOOD_CODE }, "Turn off");

  expect(await screen.findByRole("button", { name: "Set up two-factor authentication" })).toBeInTheDocument();
  expect(requests).toEqual([
    { route: "disable", body: { password: "wrong password", code: GOOD_CODE } },
    { route: "disable", body: { password: PASSWORD, code: GOOD_CODE } },
  ]);
});

test("reports an unexpected failure turning MFA off", async () => {
  fakeMfaApi({ enabled: true });
  server.use(http.post("*/api/auth/mfa/disable", () => new HttpResponse(null, { status: 502 })));
  openSecurity();

  await fillAndSubmit(
    "Turn off two-factor authentication",
    { Password: PASSWORD, "Code from your app or a recovery code": GOOD_CODE },
    "Turn off",
  );

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});
