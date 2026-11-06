import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { aChunk, aDocument, fakeDocumentViewerApi } from "../test/documents";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const project = `/organisations/${organisationId}/projects/${hrProject.id}`;
const handbook = aDocument({ name: "Staff handbook.pdf", chunk_count: 4 });
const viewer = `${project}/documents/${handbook.id}`;
const API_DOCUMENT =
  "*/api/organisations/:organisationId/projects/:projectId/documents/:documentId";

// The first render of a test file is slow on a busy machine (the markdown renderer warms up).
const LOAD = { timeout: 5000 };

const MARKDOWN = `## Northwind staff handbook

Welcome to **Northwind Traders**.

### Annual leave

| Years | Days |
| --- | --- |
| 0–5 | 25 |
`;

const handbookChunks = [
  aChunk({
    ordinal: 0,
    heading_path: ["Northwind staff handbook"],
    page_start: 1,
    page_end: 1,
    text: "Welcome to Northwind Traders.",
  }),
  aChunk({
    ordinal: 1,
    heading_path: ["Northwind staff handbook", "Annual leave"],
    page_start: 1,
    page_end: 2,
    text: "Everyone gets 25 days.",
  }),
  aChunk({
    ordinal: 2,
    heading_path: ["Expenses"],
    page_start: 3,
    page_end: null,
    text: "Claim within 30 days.",
  }),
  aChunk({
    ordinal: 3,
    heading_path: [],
    page_start: null,
    page_end: null,
    text: "Footnotes.",
  }),
];

function signedIn() {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
}

test("an Editor opens a Document from the list and sees its markdown beside its Chunks", async () => {
  signedIn();
  fakeDocumentViewerApi({
    document: { ...handbook, markdown: MARKDOWN },
    chunks: handbookChunks,
  });
  renderStudio(project);

  await userEvent.click(
    await screen.findByRole("link", { name: "Staff handbook.pdf" }, LOAD),
  );

  expect(
    await screen.findByRole(
      "heading",
      { level: 2, name: "Staff handbook.pdf" },
      LOAD,
    ),
  ).toBeInTheDocument();
  // The converted markdown is rendered, not shown as source.
  const markdown = within(
    screen.getByRole("region", { name: "Converted markdown" }),
  );
  expect(
    markdown.getByRole("heading", { name: "Northwind staff handbook" }),
  ).toBeInTheDocument();
  expect(
    markdown.getByRole("heading", { name: "Annual leave" }),
  ).toBeInTheDocument();
  expect(markdown.getByText("Northwind Traders").tagName).toBe("STRONG");
  expect(markdown.getByRole("cell", { name: "25" })).toBeInTheDocument();
  // Each Chunk shows its heading path and pages.
  const list = within(screen.getByRole("region", { name: "Chunks" }));
  const items = await list.findAllByRole("listitem", {}, LOAD);
  expect(items.map((item) => item.textContent)).toEqual([
    "Chunk 1Northwind staff handbookPage 1Welcome to Northwind Traders.",
    "Chunk 2Northwind staff handbook › Annual leavePages 1–2Everyone gets 25 days.",
    "Chunk 3ExpensesPage 3Claim within 30 days.",
    "Chunk 4Footnotes.",
  ]);
  expect(list.getByText("Chunks 1–4 of 4")).toBeInTheDocument();
  expect(list.queryByRole("navigation")).not.toBeInTheDocument();
}, 15000);

test("the original file downloads through the API, which redirects to a presigned GET", async () => {
  signedIn();
  fakeDocumentViewerApi({
    document: { ...handbook, markdown: MARKDOWN },
    chunks: handbookChunks,
  });
  renderStudio(viewer);

  const download = await screen.findByRole(
    "link",
    { name: "Download original" },
    LOAD,
  );

  expect(download).toHaveAttribute(
    "href",
    `/api/organisations/${organisationId}/projects/${hrProject.id}/documents/${handbook.id}/download`,
  );
  expect(download).toHaveAttribute("download", "Staff handbook.pdf");
});

