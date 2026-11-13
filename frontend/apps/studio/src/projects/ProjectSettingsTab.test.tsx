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
import { openSection } from "../test/navigation";
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

  await openSection("Project sections", "Settings");

  expect(
    await screen.findByRole("heading", { level: 2, name: "Settings" }),
  ).toBeInTheDocument();
  const card = screen.getByRole("region", { name: "OCR" });
  const box = within(card).getByRole("checkbox", { name: OCR });
  expect(box).not.toBeChecked();
  expect(box).toHaveAccessibleDescription(
    /OCR reads text in images, such as scanned pages\. It makes processing slower/,
  );
  expect(within(card).getByRole("status")).toHaveTextContent("OCR is off. Text in images isn't read.");
});

test("Settings opens with a header and a short description, then a card per setting, each with a title and explanation", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  fakeProjectsApi();
  renderStudio(settingsPage(hrProject.id));

  const header = await screen.findByRole("heading", { level: 2, name: "Settings" });
  expect(header.parentElement).toHaveTextContent(
    "How this Project embeds, reads and screens its Documents. A change applies to every Agent in it.",
  );
  const cards = ["Embedding Model", "OCR", "Flagged Chunks"].map((name) => screen.getByRole("region", { name }));
  expect(cards.map((card) => within(card).getByRole("heading", { level: 3 }).textContent)).toEqual([
    "Embedding Model",
    "OCR",
    "Flagged Chunks",
  ]);
  expect(cards[0]).toHaveTextContent("The model that turns each Chunk into a vector for retrieval.");
  expect(cards[1]).toHaveTextContent("OCR reads text in images, such as scanned pages.");
  expect(cards[2]).toHaveTextContent("The ingestion scan flags Chunks that look like instructions to an AI");
});

test("an archived Project's Settings say why they can't be changed, show every setting disabled and offer no Embedding Model change", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  renderStudio(settingsPage(oldProject.id));

  const header = await screen.findByRole("heading", { level: 2, name: "Settings" });
  expect(header.parentElement).toHaveTextContent("This Project is archived, so its settings can't be changed.");
  expect(screen.getByRole("checkbox", { name: OCR })).toBeDisabled();
  expect(screen.queryByRole("region", { name: "Embedding Model" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Change/ })).not.toBeInTheDocument();
});

test("an Editor turns OCR on, then off again", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  const { requests } = fakeProjectsApi();
  renderStudio(settingsPage(hrProject.id));

  await userEvent.click(await screen.findByRole("checkbox", { name: OCR }));

  expect(await screen.findByRole("checkbox", { name: OCR })).toBeChecked();
  expect(
    within(screen.getByRole("region", { name: "OCR" })).getByRole("status"),
  ).toHaveTextContent(
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

test("flagged Chunks are always quarantined: the Flagged Chunks card explains it and offers no setting", async () => {
  fakeAuthApi({ signedInAs: editorSession });
  const { requests } = fakeProjectsApi();
  renderStudio(settingsPage(hrProject.id));

  const card = await screen.findByRole("region", { name: "Flagged Chunks" });
  expect(card).toHaveTextContent(
    "Flagged Chunks are always quarantined: Agents are never given them, and the Trace lists them as excluded by the ingestion scan.",
  );
  expect(card).toHaveTextContent("Review a flagged Chunk in the Document viewer, and allow it there if it is a false positive.");
  // No setting lets a detected prompt injection reach an Agent.
  expect(within(card).queryByRole("radiogroup")).not.toBeInTheDocument();
  expect(within(card).queryByRole("radio")).not.toBeInTheDocument();
  expect(requests).toEqual([]);
});
