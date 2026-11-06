import type { Schemas } from "@studio/api-client";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import {
  aDocument,
  BUSY,
  fakeDocumentsApi,
  STORAGE,
  UNSUPPORTED,
} from "../test/documents";
import { fakeProjectsApi, hrProject, oldProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const documentsTab = (projectId = hrProject.id) =>
  `/organisations/${organisationId}/projects/${projectId}`;
const DOCUMENTS =
  "*/api/organisations/:organisationId/projects/:projectId/documents";

function file(name: string, text = "# Handbook\n\nWelcome.") {
  return new File([text], name, { type: "text/markdown" });
}

async function documentsTable() {
  return within(await screen.findByRole("table", { name: "Documents" }));
}

function rowOf(
  table: Awaited<ReturnType<typeof documentsTable>>,
  name: string,
) {
  const cell = table.getByRole("cell", { name });
  return within(cell.closest("tr") as HTMLElement);
}

test("an Editor uploads files and watches each go from Queued to Ready without refreshing", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const { requests } = fakeDocumentsApi();
  renderStudio(documentsTab());
  expect(await screen.findByText(/No Documents yet/)).toBeInTheDocument();

  await userEvent.upload(screen.getByLabelText("Choose files to upload"), [
    file("handbook.md"),
    file("faq.txt", "Q and A"),
  ]);

  const uploads = within(screen.getByRole("list", { name: "Uploads" }));
  expect(await uploads.findAllByText("Uploaded")).toHaveLength(2);
  const table = await documentsTable();
  expect(rowOf(table, "handbook.md").getByText("Queued")).toBeInTheDocument();
  expect(rowOf(table, "faq.txt").getByText("512 B")).toBeInTheDocument();
  expect(
    await table.findAllByText("Processing", {}, { timeout: 4000 }),
  ).toHaveLength(2);
  expect(
    await table.findAllByText("Ready", {}, { timeout: 4000 }),
  ).toHaveLength(2);
  expect(
    rowOf(table, "handbook.md").getByRole("cell", { name: "4" }),
  ).toBeInTheDocument();

  // Each file was presigned, PUT straight to storage with its type, then confirmed.
  expect(
    requests.filter((r) => r.route === "start").map((r) => r.body),
  ).toEqual([
    { filename: "handbook.md", size_bytes: 20 },
    { filename: "faq.txt", size_bytes: 7 },
  ]);
  expect(
    requests
      .filter((r) => r.route === "put")
      .map((r) => [r.body, r.contentType]),
  ).toEqual([
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

  expect(
    await (await documentsTable()).findByRole("cell", { name: "dropped.md" }),
  ).toBeInTheDocument();
});

test("a file of an unsupported type is refused before upload, and the others still upload", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const { requests } = fakeDocumentsApi();
  renderStudio(documentsTab());
  expect(await screen.findByText(/0 of 500 Documents/)).toBeInTheDocument();

  await userEvent.upload(await screen.findByLabelText("Choose files to upload"), [file("sheet.xlsx"), file("README"), file("ok.md")], {
    applyAccept: false,
  });

  const refused = await screen.findAllByRole("alert");
  expect(refused.map((alert) => alert.textContent)).toEqual([UNSUPPORTED, UNSUPPORTED]);
  expect(await (await documentsTable()).findByRole("cell", { name: "ok.md" })).toBeInTheDocument();
  // The refused files never reached the API.
  expect(requests.filter((r) => r.route === "start").map((r) => r.body)).toEqual([{ filename: "ok.md", size_bytes: 20 }]);
});

test("a file over the size limit is refused before upload", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const { requests } = fakeDocumentsApi({ limits: { max_upload_bytes: 2 * 1024 * 1024 } });
  renderStudio(documentsTab());
  expect(await screen.findByText(/up to 2.0 MB each/)).toBeInTheDocument();

  await userEvent.upload(screen.getByLabelText("Choose files to upload"), file("huge.md", "x".repeat(2 * 1024 * 1024 + 1)));

  expect(await screen.findByRole("alert")).toHaveTextContent("This file is larger than the 2 MB upload limit.");
  expect(requests.filter((r) => r.route === "start")).toEqual([]);
});

