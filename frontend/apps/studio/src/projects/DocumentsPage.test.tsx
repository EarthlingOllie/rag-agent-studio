/**
 * The Documents section as the mockup draws it (ticket 11-06): stat cards, the toolbar, the table
 * with its ⋯ row menus, the Tags dialog, the bulk bar, and confirmations as toasts and notices.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { aDocument, aTag, fakeDocumentsApi } from "../test/documents";
import { fakeProjectsApi, hrProject, oldProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const documentsTab = (projectId = hrProject.id) => `/organisations/${organisationId}/projects/${projectId}`;

const hr = aTag({ id: "7a900000-0000-4000-8000-000000000001", name: "HR" });
const policy = aTag({ id: "7a900000-0000-4000-8000-000000000002", name: "Policy" });
const handbook = aDocument({ chunk_count: 12, flagged_chunk_count: 2, tags: [{ id: hr.id, name: "HR" }] });
const faq = aDocument({
  id: "d0c00000-0000-4000-8000-000000000002",
  name: "faq.md",
  mime_type: "text/markdown",
  size_bytes: 512,
  chunk_count: 3,
});
const slides = aDocument({
  id: "d0c00000-0000-4000-8000-000000000003",
  name: "launch.pptx",
  status: "processing",
  chunk_count: 0,
});

function start(options: Parameters<typeof fakeDocumentsApi>[0] = {}, projectId = hrProject.id) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const fake = fakeDocumentsApi({ documents: [handbook, faq], tags: [hr, policy], ...options });
  // Statuses stay as given: these tests are about the page, not about ingestion moving on.
  server.use(http.get("*/api/organisations/:organisationId/projects/:projectId/documents/statuses", () => HttpResponse.json([])));
  renderStudio(documentsTab(projectId));
  return fake;
}

async function documentsTable() {
  return within(await screen.findByRole("table", { name: "Documents" }));
}

/** The value printed on the stat card with this label. */
function statCard(label: string) {
  const stats = within(screen.getByRole("region", { name: "Knowledge Base" }));
  return stats.getByText(label, { selector: "span" }).nextElementSibling as HTMLElement;
}

async function rowMenu(name: string) {
  const table = await documentsTable();
  await userEvent.click(table.getByRole("button", { name: `More actions for ${name}` }));
  return within(screen.getByRole("menu", { name: `Actions for ${name}` }));
}

test("stat cards show Documents against the quota, Chunks, flagged chunks in the flag colour, and the Embedding Model", async () => {
  start({ limits: { document_quota: 500 } });
  await documentsTable();

  await waitFor(() => {
    expect(statCard("Documents")).toHaveTextContent("2 / 500");
  });
  expect(statCard("Chunks")).toHaveTextContent(/^15$/);
  expect(statCard("Flagged chunks")).toHaveTextContent(/^2$/);
  expect(statCard("Flagged chunks")).toHaveClass("text-flag");
  expect(statCard("Embedding Model")).toHaveTextContent("multilingual-e5-small");

  // A filter narrows the table, not the Project's figures.
  await userEvent.type(screen.getByRole("searchbox", { name: "Search by name" }), "faq");
  await waitFor(() => {
    expect(within(screen.getByRole("table", { name: "Documents" })).queryByText("handbook.pdf")).not.toBeInTheDocument();
  });
  expect(statCard("Chunks")).toHaveTextContent(/^15$/);
});

test("no flagged chunks keeps the stat card's quiet colour", async () => {
  start({ documents: [faq] });
  await documentsTable();
  expect(statCard("Flagged chunks")).toHaveTextContent(/^0$/);
  expect(statCard("Flagged chunks")).not.toHaveClass("text-flag");
});

test("rows show the file type, Tag pills, a status dot and the flagged count", async () => {
  start({ documents: [handbook, faq, slides] });
  const table = await documentsTable();
  const headers = table.getAllByRole("columnheader").map((header) => header.textContent);
  expect(headers).toEqual(["Select", "Name", "Type", "Tags", "Status", "Chunks", "Flagged", "Size", "Actions"]);

  const row = (name: string) => within(table.getByRole("link", { name }).closest("tr") as HTMLElement);
  expect(row("handbook.pdf").getByText("PDF")).toBeInTheDocument();
  expect(row("faq.md").getByText("Markdown")).toBeInTheDocument();
  expect(row("launch.pptx").getByText("PPTX")).toBeInTheDocument();
  expect(within(row("handbook.pdf").getByRole("list", { name: "Tags" })).getByText("HR")).toHaveClass("bg-sand");
  expect(row("handbook.pdf").getByText("Ready")).toBeInTheDocument();
  expect(row("launch.pptx").getByText("Processing")).toBeInTheDocument();
  expect(row("handbook.pdf").getByLabelText("2 flagged chunks")).toHaveTextContent("2");
  expect(row("faq.md").getByLabelText("No flagged chunks")).toBeInTheDocument();
});

