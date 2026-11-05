import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { aDocument, fakeDocumentsApi, STORAGE, UNSUPPORTED } from "../test/documents";
import { fakeProjectsApi, hrProject, oldProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const documentsTab = (projectId = hrProject.id) => `/organisations/${organisationId}/projects/${projectId}`;
const DOCUMENTS = "*/api/organisations/:organisationId/projects/:projectId/documents";

function file(name: string, text = "# Handbook\n\nWelcome.") {
  return new File([text], name, { type: "text/markdown" });
}

async function documentsTable() {
  return within(await screen.findByRole("table", { name: "Documents" }));
}

function rowOf(table: Awaited<ReturnType<typeof documentsTable>>, name: string) {
  const cell = table.getByRole("cell", { name });
  return within(cell.closest("tr") as HTMLElement);
}

test("an Editor uploads files and watches each go from Queued to Ready without refreshing", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const { requests } = fakeDocumentsApi();
  renderStudio(documentsTab());
  expect(await screen.findByText(/No Documents yet/)).toBeInTheDocument();

  await userEvent.upload(screen.getByLabelText("Choose files to upload"), [file("handbook.md"), file("faq.txt", "Q and A")]);

  const uploads = within(screen.getByRole("list", { name: "Uploads" }));
  expect(await uploads.findAllByText("Uploaded")).toHaveLength(2);
  const table = await documentsTable();
  expect(rowOf(table, "handbook.md").getByText("Queued")).toBeInTheDocument();
  expect(rowOf(table, "faq.txt").getByText("512 B")).toBeInTheDocument();
  expect(await table.findAllByText("Processing", {}, { timeout: 4000 })).toHaveLength(2);
  expect(await table.findAllByText("Ready", {}, { timeout: 4000 })).toHaveLength(2);
  expect(rowOf(table, "handbook.md").getByRole("cell", { name: "4" })).toBeInTheDocument();

  // Each file was presigned, PUT straight to storage with its type, then confirmed.
  expect(requests.filter((r) => r.route === "start").map((r) => r.body)).toEqual([
    { filename: "handbook.md", size_bytes: 20 },
    { filename: "faq.txt", size_bytes: 7 },
  ]);
  expect(requests.filter((r) => r.route === "put").map((r) => [r.body, r.contentType])).toEqual([
    ["# Handbook\n\nWelcome.", "text/markdown"],
    ["Q and A", "text/markdown"],
  ]);
  expect(requests.filter((r) => r.route === "confirm")).toHaveLength(2);
  // Polling stops once every Document is Ready or Failed.
  const polls = requests.filter((r) => r.route === "statuses").length;
  await new Promise((resolve) => setTimeout(resolve, 2500));
  expect(requests.filter((r) => r.route === "statuses")).toHaveLength(polls);
}, 15000);

test("files dropped on the dropzone are uploaded", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi();
  renderStudio(documentsTab());
  const dropzone = await screen.findByTestId("dropzone");

  fireEvent.dragOver(dropzone);
  expect(dropzone).toHaveClass("border-slate-700");
  fireEvent.dragLeave(dropzone);
  expect(dropzone).not.toHaveClass("border-slate-700");
  fireEvent.drop(dropzone, { dataTransfer: { files: [file("dropped.md")] } });

  expect(await (await documentsTable()).findByRole("cell", { name: "dropped.md" })).toBeInTheDocument();
});

test("a file the API refuses says why, and the others still upload", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi();
  renderStudio(documentsTab());

  await userEvent.upload(await screen.findByLabelText("Choose files to upload"), [file("sheet.xlsx"), file("ok.md")], {
    applyAccept: false,
  });

  expect(await screen.findByRole("alert")).toHaveTextContent(UNSUPPORTED);
  expect(await (await documentsTable()).findByRole("cell", { name: "ok.md" })).toBeInTheDocument();
});