test("files beyond the Project's Document quota are refused with a clear message", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const { requests } = fakeDocumentsApi({ documents: [aDocument()], limits: { document_quota: 2 } });
  renderStudio(documentsTab());
  expect(await screen.findByText(/1 of 2 Documents/)).toBeInTheDocument();

  await userEvent.upload(screen.getByLabelText("Choose files to upload"), [file("fits.md"), file("over.md")]);

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "This Project has reached its quota of 2 Documents. Delete a Document, or ask an Owner to raise the quota.",
  );
  expect(await (await documentsTable()).findByRole("cell", { name: "fits.md" })).toBeInTheDocument();
  expect(requests.filter((r) => r.route === "start").map((r) => r.body)).toEqual([{ filename: "fits.md", size_bytes: 20 }]);
  expect(await screen.findByText(/2 of 2 Documents/)).toBeInTheDocument();
});

test("a quota of one names a single Document", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({ documents: [aDocument()], limits: { document_quota: 1 } });
  renderStudio(documentsTab());
  expect(await screen.findByText(/1 of 1 Documents/)).toBeInTheDocument();

  await userEvent.upload(screen.getByLabelText("Choose files to upload"), file("over.md"));

  expect(await screen.findByRole("alert")).toHaveTextContent("This Project has reached its quota of 1 Document. Delete a Document");
});

test("a file the API refuses at the start says why", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi();
  const full = "This Project has reached its quota of 3 Documents. Delete a Document, or ask an Owner to raise the quota.";
  server.use(
    http.post("*/api/organisations/:organisationId/projects/:projectId/uploads", () => HttpResponse.json({ detail: full }, { status: 409 })),
  );
  renderStudio(documentsTab());
  expect(await screen.findByText(/0 of 500 Documents/)).toBeInTheDocument();

  await userEvent.upload(screen.getByLabelText("Choose files to upload"), file("handbook.md"));

  expect(await screen.findByRole("alert")).toHaveTextContent(full);
});

test("uploads still go ahead when the upload limits can't be loaded, and the API checks them", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const { requests } = fakeDocumentsApi();
  server.use(http.get(`*/api/organisations/:organisationId/projects/:projectId/uploads/limits`, () => new HttpResponse(null, { status: 502 })));
  renderStudio(documentsTab());
  const picker = await screen.findByLabelText("Choose files to upload");
  expect(picker).toHaveAttribute("accept", ".pdf,.docx,.pptx,.html,.htm,.md,.markdown,.txt");

  await userEvent.upload(picker, [file("sheet.xlsx"), file("ok.md")], { applyAccept: false });

  expect(await screen.findByRole("alert")).toHaveTextContent(UNSUPPORTED);
  expect(await (await documentsTable()).findByRole("cell", { name: "ok.md" })).toBeInTheDocument();
  expect(requests.filter((r) => r.route === "start")).toHaveLength(2);
  expect(screen.queryByText(/Documents in this Project's quota/)).not.toBeInTheDocument();
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

  await userEvent.upload(
    await screen.findByLabelText("Choose files to upload"),
    file("slow.md"),
  );

  expect(
    await screen.findByRole("progressbar", { name: "Uploading slow.md" }),
  ).toBeInTheDocument();
  expect(await screen.findByText("Uploaded")).toBeInTheDocument();
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
});

test.each([
  [
    "storage refuses the file",
    () =>
      http.put(
        `${STORAGE}/:uploadId`,
        () => new HttpResponse(null, { status: 403 }),
      ),
  ],
  [
    "storage can't be reached",
    () => http.put(`${STORAGE}/:uploadId`, () => HttpResponse.error()),
  ],
  [
    "the API fails without a reason",
    () =>
      http.post(
        DOCUMENTS,
        () => new HttpResponse("Bad gateway", { status: 502 }),
      ),
  ],
  [
    "starting fails without a reason",
    () =>
      http.post(
        "*/api/organisations/:organisationId/projects/:projectId/uploads",
        () => new HttpResponse("Bad gateway", { status: 502 }),
      ),
  ],
])("an upload that fails because %s says to try again", async (_, handler) => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi();
  server.use(handler());
  renderStudio(documentsTab());

  await userEvent.upload(
    await screen.findByLabelText("Choose files to upload"),
    file("handbook.md"),
  );

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "The upload failed. Try again.",
  );
});

