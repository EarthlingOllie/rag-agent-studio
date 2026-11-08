import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { adaSession, fakeAuthApi } from "../test/auth";
import { organisationId } from "../test/invites";
import { renderStudio } from "../test/render";
import { fakeRetentionApi } from "../test/retention";

const settingsPath = `/organisations/${organisationId}/settings`;
const editorSession = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};

const retention = () => screen.getByRole("region", { name: "Retention" });

test("an Owner sees the default Retention Window and changes it", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  let answerSave = () => {};
  const api = fakeRetentionApi({ saveGate: new Promise((resolve) => (answerSave = resolve)) });
  renderStudio(settingsPath);

  expect(
    await screen.findByText(
      "Message text and feedback comments are kept for 90 days, then purged every night. Metrics are kept.",
    ),
  ).toBeInTheDocument();
  const days = within(retention()).getByRole("spinbutton", { name: "Retention Window (days)" });
  expect(days).toHaveValue(90);
  expect(days).toHaveAccessibleDescription("Choose from 7 to 3650 days. Changes are recorded in the Audit log.");
  await userEvent.clear(days);
  await userEvent.type(days, "30");
  await userEvent.click(within(retention()).getByRole("button", { name: "Save" }));

  // While the save is under way the button says so and can't be pressed again.
  expect(await within(retention()).findByRole("button", { name: "Saving…" })).toBeDisabled();
  answerSave();
  expect(await within(retention()).findByRole("status")).toHaveTextContent("Saved.");
  expect(
    within(retention()).getByText(
      "Message text and feedback comments are kept for 30 days, then purged every night. Metrics are kept.",
    ),
  ).toBeInTheDocument();
  expect(api.requests).toEqual([{ retention_days: 30 }]);
});

test("a Retention Window out of range is refused and explained", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  const api = fakeRetentionApi({ days: 30 });
  renderStudio(settingsPath);
  const days = await screen.findByRole("spinbutton", { name: "Retention Window (days)" });
  // The browser's own range check is skipped to show the API's answer.
  days.removeAttribute("min");

  await userEvent.clear(days);
  await userEvent.type(days, "3");
  await userEvent.click(within(retention()).getByRole("button", { name: "Save" }));

  expect(await within(retention()).findByRole("alert")).toHaveTextContent("Choose from 7 to 3650 days.");
  expect(api.requests).toEqual([{ retention_days: 3 }]);
  // Typing again clears the error.
  await userEvent.type(days, "0");
  expect(within(retention()).queryByRole("alert")).not.toBeInTheDocument();
  expect(within(retention()).getByText(/kept for 30 days/)).toBeInTheDocument();
});

test("a failed save says so", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeRetentionApi({ saveStatus: 500 });
  renderStudio(settingsPath);

  await userEvent.click(await screen.findByRole("button", { name: "Save" }));

  expect(await within(retention()).findByRole("alert")).toHaveTextContent(
    "The Retention Window could not be saved. Try again shortly.",
  );
});

test("an Editor sees the Retention Window without changing it", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  fakeRetentionApi({ days: 365 });
  renderStudio(settingsPath);

  expect(await screen.findByText(/kept for 365 days/)).toBeInTheDocument();
  expect(within(retention()).getByText("Only Owners can change this.")).toBeInTheDocument();
  expect(within(retention()).queryByRole("spinbutton")).not.toBeInTheDocument();
});

test("a Retention Window that can't be loaded says so", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeRetentionApi({ readStatus: 500 });
  renderStudio(settingsPath);

  expect(await screen.findByText("The Retention Window could not be loaded. Try again shortly.")).toBeInTheDocument();
});
