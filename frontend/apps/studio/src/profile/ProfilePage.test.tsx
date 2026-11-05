import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { fakeAccountApi } from "../test/account";
import { adaSession } from "../test/auth";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const profilePath = `/organisations/${organisationId}/profile`;

function nameForm() {
  return screen.getByRole("form", { name: "Your name" });
}

function passwordForm() {
  return screen.getByRole("form", { name: "Change password" });
}

async function changePassword(current: string, next = "a brand new password") {
  const user = userEvent.setup();
  const form = await screen.findByRole("form", { name: "Change password" });
  await user.type(within(form).getByLabelText("Current password"), current);
  await user.type(within(form).getByLabelText("New password"), next);
  await user.click(within(form).getByRole("button", { name: "Change password" }));
}

async function rename(name: string) {
  const user = userEvent.setup();
  const field = within(await screen.findByRole("form", { name: "Your name" })).getByLabelText("Name");
  await user.clear(field);
  await user.type(field, name);
  await user.click(within(nameForm()).getByRole("button", { name: "Save name" }));
}

test("the Profile is linked from the header", async () => {
  fakeAccountApi({ signedInAs: adaSession });
  renderStudio("/");

  await userEvent.click(await screen.findByRole("link", { name: "Profile" }));

  expect(await screen.findByRole("heading", { name: "Profile" })).toBeInTheDocument();
  expect(within(nameForm()).getByLabelText("Name")).toHaveValue("Ada Lovelace");
  expect(screen.getByText("ada@example.test")).toBeInTheDocument();
});

test("a Member edits their name and the header shows it", async () => {
  const { requests } = fakeAccountApi({ signedInAs: adaSession });
  renderStudio(profilePath);

  await rename("Ada King");

  expect(await within(nameForm()).findByRole("status")).toHaveTextContent("Name saved.");
  expect(within(screen.getByRole("banner")).getByText("Ada King")).toBeInTheDocument();
  expect(requests).toEqual([{ route: "update-profile", body: { name: "Ada King" } }]);
});

test("a refused name says what is wrong", async () => {
  fakeAccountApi({ signedInAs: adaSession });
  server.use(http.patch("*/api/auth/me", () => HttpResponse.json({ detail: [] }, { status: 422 })));
  renderStudio(profilePath);

  await rename(" ");

  expect(await within(nameForm()).findByRole("alert")).toHaveTextContent("Enter a name of up to 200 characters.");
});

test("a failed name change reports it", async () => {
  fakeAccountApi({ signedInAs: adaSession });
  server.use(http.patch("*/api/auth/me", () => new HttpResponse(null, { status: 500 })));
  renderStudio(profilePath);

  await rename("Ada King");

  expect(await within(nameForm()).findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("shows progress while saving the name", async () => {
  fakeAccountApi({ signedInAs: adaSession });
  server.use(http.patch("*/api/auth/me", () => delay("infinite")));
  renderStudio(profilePath);

  await rename("Ada King");

  expect(await within(nameForm()).findByRole("button", { name: "Saving…" })).toBeDisabled();
});

test("a Member changes their password with their current one", async () => {
  const { requests } = fakeAccountApi({ signedInAs: adaSession, currentPassword: "my current password" });
  renderStudio(profilePath);

  await changePassword("my current password");

  expect(await within(passwordForm()).findByRole("status")).toHaveTextContent(
    "Password changed. Your other sessions have been signed out.",
  );
  expect(within(passwordForm()).getByLabelText("Current password")).toHaveValue("");
  expect(within(passwordForm()).getByLabelText("New password")).toHaveValue("");
  expect(requests).toEqual([
    {
      route: "change-password",
      body: { current_password: "my current password", new_password: "a brand new password" },
    },
  ]);
});

test("a wrong current password is refused", async () => {
  fakeAccountApi({ signedInAs: adaSession, currentPassword: "my current password" });
  renderStudio(profilePath);

  await changePassword("not my password");

  expect(await within(passwordForm()).findByRole("alert")).toHaveTextContent("Current password is incorrect.");
});

test("a too-short new password is refused", async () => {
  fakeAccountApi({ signedInAs: adaSession });
  server.use(http.post("*/api/auth/me/password", () => HttpResponse.json({ detail: [] }, { status: 422 })));
  renderStudio(profilePath);

  await changePassword("my current password", "twelve chars");

  expect(await within(passwordForm()).findByRole("alert")).toHaveTextContent(
    "Choose a new password of at least 12 characters.",
  );
});

test("a failed password change reports it", async () => {
  fakeAccountApi({ signedInAs: adaSession });
  server.use(http.post("*/api/auth/me/password", () => new HttpResponse(null, { status: 503 })));
  renderStudio(profilePath);

  await changePassword("my current password");

  expect(await within(passwordForm()).findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("shows progress while changing the password", async () => {
  fakeAccountApi({ signedInAs: adaSession });
  server.use(http.post("*/api/auth/me/password", () => delay("infinite")));
  renderStudio(profilePath);

  await changePassword("my current password");

  expect(await within(passwordForm()).findByRole("button", { name: "Changing password…" })).toBeDisabled();
});

test("an unreachable API is reported", async () => {
  fakeAccountApi({ signedInAs: adaSession });
  server.use(http.post("*/api/auth/me/password", () => HttpResponse.error()));
  renderStudio(profilePath);

  await changePassword("my current password");

  expect(await within(passwordForm()).findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});