test("a confirmation the API refuses shows its reason", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi();
  const expired =
    "This upload wasn't found or has expired. Start the upload again.";
  server.use(
    http.post(DOCUMENTS, () =>
      HttpResponse.json({ detail: expired }, { status: 409 }),
    ),
  );
  renderStudio(documentsTab());

  await userEvent.upload(
    await screen.findByLabelText("Choose files to upload"),
    file("handbook.md"),
  );

  expect(await screen.findByRole("alert")).toHaveTextContent(expired);
});

test("Documents show their status, size and Chunk count, and what kind of failure and why", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({
    documents: [
      aDocument(),
      aDocument({
        id: "d0c00000-0000-4000-8000-000000000002",
        name: "broken.docx",
        status: "failed",
        error_category: "unsupported_content",
        error_message: "This file isn't a valid DOCX file. Check the file, then upload it again.",
        chunk_count: 0,
        size_bytes: 20_480,
      }),
    ],
  });
  renderStudio(documentsTab());

  const table = await documentsTable();
  expect(
    table.getAllByRole("columnheader").map((header) => header.textContent),
  ).toEqual(["Select", "Name", "Status", "Tags", "Chunks", "Size", "Actions"]);
  const ready = rowOf(table, "handbook.pdf");
  expect(ready.getByText("Ready")).toBeInTheDocument();
  expect(ready.getByText("12")).toBeInTheDocument();
  expect(ready.getByText("2.5 MB")).toBeInTheDocument();
  const failed = rowOf(table, "broken.docx");
  expect(failed.getByText("Failed")).toBeInTheDocument();
  expect(failed.getByText("Unsupported content")).toBeInTheDocument();
  expect(failed.getByText("This file isn't a valid DOCX file. Check the file, then upload it again.")).toBeInTheDocument();
  expect(failed.getByText("20.0 KB")).toBeInTheDocument();
  expect(failed.getByRole("button", { name: "Retry broken.docx" })).toBeInTheDocument();
});

const failedDocument = (category: Schemas["FailureCategory"], message: string) =>
  aDocument({
    id: "d0c00000-0000-4000-8000-000000000009",
    name: "broken.md",
    status: "failed",
    error_category: category,
    error_message: message,
    chunk_count: 0,
  });

test.each([
  ["conversion", "Conversion error"],
  ["provider", "Provider error"],
  ["quota", "Quota reached"],
] as const)("a %s failure is labelled %s", async (category, label) => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({ documents: [failedDocument(category, "Why it failed.")] });
  renderStudio(documentsTab());

  const row = rowOf(await documentsTable(), "broken.md");
  expect(row.getByText(label)).toBeInTheDocument();
  expect(row.getByText("Why it failed.")).toBeInTheDocument();
});

test("an Editor retries a failed Document and watches it go back to Ready", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const { requests } = fakeDocumentsApi({
    documents: [failedDocument("conversion", "This file couldn't be converted. Retry it, or upload a fixed copy.")],
  });
  renderStudio(documentsTab());
  const table = await documentsTable();

  await userEvent.click(table.getByRole("button", { name: "Retry broken.md" }));

  expect(await table.findByText("Queued")).toBeInTheDocument();
  expect(table.queryByText("Conversion error")).not.toBeInTheDocument();
  expect(await table.findByText("Ready", {}, { timeout: 6000 })).toBeInTheDocument();
  expect(requests.filter((r) => r.route === "retry").map((r) => r.body)).toEqual(["d0c00000-0000-4000-8000-000000000009"]);
}, 10000);

