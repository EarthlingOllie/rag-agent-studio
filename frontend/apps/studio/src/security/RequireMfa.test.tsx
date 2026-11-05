import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, type Session } from "../test/auth";
import { fakeMfaApi, GOOD_CODE, PASSWORD } from "../test/mfa";
import { fakeMfaPolicyApi, OWNER_WITHOUT_MFA } from "../test/mfaPolicy";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const organisationPath = (page: string) => `/organisations/${organisationId}/${page}`;
const REQUIRED_NOTICE = "Analytical Engines requires two-factor authentication. Set it up to continue.";

function session({ mfaEnabled, mfaRequired, role = "owner" }: {
  mfaEnabled: boolean;
  mfaRequired: boolean;
  role?: "owner" | "editor";
}): Session {
  return {
    ...adaSession,
    member: { ...adaSession.member, mfa_enabled: mfaEnabled },
    organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role, mfa_required: mfaRequired })),
  };
}

function organisationNav() {
  return screen.findByRole("navigation", { name: "Organisation" });
}

test("a Member without MFA opening an Organisation that requires it is guided through enrolment first", async () => {
  const { requests } = fakeMfaApi();
  // MFA is on once the enrolment has been confirmed with a good code.
  const enrolled = () => requests.some((request) => request.route === "confirm" && (request.body as { code: string }).code === GOOD_CODE);
  server.use(
    http.get("*/api/auth/me", () => HttpResponse.json(session({ mfaEnabled: enrolled(), mfaRequired: true }))),
  );
  renderStudio(organisationPath("projects"));
  const user = userEvent.setup();

  expect(await screen.findByRole("heading", { name: "Security", level: 1 })).toBeInTheDocument();
  expect(screen.getByText(REQUIRED_NOTICE)).toBeInTheDocument();
  const nav = await organisationNav();
  expect(within(nav).queryByRole("link", { name: "Projects" })).not.toBeInTheDocument();
  expect(within(nav).queryByRole("link", { name: "Organisation settings" })).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Set up two-factor authentication" }));
  const form = within(await screen.findByRole("form", { name: "Confirm your authenticator app" }));
  await user.type(form.getByLabelText("Code from your app"), GOOD_CODE);
  await user.click(form.getByRole("button", { name: "Turn on" }));
  await user.click(await screen.findByRole("button", { name: "I've saved my recovery codes" }));

  await user.click(await within(await organisationNav()).findByRole("link", { name: "Projects" }));
  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  expect(screen.queryByText(REQUIRED_NOTICE)).not.toBeInTheDocument();
});

