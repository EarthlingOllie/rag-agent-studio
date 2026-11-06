import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi, type Session } from "../test/auth";
import {
  fakeProjectsApi,
  hrProject,
  oldProject,
  PROJECT_ARCHIVED,
} from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const settingsPage = (projectId: string) =>
  `/organisations/${organisationId}/projects/${projectId}/settings`;
const editorSession: Session = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({
    ...organisation,
    role: "editor" as const,
  })),
};
const OCR = "Read scanned PDFs with OCR";

test("the Settings tab shows OCR off by default, and why it is off", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  fakeProjectsApi();
  renderStudio(`/organisations/${organisationId}/projects/${hrProject.id}`);

  await screen.findByRole("heading", { level: 1, name: "HR handbook" });

  await userEvent.click(
    within(screen.getByRole("navigation", { name: "Project" })).getByRole(
      "link",
      { name: "Settings" },
    ),
  );

  expect(
    await screen.findByRole("heading", { level: 2, name: "Settings" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: OCR })).not.toBeChecked();
  expect(
    screen.getByText(
      /OCR reads text in images, such as scanned pages\. It makes processing slower/,
    ),
  ).toBeInTheDocument();
});

test("an Editor turns OCR on, then off again", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  const { requests } = fakeProjectsApi();
  renderStudio(settingsPage(hrProject.id));

  await userEvent.click(await screen.findByRole("checkbox", { name: OCR }));

  expect(await screen.findByRole("checkbox", { name: OCR })).toBeChecked();
  expect(screen.getByRole("status")).toHaveTextContent(
    "OCR is on. New uploads are read with OCR. Retry a Document on the Documents tab to reprocess it.",
  );
  await userEvent.click(screen.getByRole("checkbox", { name: OCR }));
  await screen.findByText(/OCR is off\./);
  expect(screen.getByRole("checkbox", { name: OCR })).not.toBeChecked();
  expect(requests).toEqual([
    { route: "update", projectId: hrProject.id, body: { ocr_enabled: true } },
    { route: "update", projectId: hrProject.id, body: { ocr_enabled: false } },
  ]);
});

test("the toggle is disabled while saving, and a refused change says why and keeps the setting", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  server.use(
    http.patch(
      "*/api/organisations/:organisationId/projects/:projectId",
      async () => {
        await delay(200);
        return HttpResponse.json({ detail: PROJECT_ARCHIVED }, { status: 409 });
      },
    ),
  );
  renderStudio(settingsPage(hrProject.id));

  await userEvent.click(await screen.findByRole("checkbox", { name: OCR }));

  expect(screen.getByRole("checkbox", { name: OCR })).toBeDisabled();
  expect(screen.getByRole("checkbox", { name: OCR })).toBeChecked();
  expect(await screen.findByRole("alert")).toHaveTextContent(PROJECT_ARCHIVED);
  expect(screen.getByRole("checkbox", { name: OCR })).not.toBeChecked();
  expect(screen.getByRole("checkbox", { name: OCR })).toBeEnabled();
});

test("the box shows the setting asked for as soon as it is clicked, before the save starts", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  fakeProjectsApi();
  renderStudio(settingsPage(hrProject.id));
  const box = await screen.findByRole("checkbox", { name: OCR });

  // A synchronous click, as a browser delivers it: nothing else runs before the box is read.
  fireEvent.click(box);

  expect(box).toBeChecked();
  expect(box).toBeDisabled();
  await screen.findByText(/OCR is on\./);
  expect(box).toBeChecked();
  expect(box).toBeEnabled();
});

test("an archived Project's OCR setting can't be changed", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi({ projects: [{ ...oldProject, ocr_enabled: true }] });
  renderStudio(settingsPage(oldProject.id));

  expect(await screen.findByRole("checkbox", { name: OCR })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: OCR })).toBeDisabled();
});