test.each([
  [409, { detail: "This file is already in the Project as handbook.md." }, "This file is already in the Project as handbook.md."],
  [502, "Bad gateway", "The retry failed. Try again."],
  [409, {}, "The retry failed. Try again."],
])("a retry the API answers with %s says so", async (status, body, message) => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({ documents: [failedDocument("conversion", "Couldn't convert.")] });
  server.use(
    http.post("*/api/organisations/:organisationId/projects/:projectId/documents/:documentId/retry", () =>
      typeof body === "string" ? new HttpResponse(body, { status }) : HttpResponse.json(body, { status }),
    ),
  );
  renderStudio(documentsTab());

  await userEvent.click((await documentsTable()).getByRole("button", { name: "Retry broken.md" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(message);
});

test("a Document waiting for an automatic retry says so while it is Queued", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const retrying = "The Embedding Model's provider didn't respond. Retrying automatically (attempt 2 of 4).";
  fakeDocumentsApi({ documents: [aDocument({ status: "queued", error_message: retrying, chunk_count: 0, attempt_count: 1 })] });
  server.use(http.get(`${DOCUMENTS}/statuses`, () => new HttpResponse("Bad gateway", { status: 502 })));
  renderStudio(documentsTab());

  const row = rowOf(await documentsTable(), "handbook.pdf");
  expect(row.getByText("Queued")).toBeInTheDocument();
  expect(row.getByText(retrying)).toHaveClass("text-slate-700");
  expect(row.queryByRole("button", { name: /Retry/ })).not.toBeInTheDocument();
});

test("the Document list says when it can't be loaded", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  server.use(
    http.get(DOCUMENTS, () =>
      HttpResponse.json({ detail: "Not found" }, { status: 404 }),
    ),
  );
  renderStudio(documentsTab());

  expect(
    await screen.findByText(
      "The Documents could not be loaded. Try again shortly.",
    ),
  ).toBeInTheDocument();
});

test("a status poll that fails keeps the last known statuses", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({
    documents: [aDocument({ status: "processing", chunk_count: 0 })],
  });
  server.use(
    http.get(
      `${DOCUMENTS}/statuses`,
      () => new HttpResponse("Bad gateway", { status: 502 }),
    ),
  );
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
  expect(
    screen.queryByLabelText("Choose files to upload"),
  ).not.toBeInTheDocument();
});

test("uploading a file already in the Project is refused with a link to the existing Document", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const { requests } = fakeDocumentsApi();
  renderStudio(documentsTab());
  const picker = await screen.findByLabelText("Choose files to upload");
  await userEvent.upload(picker, file("handbook.md"));
  const table = await documentsTable();
  expect(
    await table.findByRole("cell", { name: "handbook.md" }),
  ).toBeInTheDocument();

  await userEvent.upload(picker, file("copy.md"));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent(
    "This file is already in the Project as handbook.md.",
  );
  const link = within(alert).getByRole("link", { name: "Show handbook.md" });
  const row = table
    .getByRole("cell", { name: "handbook.md" })
    .closest("tr") as HTMLElement;
  expect(link).toHaveAttribute("href", `#${row.id}`);
  expect(requests.filter((r) => r.route === "confirm")).toHaveLength(2);
  expect(
    table.queryByRole("cell", { name: "copy.md" }),
  ).not.toBeInTheDocument();
});