test.each(["settings", "settings/members", "profile"])("every page of the Organisation leads to enrolment: %s", async (page) => {
  fakeMfaApi();
  server.use(http.get("*/api/auth/me", () => HttpResponse.json(session({ mfaEnabled: false, mfaRequired: true }))));
  renderStudio(organisationPath(page));

  expect(await screen.findByText(REQUIRED_NOTICE)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Security", level: 1 })).toBeInTheDocument();
});

test("a Member who has MFA uses an Organisation that requires it as usual", async () => {
  server.use(http.get("*/api/auth/me", () => HttpResponse.json(session({ mfaEnabled: true, mfaRequired: true }))));
  renderStudio(organisationPath("projects"));

  expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  expect(screen.queryByText(REQUIRED_NOTICE)).not.toBeInTheDocument();
});

test("an Owner requires MFA in Organisation settings, and can stop requiring it", async () => {
  const api = fakeMfaPolicyApi(session({ mfaEnabled: true, mfaRequired: false }));
  renderStudio(organisationPath("settings"));
  const user = userEvent.setup();

  const policy = within(await screen.findByRole("region", { name: "Two-factor authentication" }));
  expect(policy.getByText(/Members choose whether to use two-factor authentication/)).toBeInTheDocument();
  await user.click(policy.getByRole("button", { name: "Require two-factor authentication" }));

  expect(await policy.findByText(/Every Member must use two-factor authentication/)).toBeInTheDocument();
  await user.click(policy.getByRole("button", { name: "Stop requiring two-factor authentication" }));
  expect(await policy.findByText(/Members choose whether to use two-factor authentication/)).toBeInTheDocument();
  expect(api.requests).toEqual([{ require_mfa: true }, { require_mfa: false }]);
});

test("an Owner without MFA is told to turn it on before requiring it", async () => {
  fakeMfaPolicyApi(session({ mfaEnabled: false, mfaRequired: false }));
  renderStudio(organisationPath("settings"));

  await userEvent.click(await screen.findByRole("button", { name: "Require two-factor authentication" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(OWNER_WITHOUT_MFA);
});

test("reports an unexpected failure changing the policy", async () => {
  fakeMfaPolicyApi(session({ mfaEnabled: true, mfaRequired: false }));
  server.use(http.put("*/api/organisations/:organisationId/mfa-policy", () => new HttpResponse(null, { status: 502 })));
  renderStudio(organisationPath("settings"));

  await userEvent.click(await screen.findByRole("button", { name: "Require two-factor authentication" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("shows progress while the policy changes", async () => {
  fakeMfaPolicyApi(session({ mfaEnabled: true, mfaRequired: false }));
  server.use(http.put("*/api/organisations/:organisationId/mfa-policy", () => delay("infinite")));
  renderStudio(organisationPath("settings"));

  await userEvent.click(await screen.findByRole("button", { name: "Require two-factor authentication" }));

  expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();
});

test("Editors see the policy but can't change it", async () => {
  server.use(
    http.get("*/api/auth/me", () => HttpResponse.json(session({ mfaEnabled: true, mfaRequired: true, role: "editor" }))),
  );
  renderStudio(organisationPath("settings"));

  const policy = within(await screen.findByRole("region", { name: "Two-factor authentication" }));
  expect(policy.getByText(/Every Member must use two-factor authentication/)).toBeInTheDocument();
  expect(policy.getByText("Only Owners can change this.")).toBeInTheDocument();
  expect(policy.queryByRole("button")).not.toBeInTheDocument();
});

test("a Member can't turn MFA off while an Organisation requires it, and is told which", async () => {
  fakeMfaApi({ enabled: true });
  const refusal = "MFA can't be turned off while Analytical Engines requires it.";
  server.use(
    http.get("*/api/auth/me", () => HttpResponse.json(session({ mfaEnabled: true, mfaRequired: true }))),
    http.post("*/api/auth/mfa/disable", () => HttpResponse.json({ detail: refusal }, { status: 409 })),
  );
  renderStudio(organisationPath("security"));
  const user = userEvent.setup();

  const form = within(await screen.findByRole("form", { name: "Turn off two-factor authentication" }));
  await user.type(form.getByLabelText("Password"), PASSWORD);
  await user.type(form.getByLabelText("Code from your app or a recovery code"), GOOD_CODE);
  await user.click(form.getByRole("button", { name: "Turn off" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(refusal);
  expect(screen.getByText(/Signing in asks for a code/)).toHaveTextContent("On.");
});

test("a conflict without a message reads as a generic failure", async () => {
  fakeMfaApi({ enabled: true });
  server.use(
    http.get("*/api/auth/me", () => HttpResponse.json(session({ mfaEnabled: true, mfaRequired: false }))),
    http.post("*/api/auth/mfa/disable", () => new HttpResponse(null, { status: 409 })),
  );
  renderStudio(organisationPath("security"));
  const user = userEvent.setup();

  const form = within(await screen.findByRole("form", { name: "Turn off two-factor authentication" }));
  await user.type(form.getByLabelText("Password"), PASSWORD);
  await user.type(form.getByLabelText("Code from your app or a recovery code"), GOOD_CODE);
  await user.click(form.getByRole("button", { name: "Turn off" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});