test("each upload shows its progress until it is stored", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi();
  server.use(
    http.put(`${STORAGE}/:uploadId`, async () => {
      await delay(300);
      return new HttpResponse(null, { status: 200 });
    }),
  );
  renderStudio(documentsTab());

  await userEvent.upload(await screen.findByLabelText("Choose files to upload"), file("slow.md"));

  expect(await screen.findByRole("progressbar", { name: "Uploading slow.md" })).toBeInTheDocument();
  expect(await screen.findByText("Uploaded")).toBeInTheDocument();
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
});

test.each([
  ["storage refuses the file", () => http.put(`${STORAGE}/:uploadId`, () => new HttpResponse(null, { status: 403 }))],
  ["storage can't be reached", () => http.put(`${STORAGE}/:uploadId`, () => HttpResponse.error())],
  ["the API fails without a reason", () => http.post(DOCUMENTS, () => new HttpResponse("Bad gateway", { status: 502 }))],
  [
    "starting fails without a reason",
    () => http.post("*/api/organisations/:organisationId/projects/:projectId/uploads", () => new HttpResponse("Bad gateway", { status: 502 })),
  ],
])("an upload that fails because %s says to try again", async (_, handler) => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi();
  server.use(handler());
  renderStudio(documentsTab());

  await userEvent.upload(await screen.findByLabelText("Choose files to upload"), file("handbook.md"));

  expect(await screen.findByRole("alert")).toHaveTextContent("The upload failed. Try again.");
});

test("a confirmation the API refuses shows its reason", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi();
  const expired = "This upload wasn't found or has expired. Start the upload again.";
  server.use(http.post(DOCUMENTS, () => HttpResponse.json({ detail: expired }, { status: 409 })));
  renderStudio(documentsTab());

  await userEvent.upload(await screen.findByLabelText("Choose files to upload"), file("handbook.md"));

  expect(await screen.findByRole("alert")).toHaveTextContent(expired);
});

test("Documents show their status, size and Chunk count, and why one failed", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({
    documents: [
      aDocument(),
      aDocument({
        id: "d0c00000-0000-4000-8000-000000000002",
        name: "broken.docx",
        status: "failed",
        error_message: "This Document couldn't be processed. Try uploading it again.",
        chunk_count: 0,
        size_bytes: 20_480,
      }),
    ],
  });
  renderStudio(documentsTab());

  const table = await documentsTable();
  expect(table.getAllByRole("columnheader").map((header) => header.textContent)).toEqual(["Name", "Status", "Chunks", "Size"]);
  const ready = rowOf(table, "handbook.pdf");
  expect(ready.getByText("Ready")).toBeInTheDocument();
  expect(ready.getByText("12")).toBeInTheDocument();
  expect(ready.getByText("2.5 MB")).toBeInTheDocument();
  const failed = rowOf(table, "broken.docx");
  expect(failed.getByText("Failed")).toBeInTheDocument();
  expect(failed.getByText("This Document couldn't be processed. Try uploading it again.")).toBeInTheDocument();
  expect(failed.getByText("20.0 KB")).toBeInTheDocument();
});

test("the Document list says when it can't be loaded", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  server.use(http.get(DOCUMENTS, () => HttpResponse.json({ detail: "Not found" }, { status: 404 })));
  renderStudio(documentsTab());

  expect(await screen.findByText("The Documents could not be loaded. Try again shortly.")).toBeInTheDocument();
});

test("a status poll that fails keeps the last known statuses", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({ documents: [aDocument({ status: "processing", chunk_count: 0 })] });
  server.use(http.get(`${DOCUMENTS}/statuses`, () => new HttpResponse("Bad gateway", { status: 502 })));
  renderStudio(documentsTab());

  const table = await documentsTable();
  expect(table.getByText("Processing")).toBeInTheDocument();
});

test("an archived Project takes no uploads", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi();
  renderStudio(documentsTab(oldProject.id));

  expect(await screen.findByText(/No Documents yet/)).toBeInTheDocument();
  expect(screen.queryByLabelText("Choose files to upload")).not.toBeInTheDocument();
});