test("an Editor uploads a new edition, and the old one shows as Ready until the new one replaces it", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const { requests } = fakeDocumentsApi({ documents: [aDocument()] });
  renderStudio(documentsTab());
  const table = await documentsTable();
  expect(
    table.getAllByRole("columnheader").map((header) => header.textContent),
  ).toEqual(["Select", "Name", "Status", "Tags", "Chunks", "Size", "Actions"]);

  await userEvent.upload(
    table.getByLabelText("New edition of handbook.pdf"),
    file("handbook-2027.md", "# Handbook 2027"),
  );

  const uploads = within(screen.getByRole("list", { name: "Uploads" }));
  expect(
    await uploads.findByText("New edition of handbook.pdf"),
  ).toBeInTheDocument();
  expect(await uploads.findByText("Uploaded")).toBeInTheDocument();
  const row = rowOf(table, "handbook.pdf");
  expect(
    await row.findByText(
      /New edition 2 \(handbook-2027\.md\): (Queued|Processing)/,
    ),
  ).toBeInTheDocument();
  // The current edition keeps serving: still Ready, with its Chunks.
  expect(row.getByText("Ready")).toBeInTheDocument();
  expect(row.getByRole("cell", { name: "12" })).toBeInTheDocument();
  // While the new edition is processing, another can't be uploaded.
  expect(
    row.queryByLabelText("New edition of handbook.pdf"),
  ).not.toBeInTheDocument();

  const replaced = await table.findByRole(
    "cell",
    { name: "handbook-2027.md" },
    { timeout: 8000 },
  );
  const after = within(replaced.closest("tr") as HTMLElement);
  expect(after.getByText("Ready")).toBeInTheDocument();
  expect(after.queryByText(/New edition 2/)).not.toBeInTheDocument();
  expect(await after.findByRole("cell", { name: "6" })).toBeInTheDocument();
  // Upload IDs count every request; the list read comes first.
  expect(
    requests.filter((r) => r.route === "replace").map((r) => r.body),
  ).toEqual([{ upload_id: "u2" }]);
}, 15000);

test("a second new edition shows as soon as it is uploaded, after the first has replaced the Document", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({ documents: [aDocument()] });
  renderStudio(documentsTab());
  const table = await documentsTable();
  await userEvent.upload(
    table.getByLabelText("New edition of handbook.pdf"),
    file("handbook-2027.md", "# Handbook 2027"),
  );
  const replaced = await table.findByRole(
    "cell",
    { name: "handbook-2027.md" },
    { timeout: 8000 },
  );
  const row = within(replaced.closest("tr") as HTMLElement);
  expect(await row.findByRole("cell", { name: "6" })).toBeInTheDocument();
  // From here the status endpoint answers slowly, so the last poll's answer, from before this
  // upload, is what the Studio holds while the list is read again.
  server.use(
    http.get(`${DOCUMENTS}/statuses`, async () => {
      await delay(2000);
    }),
  );

  await userEvent.upload(
    row.getByLabelText("New edition of handbook-2027.md"),
    file("handbook-2028.md", "# Handbook 2028"),
  );

  expect(
    await row.findByText(
      /New edition 3 \(handbook-2028\.md\): Queued/,
      {},
      { timeout: 1000 },
    ),
  ).toBeInTheDocument();
  expect(row.getByText("Ready")).toBeInTheDocument();
  expect(
    await table.findByRole(
      "cell",
      { name: "handbook-2028.md" },
      { timeout: 10000 },
    ),
  ).toBeInTheDocument();
}, 20000);

const CONVERT_FAILED =
  "This file couldn't be converted. Retry it, or upload a fixed copy.";

const withFailedEdition = () =>
  aDocument({
    replacement: {
      edition: 2,
      name: "broken.md",
      status: "failed",
      error_category: "conversion",
      error_message: CONVERT_FAILED,
    },
  });

test("a failed new edition says why, and the Document keeps its current edition", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({ documents: [withFailedEdition()] });
  renderStudio(documentsTab());

  const row = rowOf(await documentsTable(), "handbook.pdf");
  expect(row.getByText("Ready")).toBeInTheDocument();
  expect(
    row.getByText(/New edition 2 \(broken\.md\): Failed/),
  ).toBeInTheDocument();
  expect(row.getByText("Conversion error")).toBeInTheDocument();
  expect(row.getByText(CONVERT_FAILED)).toBeInTheDocument();
  // A failed new edition can be replaced by another, or retried.
  expect(row.getByLabelText("New edition of handbook.pdf")).toBeInTheDocument();
  expect(
    row.getByRole("button", { name: "Retry handbook.pdf" }),
  ).toBeInTheDocument();
});