test("the Chunk list of a large Document pages through the API", async () => {
  signedIn();
  const many = Array.from({ length: 120 }, (_, ordinal) =>
    aChunk({
      ordinal,
      id: `c${String(ordinal)}`,
      heading_path: [`Section ${String(ordinal + 1)}`],
      text: `Policy ${String(ordinal + 1)}.`,
    }),
  );
  const { requests } = fakeDocumentViewerApi({
    document: { ...handbook, chunk_count: 120, markdown: MARKDOWN },
    chunks: many,
  });
  renderStudio(viewer);
  const chunks = within(
    await screen.findByRole("region", { name: "Chunks" }, LOAD),
  );
  const pages = () =>
    within(chunks.getByRole("navigation", { name: "Chunk pages" }));

  expect(await chunks.findByText("Chunks 1–50 of 120")).toBeInTheDocument();
  expect(chunks.getAllByRole("listitem")).toHaveLength(50);
  expect(pages().getByRole("button", { name: "Previous" })).toBeDisabled();

  await userEvent.click(pages().getByRole("button", { name: "Next" }));
  expect(await chunks.findByText("Chunks 51–100 of 120")).toBeInTheDocument();
  expect(chunks.getByText("Policy 51.")).toBeInTheDocument();

  await userEvent.click(pages().getByRole("button", { name: "Next" }));
  expect(await chunks.findByText("Chunks 101–120 of 120")).toBeInTheDocument();
  expect(chunks.getAllByRole("listitem")).toHaveLength(20);
  expect(pages().getByRole("button", { name: "Next" })).toBeDisabled();

  await userEvent.click(pages().getByRole("button", { name: "Previous" }));
  expect(await chunks.findByText("Chunks 51–100 of 120")).toBeInTheDocument();
  // Each page is asked for with its offset (going back may ask again for a page seen before).
  expect(requests.slice(0, 3)).toEqual([
    { offset: 0, limit: 50 },
    { offset: 50, limit: 50 },
    { offset: 100, limit: 50 },
  ]);
}, 15000);

test("a Document not converted yet says so instead of showing markdown and Chunks", async () => {
  signedIn();
  fakeDocumentViewerApi({
    document: {
      ...handbook,
      status: "failed",
      chunk_count: 0,
      error_message: "This Document couldn't be processed.",
      markdown: null,
    },
    chunks: [],
  });
  renderStudio(viewer);

  expect(
    await screen.findByText(
      "Failed: This Document couldn't be processed.",
      {},
      LOAD,
    ),
  ).toBeInTheDocument();
  const markdown = within(
    screen.getByRole("region", { name: "Converted markdown" }),
  );
  expect(
    markdown.getByText("There is no converted markdown yet."),
  ).toBeInTheDocument();
  const chunks = within(screen.getByRole("region", { name: "Chunks" }));
  expect(
    await chunks.findByText("This Document has no Chunks yet."),
  ).toBeInTheDocument();
});

test("a Document still processing shows its status", async () => {
  signedIn();
  fakeDocumentViewerApi({
    document: {
      ...handbook,
      status: "processing",
      chunk_count: 0,
      markdown: null,
    },
    chunks: [],
  });
  renderStudio(viewer);

  expect(await screen.findByText("Processing", {}, LOAD)).toBeInTheDocument();
});

test("a Document that can't be loaded says so", async () => {
  signedIn();
  server.use(
    http.get(API_DOCUMENT, () =>
      HttpResponse.json({ detail: "Not found" }, { status: 404 }),
    ),
  );
  renderStudio(viewer);

  expect(await screen.findByRole("alert", {}, LOAD)).toHaveTextContent(
    "This Document could not be loaded.",
  );
  expect(screen.getByRole("link", { name: "All Documents" })).toHaveAttribute(
    "href",
    project,
  );
});

test("Chunks that can't be loaded say so", async () => {
  signedIn();
  fakeDocumentViewerApi({
    document: { ...handbook, markdown: MARKDOWN },
    chunks: [],
  });
  server.use(
    http.get(`${API_DOCUMENT}/chunks`, () =>
      HttpResponse.json({ detail: "Not found" }, { status: 404 }),
    ),
  );
  renderStudio(viewer);

  const chunks = within(
    await screen.findByRole("region", { name: "Chunks" }, LOAD),
  );
  expect(await chunks.findByRole("alert")).toHaveTextContent(
    "The Chunks could not be loaded. Try again shortly.",
  );
});