test("Retry, New edition, Edit Tags and Delete are in each row's ⋯ menu, as far as the Document allows", async () => {
  start({ documents: [handbook, slides] });
  const table = await documentsTable();
  expect(table.queryByRole("button", { name: /^(Retry|Delete) / })).not.toBeInTheDocument();

  const ready = await rowMenu("handbook.pdf");
  expect(ready.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Retry", "New edition", "Edit Tags", "Delete"]);
  await userEvent.keyboard("{Escape}");

  // A Document still being processed can't be retried or replaced yet.
  const busy = await rowMenu("launch.pptx");
  expect(busy.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Edit Tags", "Delete"]);
});

test("an archived Project's rows have no ⋯ menu, no selection and no Upload", async () => {
  start({}, oldProject.id);
  const table = await documentsTable();
  expect(table.queryByRole("button", { name: /More actions/ })).not.toBeInTheDocument();
  expect(table.queryByRole("checkbox")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Upload")).not.toBeInTheDocument();
  expect(screen.queryByTestId("dropzone")).not.toBeInTheDocument();
});

test("Delete asks in a ConfirmDialog, then confirms with a toast", async () => {
  const { requests } = start();
  const menu = await rowMenu("handbook.pdf");
  await userEvent.click(menu.getByRole("menuitem", { name: "Delete" }));

  const dialog = within(screen.getByRole("alertdialog", { name: "Delete handbook.pdf?" }));
  expect(dialog.getByText("Its 12 chunks stop being retrieved at once.")).toBeInTheDocument();
  expect(dialog.getByRole("button", { name: "Cancel" })).toHaveFocus();
  await userEvent.click(dialog.getByRole("button", { name: "Delete handbook.pdf" }));

  expect(await screen.findByText("Deleted handbook.pdf.")).toBeInTheDocument();
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(requests.filter((r) => r.route === "delete").map((r) => r.body)).toEqual([handbook.id]);
});

test("Retry is confirmed with a toast", async () => {
  start({ documents: [faq] });
  await userEvent.click((await rowMenu("faq.md")).getByRole("menuitem", { name: "Retry" }));
  expect(await screen.findByText("Retrying faq.md.")).toBeInTheDocument();
});

test("Manage tags opens the Tags panel in a dialog", async () => {
  start();
  await documentsTable();
  expect(screen.queryByRole("region", { name: "Tags" })).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Manage tags" }));
  const dialog = within(screen.getByRole("dialog", { name: "Tags" }));
  expect(await dialog.findByText("Policy")).toBeInTheDocument();
  expect(dialog.getByLabelText("New Tag")).toBeInTheDocument();

  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Manage tags" })).toHaveFocus();
});

test("the Tag chips filter the list, with All for every Document", async () => {
  const { requests } = start();
  await documentsTable();
  const chips = within(screen.getByRole("radiogroup", { name: "Filter by Tag" }));
  expect(chips.getAllByRole("radio").map((chip) => chip.textContent)).toEqual(["All", "HR", "Policy"]);
  expect(chips.getByRole("radio", { name: "All" })).toBeChecked();

  await userEvent.click(chips.getByRole("radio", { name: "HR" }));
  await waitFor(() => {
    expect(within(screen.getByRole("table", { name: "Documents" })).queryByText("faq.md")).not.toBeInTheDocument();
  });
  expect(requests.filter((r) => r.route === "list").at(-1)?.body).toBe(`tag_id=${hr.id}`);

  await userEvent.click(chips.getByRole("radio", { name: "All" }));
  expect(await screen.findByText("faq.md")).toBeInTheDocument();
});

test("selecting Documents shows the bulk bar, which adds and removes a Tag with a toast", async () => {
  const { requests } = start();
  const table = await documentsTable();
  expect(screen.queryByRole("toolbar", { name: "Bulk actions" })).not.toBeInTheDocument();

  await userEvent.click(table.getByRole("checkbox", { name: "Select all Documents" }));
  const bar = within(screen.getByRole("toolbar", { name: "Bulk actions" }));
  expect(bar.getByText("2 Documents selected")).toBeInTheDocument();

  await userEvent.click(bar.getByRole("button", { name: "Add Tag" }));
  await userEvent.click(within(screen.getByRole("menu", { name: "Add a Tag to the selected Documents" })).getByRole("menuitem", { name: "Policy" }));
  expect(await screen.findByText("Added Policy to 2 Documents.")).toBeInTheDocument();

  await userEvent.click(bar.getByRole("button", { name: "Remove Tag" }));
  await userEvent.click(within(screen.getByRole("menu", { name: "Remove a Tag from the selected Documents" })).getByRole("menuitem", { name: "HR" }));
  expect(await screen.findByText("Removed HR from 2 Documents.")).toBeInTheDocument();
  expect(requests.filter((r) => r.route === "bulkTag").map((r) => r.body)).toEqual([
    { document_ids: [handbook.id, faq.id], add: [policy.id] },
    { document_ids: [handbook.id, faq.id], remove: [hr.id] },
  ]);

  await userEvent.click(bar.getByRole("button", { name: "Clear selection" }));
  expect(screen.queryByRole("toolbar", { name: "Bulk actions" })).not.toBeInTheDocument();
});

test("the bulk bar's Tag menus say so when the Project has no Tags", async () => {
  start({ tags: [] });
  const table = await documentsTable();
  await userEvent.click(table.getByRole("checkbox", { name: "Select handbook.pdf" }));
  const bar = within(screen.getByRole("toolbar", { name: "Bulk actions" }));
  expect(bar.getByText("1 Document selected")).toBeInTheDocument();
  expect(bar.getByRole("button", { name: "Add Tag" })).toBeDisabled();
  expect(bar.getByRole("button", { name: "Remove Tag" })).toBeDisabled();
});

test("a Tag saved for one Document is confirmed with a toast", async () => {
  start();
  await userEvent.click((await rowMenu("faq.md")).getByRole("menuitem", { name: "Edit Tags" }));
  const dialog = within(screen.getByRole("dialog", { name: "Tags for faq.md" }));
  await userEvent.click(dialog.getByRole("checkbox", { name: "Policy" }));
  await userEvent.click(dialog.getByRole("button", { name: "Save Tags" }));
  expect(await screen.findByText("Saved the Tags on faq.md.")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("failed Documents and a full quota are explained in notices above the table", async () => {
  const broken = aDocument({
    id: "d0c00000-0000-4000-8000-000000000009",
    name: "broken.md",
    status: "failed",
    error_category: "conversion",
    error_message: "Couldn't convert.",
    chunk_count: 0,
  });
  start({ documents: [faq, broken], limits: { document_quota: 1, documents_counted: 1 } });
  await documentsTable();

  const failures = await screen.findByText(/1 Document failed/);
  expect(failures).toHaveTextContent("1 Document failed to process. Retry it from its ⋯ menu, or upload a fixed copy.");
  expect(failures).toHaveAttribute("role", "status");
  const full = await screen.findByText(/reached its quota/);
  expect(full).toHaveTextContent(
    "This Project has reached its quota of 1 Document. Delete a Document, or ask an Owner to raise the quota.",
  );
  expect(full).toHaveAttribute("role", "status");
});

test("an empty Project shows an empty state, and loading shows a skeleton", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi();
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/documents", async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
      return HttpResponse.json([]);
    }),
  );
  renderStudio(documentsTab());
  expect(await screen.findByRole("status", { name: "Loading Documents" })).toBeInTheDocument();
  expect(await screen.findByRole("heading", { name: "No Documents yet" })).toBeInTheDocument();
  expect(screen.getByText("Upload files to build this Project's Knowledge Base.")).toBeInTheDocument();
});

test("Upload is the one primary action, and the drop zone stays quiet beside it", async () => {
  start();
  await documentsTable();
  expect(screen.getByLabelText("Upload")).toHaveAttribute("type", "file");
  expect(screen.getByTestId("dropzone")).toHaveTextContent(/Drop files here to upload/);
});

test("a file type the Studio doesn't name shows as File", async () => {
  start({ documents: [aDocument({ name: "README", mime_type: "text/plain" }), aDocument({ id: faq.id, name: "notes.TXT" })] });
  const table = await documentsTable();
  expect(within(table.getByRole("link", { name: "README" }).closest("tr") as HTMLElement).getByText("File")).toBeInTheDocument();
  expect(within(table.getByRole("link", { name: "notes.TXT" }).closest("tr") as HTMLElement).getByText("Text")).toBeInTheDocument();
});

test.each([
  [1, "Its 1 chunk stops being retrieved at once."],
  [0, "It has no chunks, so no Agent retrieves it."],
])("deleting a Document with %s chunks says what that does", async (chunks, consequence) => {
  start({ documents: [aDocument({ chunk_count: chunks })] });
  await userEvent.click((await rowMenu("handbook.pdf")).getByRole("menuitem", { name: "Delete" }));
  expect(within(screen.getByRole("alertdialog")).getByText(consequence)).toBeInTheDocument();
});

test("several failed Documents are counted in one notice", async () => {
  const failed = (id: string, name: string) => aDocument({ id, name, status: "failed", error_category: "conversion", chunk_count: 0 });
  start({ documents: [failed("d0c00000-0000-4000-8000-000000000021", "a.md"), failed("d0c00000-0000-4000-8000-000000000022", "b.md")] });
  expect(await screen.findByText(/2 Documents failed/)).toHaveTextContent(
    "2 Documents failed to process. Retry each from its ⋯ menu, or upload fixed copies.",
  );
});

test("Manage tags says so when the Project has no Tags yet", async () => {
  start({ tags: [] });
  await documentsTable();
  expect(screen.queryByRole("radiogroup", { name: "Filter by Tag" })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Manage tags" }));
  expect(await within(screen.getByRole("dialog", { name: "Tags" })).findByText("No Tags yet.")).toBeInTheDocument();
});