test("an Editor retries a failed new edition and it replaces the Document", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const { requests } = fakeDocumentsApi({ documents: [withFailedEdition()] });
  renderStudio(documentsTab());
  const table = await documentsTable();

  await userEvent.click(
    table.getByRole("button", { name: "Retry handbook.pdf" }),
  );

  expect(
    await table.findByText(/New edition 2 \(broken\.md\): Queued/),
  ).toBeInTheDocument();
  expect(table.queryByText("Conversion error")).not.toBeInTheDocument();
  expect(
    await table.findByRole("cell", { name: "broken.md" }, { timeout: 6000 }),
  ).toBeInTheDocument();
  expect(
    requests.filter((r) => r.route === "retry").map((r) => r.body),
  ).toEqual([aDocument().id]);
}, 10000);

test("a new edition of an unsupported type is refused before upload, even in a full Project", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const { requests } = fakeDocumentsApi({
    documents: [aDocument()],
    limits: { document_quota: 1 },
  });
  renderStudio(documentsTab());
  expect(await screen.findByText(/1 of 1 Documents/)).toBeInTheDocument();
  const table = await documentsTable();

  await userEvent.upload(
    table.getByLabelText("New edition of handbook.pdf"),
    file("sheet.xlsx"),
    { applyAccept: false },
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(UNSUPPORTED);
  expect(requests.filter((r) => r.route === "start")).toEqual([]);

  // A new edition doesn't add a Document, so the full quota doesn't refuse it.
  await userEvent.upload(
    table.getByLabelText("New edition of handbook.pdf"),
    file("handbook-2.md"),
  );
  expect(
    await table.findByText(/New edition 2 \(handbook-2\.md\)/),
  ).toBeInTheDocument();
  expect(
    requests.filter((r) => r.route === "start").map((r) => r.body),
  ).toEqual([
    {
      filename: "handbook-2.md",
      size_bytes: 20,
      replacing_document_id: aDocument().id,
    },
  ]);
});

test("a failed Document in an archived Project offers no retry", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({
    documents: [aDocument({ status: "failed", error_category: "conversion" })],
  });
  renderStudio(documentsTab(oldProject.id));

  const row = rowOf(await documentsTable(), "handbook.pdf");
  expect(row.getByText("Conversion error")).toBeInTheDocument();
  expect(row.queryByRole("button", { name: /Retry/ })).not.toBeInTheDocument();
});

test("a new edition the API refuses says why", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({ documents: [aDocument()] });
  const busy =
    "This Document is still being processed. Try again once it is Ready or Failed.";
  server.use(
    http.post(`${DOCUMENTS}/:documentId/editions`, () =>
      HttpResponse.json({ detail: busy }, { status: 409 }),
    ),
  );
  renderStudio(documentsTab());
  const table = await documentsTable();

  await userEvent.upload(
    table.getByLabelText("New edition of handbook.pdf"),
    file("new.md"),
  );

  expect(await screen.findByRole("alert")).toHaveTextContent(busy);
  expect(screen.queryByRole("link", { name: /Show/ })).not.toBeInTheDocument();
});

test("choosing no file for a new edition uploads nothing", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const { requests } = fakeDocumentsApi({ documents: [aDocument()] });
  renderStudio(documentsTab());
  const table = await documentsTable();

  fireEvent.change(table.getByLabelText("New edition of handbook.pdf"), {
    target: { files: [] },
  });

  expect(
    screen.queryByRole("list", { name: "Uploads" }),
  ).not.toBeInTheDocument();
  expect(requests.filter((r) => r.route !== "list")).toEqual([]);
});

test("a Document still processing can be deleted but not replaced", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({
    documents: [aDocument({ status: "queued", chunk_count: 0 })],
  });
  renderStudio(documentsTab());

  const row = rowOf(await documentsTable(), "handbook.pdf");
  expect(
    row.getByRole("button", { name: "Delete handbook.pdf" }),
  ).toBeInTheDocument();
  expect(
    row.queryByLabelText("New edition of handbook.pdf"),
  ).not.toBeInTheDocument();
});

