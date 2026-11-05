import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { organisationId } from "../test/invites";
import { fakeMembersApi, LAST_OWNER } from "../test/members";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const settingsPath = `/organisations/${organisationId}/settings`;
const editorSession = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};

test("an Editor leaves the Organisation after confirming", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  const api = fakeMembersApi({ members: [] });
  renderStudio(settingsPath);

  await userEvent.click(await screen.findByRole("button", { name: "Leave Analytical Engines" }));
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(api.left).toBe(0);
  await userEvent.click(screen.getByRole("button", { name: "Leave Analytical Engines" }));
  expect(screen.getByText("You will lose access to Analytical Engines until someone invites you again.")).toBeInTheDocument();
  // Once left, the session no longer lists the Organisation.
  server.use(http.get("*/api/auth/me", () => HttpResponse.json({ ...adaSession, organisations: [] })));
  await userEvent.click(screen.getByRole("button", { name: "Yes, leave Analytical Engines" }));

  expect(await screen.findByText("You don't belong to any Organisation yet.")).toBeInTheDocument();
  expect(api.left).toBe(1);
});

test("the last Owner is told they can't leave", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeMembersApi();
  renderStudio(settingsPath);

  await userEvent.click(await screen.findByRole("button", { name: "Leave Analytical Engines" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, leave Analytical Engines" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(LAST_OWNER);
  expect(screen.getByRole("heading", { name: "Organisation settings" })).toBeInTheDocument();
});

test("a failed leave says to try again", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  server.use(http.post("*/api/organisations/:organisationId/leave", () => new HttpResponse(null, { status: 500 })));
  renderStudio(settingsPath);

  await userEvent.click(await screen.findByRole("button", { name: "Leave Analytical Engines" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, leave Analytical Engines" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});