test("an Editor deletes a Document after confirming, and it leaves the list", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const kept = aDocument({
    id: "d0c00000-0000-4000-8000-000000000002",
    name: "faq.md",
  });
  const { requests } = fakeDocumentsApi({ documents: [aDocument(), kept] });
  renderStudio(documentsTab());
  const table = await documentsTable();

  await userEvent.click(
    table.getByRole("button", { name: "Delete handbook.pdf" }),
  );
  const confirmation = within(
    table.getByRole("group", { name: "Delete handbook.pdf?" }),
  );
  expect(
    confirmation.getByText(
      "Delete handbook.pdf? It stops being retrieved at once.",
    ),
  ).toBeInTheDocument();
  await userEvent.click(confirmation.getByRole("button", { name: "Cancel" }));
  expect(table.queryByRole("group")).not.toBeInTheDocument();
  expect(requests.filter((r) => r.route === "delete")).toEqual([]);

  await userEvent.click(
    table.getByRole("button", { name: "Delete handbook.pdf" }),
  );
  await userEvent.click(
    within(
      table.getByRole("group", { name: "Delete handbook.pdf?" }),
    ).getByRole("button", { name: "Delete" }),
  );

  await waitFor(() => {
    expect(
      table.queryByRole("cell", { name: "handbook.pdf" }),
    ).not.toBeInTheDocument();
  });
  expect(table.getByRole("cell", { name: "faq.md" })).toBeInTheDocument();
  expect(
    requests.filter((r) => r.route === "delete").map((r) => r.body),
  ).toEqual([aDocument().id]);
});

test("a delete that fails says so and keeps the Document", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({ documents: [aDocument()] });
  server.use(
    http.delete(
      `${DOCUMENTS}/:documentId`,
      () => new HttpResponse("Bad gateway", { status: 502 }),
    ),
  );
  renderStudio(documentsTab());
  const table = await documentsTable();

  await userEvent.click(
    table.getByRole("button", { name: "Delete handbook.pdf" }),
  );
  await userEvent.click(
    within(
      table.getByRole("group", { name: "Delete handbook.pdf?" }),
    ).getByRole("button", { name: "Delete" }),
  );

  expect(await table.findByRole("alert")).toHaveTextContent(
    "The Document could not be deleted. Try again.",
  );
  expect(table.getByRole("cell", { name: "handbook.pdf" })).toBeInTheDocument();
  // Asking again clears the message.
  await userEvent.click(
    table.getByRole("button", { name: "Delete handbook.pdf" }),
  );
  expect(table.queryByRole("alert")).not.toBeInTheDocument();
});

test("an archived Project's Documents can't be replaced or deleted", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({ documents: [aDocument()] });
  renderStudio(documentsTab(oldProject.id));

  const table = await documentsTable();
  expect(
    table.getAllByRole("columnheader").map((header) => header.textContent),
  ).toEqual(["Select", "Name", "Status", "Tags", "Chunks", "Size"]);
  expect(
    table.queryByRole("button", { name: /Delete/ }),
  ).not.toBeInTheDocument();
});

test("a new edition still uploads when the upload limits can't be loaded, and the API checks it", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const { requests } = fakeDocumentsApi({ documents: [aDocument()] });
  server.use(http.get(`*/api/organisations/:organisationId/projects/:projectId/uploads/limits`, () => new HttpResponse(null, { status: 502 })));
  renderStudio(documentsTab());
  const table = await documentsTable();

  await userEvent.upload(table.getByLabelText("New edition of handbook.pdf"), file("handbook-2027.md", "# Handbook 2027"));

  expect(await within(screen.getByRole("list", { name: "Uploads" })).findByText("Uploaded")).toBeInTheDocument();
  expect(requests.filter((r) => r.route === "start").map((r) => r.body)).toEqual([
    expect.objectContaining({ filename: "handbook-2027.md", replacing_document_id: aDocument().id }),
  ]);
});

test("a Document that fails stops counting towards the quota without a reload", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({ failing: ["broken.pdf"] });
  renderStudio(documentsTab());
  expect(await screen.findByText(/0 of 500 Documents/)).toBeInTheDocument();

  await userEvent.upload(screen.getByLabelText("Choose files to upload"), new File(["not a pdf"], "broken.pdf", { type: "application/pdf" }));

  expect(await screen.findByText(/1 of 500 Documents/)).toBeInTheDocument();
  const row = rowOf(await documentsTable(), "broken.pdf");
  expect(await row.findByText("Unsupported content", {}, { timeout: 8000 })).toBeInTheDocument();
  expect(await screen.findByText(/0 of 500 Documents/)).toBeInTheDocument();
}, 15000);
test("a Ready or Failed Document is retried, and goes through Queued to Ready again", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const failedScan = aDocument({
    id: "d0c00000-0000-4000-8000-000000000002",
    name: "scan.pdf",
    status: "failed",
    error_message: "This Document couldn't be processed. Try uploading it again.",
    chunk_count: 0,
  });
  const { requests } = fakeDocumentsApi({ documents: [aDocument(), failedScan] });
  renderStudio(documentsTab());
  const table = await documentsTable();
  expect(rowOf(table, "handbook.pdf").getByRole("button", { name: "Retry handbook.pdf" })).toBeInTheDocument();

  await userEvent.click(rowOf(table, "scan.pdf").getByRole("button", { name: "Retry scan.pdf" }));

  expect(await rowOf(table, "scan.pdf").findByText("Queued")).toBeInTheDocument();
  expect(rowOf(table, "scan.pdf").queryByText(/couldn't be processed/)).not.toBeInTheDocument();
  expect(rowOf(table, "scan.pdf").queryByRole("button", { name: /Retry/ })).not.toBeInTheDocument();
  expect(await rowOf(table, "scan.pdf").findByText("Ready", {}, { timeout: 6000 })).toBeInTheDocument();
  expect(rowOf(table, "scan.pdf").getByRole("cell", { name: "4" })).toBeInTheDocument();
  expect(requests.filter((r) => r.route === "retry")).toEqual([{ route: "retry", body: failedScan.id }]);
}, 15000);

test("a Document still being processed, or with a new edition being processed, has no Retry", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const replacing = aDocument({
    id: "d0c00000-0000-4000-8000-000000000003",
    name: "policy.pdf",
    replacement: { edition: 2, name: "policy.pdf", status: "processing", error_message: null, error_category: null },
  });
  fakeDocumentsApi({ documents: [aDocument({ status: "processing", chunk_count: 0 }), replacing] });
  server.use(http.get(`${DOCUMENTS}/statuses`, () => new HttpResponse("Bad gateway", { status: 502 })));
  renderStudio(documentsTab());
  const table = await documentsTable();
  expect(rowOf(table, "handbook.pdf").getByText("Processing")).toBeInTheDocument();
  expect(rowOf(table, "policy.pdf").getByText(/New edition 2/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Retry/ })).not.toBeInTheDocument();
});

test("an archived Project's Documents have no Retry", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({ documents: [aDocument()] });
  renderStudio(documentsTab(oldProject.id));

  expect((await documentsTable()).getByText("Ready")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Retry/ })).not.toBeInTheDocument();
});

test("a refused retry shows the API's reason", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({ documents: [aDocument()] });
  server.use(
    http.post(`${DOCUMENTS}/:documentId/retry`, async () => {
      await delay(200);
      return HttpResponse.json({ detail: BUSY }, { status: 409 });
    }),
  );
  renderStudio(documentsTab());
  const table = await documentsTable();

  await userEvent.click(rowOf(table, "handbook.pdf").getByRole("button", { name: "Retry handbook.pdf" }));

  expect(rowOf(table, "handbook.pdf").getByRole("button", { name: "Retry handbook.pdf" })).toBeDisabled();
  expect(await screen.findByRole("alert")).toHaveTextContent(BUSY);
  expect(rowOf(table, "handbook.pdf").getByText("Ready")).toBeInTheDocument();
});

test("a retry that fails without a reason asks to try again", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({ documents: [aDocument()] });
  server.use(http.post(`${DOCUMENTS}/:documentId/retry`, () => new HttpResponse("Bad gateway", { status: 502 })));
  renderStudio(documentsTab());
  const table = await documentsTable();

  await userEvent.click(rowOf(table, "handbook.pdf").getByRole("button", { name: "Retry handbook.pdf" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("The retry failed. Try again.");
});
