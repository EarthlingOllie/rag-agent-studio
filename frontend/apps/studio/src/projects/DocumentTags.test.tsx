import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import {
  aDocument,
  aTag,
  DUPLICATE_TAG,
  fakeDocumentsApi,
} from "../test/documents";
import { fakeProjectsApi, hrProject, oldProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const documentsTab = (projectId = hrProject.id) =>
  `/organisations/${organisationId}/projects/${projectId}`;
const TAGS = "*/api/organisations/:organisationId/projects/:projectId/tags";

const hr = aTag({ id: "7a900000-0000-4000-8000-000000000001", name: "HR" });
const policy = aTag({
  id: "7a900000-0000-4000-8000-000000000002",
  name: "Policy",
});
const sales = aTag({
  id: "7a900000-0000-4000-8000-000000000003",
  name: "Sales",
});
const leave = aDocument({
  id: "d0c00000-0000-4000-8000-000000000011",
  name: "Leave policy.pdf",
  tags: [{ id: hr.id, name: "HR" }],
});
const expenses = aDocument({
  id: "d0c00000-0000-4000-8000-000000000012",
  name: "Expenses.docx",
});
const deck = aDocument({
  id: "d0c00000-0000-4000-8000-000000000013",
  name: "Sales deck.pptx",
  status: "failed",
  error_message: "This Document couldn't be processed. Try uploading it again.",
  chunk_count: 0,
});

function start(
  options: Parameters<typeof fakeDocumentsApi>[0] = {},
  projectId = hrProject.id,
) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const fake = fakeDocumentsApi({
    documents: [leave, expenses, deck],
    tags: [hr, policy, sales],
    ...options,
  });
  renderStudio(documentsTab(projectId));
  return fake;
}

async function tagsPanel() {
  return within(await screen.findByRole("region", { name: "Tags" }));
}

async function documentNames() {
  const table = within(await screen.findByRole("table", { name: "Documents" }));
  return table
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell")[1]?.textContent);
}

function rowOf(name: string) {
  const cell = within(
    screen.getByRole("table", { name: "Documents" }),
  ).getByRole("cell", { name });
  return within(cell.closest("tr") as HTMLElement);
}

test("an Editor creates Tags and sees them listed by name with their Document counts", async () => {
  const { requests } = start({ tags: [hr, sales] });
  const panel = await tagsPanel();
  expect(await panel.findByText("HR")).toBeInTheDocument();
  expect(panel.getByText("1 Document")).toBeInTheDocument();
  expect(panel.getByText("0 Documents")).toBeInTheDocument();

  await userEvent.type(panel.getByLabelText("New Tag"), "  benefits ");
  await userEvent.click(panel.getByRole("button", { name: "Add Tag" }));

  expect(await panel.findByText("benefits")).toBeInTheDocument();
  expect(
    panel
      .getAllByRole("listitem")
      .map((item) => within(item).getByTestId("tag-name").textContent),
  ).toEqual(["benefits", "HR", "Sales"]);
  expect(panel.getByLabelText("New Tag")).toHaveValue("");
  expect(
    requests.filter((r) => r.route === "createTag").map((r) => r.body),
  ).toEqual(["benefits"]);
});

test("a duplicate or blank Tag name is refused with the reason", async () => {
  start();
  const panel = await tagsPanel();
  await panel.findByText("Policy");

  await userEvent.click(panel.getByRole("button", { name: "Add Tag" }));
  expect(panel.getByRole("alert")).toHaveTextContent("Give the Tag a name.");

  await userEvent.type(panel.getByLabelText("New Tag"), "hr");
  await userEvent.click(panel.getByRole("button", { name: "Add Tag" }));

  expect(await panel.findByRole("alert")).toHaveTextContent(DUPLICATE_TAG);
  expect(panel.getByLabelText("New Tag")).toHaveValue("hr");
});

test("an Editor renames a Tag, and Documents show the new name", async () => {
  start();
  const panel = await tagsPanel();
  await userEvent.click(
    await panel.findByRole("button", { name: "Rename HR" }),
  );
  const name = panel.getByLabelText("Name for HR");
  expect(name).toHaveValue("HR");

  await userEvent.clear(name);
  await userEvent.type(name, "People");
  await userEvent.click(panel.getByRole("button", { name: "Save" }));

  expect(await panel.findByText("People")).toBeInTheDocument();
  await waitFor(() => {
    expect(tagsOf("Leave policy.pdf")).toEqual(["People"]);
  });
});

test("renaming a Tag to one that exists shows why, and can be cancelled", async () => {
  start();
  const panel = await tagsPanel();
  await userEvent.click(
    await panel.findByRole("button", { name: "Rename HR" }),
  );
  const name = panel.getByLabelText("Name for HR");

  await userEvent.clear(name);
  await userEvent.type(name, "sales");
  await userEvent.click(panel.getByRole("button", { name: "Save" }));
  expect(await panel.findByRole("alert")).toHaveTextContent(DUPLICATE_TAG);

  await userEvent.click(panel.getByRole("button", { name: "Cancel" }));
  expect(panel.queryByLabelText("Name for HR")).not.toBeInTheDocument();
  expect(panel.getByText("HR")).toBeInTheDocument();
});

test("an Editor deletes a Tag after confirming, and it leaves every Document", async () => {
  const { requests } = start();
  const panel = await tagsPanel();

  await userEvent.click(
    await panel.findByRole("button", { name: "Delete HR" }),
  );
  expect(
    panel.getByText(
      "Delete HR? It is taken off 1 Document. The Documents stay.",
    ),
  ).toBeInTheDocument();
  await userEvent.click(panel.getByRole("button", { name: "Keep it" }));
  expect(requests.filter((r) => r.route === "deleteTag")).toHaveLength(0);

  await userEvent.click(panel.getByRole("button", { name: "Delete HR" }));
  await userEvent.click(panel.getByRole("button", { name: "Delete Tag" }));

  await waitForGone(() => panel.queryByText("HR"));
  expect(
    requests.filter((r) => r.route === "deleteTag").map((r) => r.body),
  ).toEqual([hr.id]);
  await waitFor(() => {
    expect(tagsOf("Leave policy.pdf")).toEqual([]);
  });
});

/** The Tag names a Document's row shows. */
function tagsOf(name: string) {
  const list = rowOf(name).queryByRole("list", { name: "Tags" });
  return list
    ? within(list)
        .getAllByRole("listitem")
        .map((item) => item.textContent)
    : [];
}

async function waitForGone(query: () => HTMLElement | null) {
  await waitFor(() => {
    expect(query()).not.toBeInTheDocument();
  });
}

test("a Tag change the API refuses without a reason says to try again", async () => {
  start();
  server.use(
    http.post(TAGS, () => new HttpResponse("Bad gateway", { status: 502 })),
    http.delete(
      `${TAGS}/:tagId`,
      () => new HttpResponse("Bad gateway", { status: 502 }),
    ),
  );
  const panel = await tagsPanel();

  await userEvent.type(await panel.findByLabelText("New Tag"), "Finance");
  await userEvent.click(panel.getByRole("button", { name: "Add Tag" }));
  expect(await panel.findByRole("alert")).toHaveTextContent(
    "Something went wrong. Try again.",
  );

  await userEvent.click(panel.getByRole("button", { name: "Delete Sales" }));
  await userEvent.click(panel.getByRole("button", { name: "Delete Tag" }));
  expect(
    await panel.findAllByText("Something went wrong. Try again."),
  ).toHaveLength(2);
});

test("the Tags say when they can't be loaded", async () => {
  start();
  server.use(
    http.get(TAGS, () =>
      HttpResponse.json({ detail: "Not found" }, { status: 404 }),
    ),
  );

  expect(
    await screen.findByText("The Tags could not be loaded. Try again shortly."),
  ).toBeInTheDocument();
});

test("an Editor applies several Tags to one Document", async () => {
  const { requests } = start();
  await screen.findByRole("table", { name: "Documents" });

  await userEvent.click(
    rowOf("Leave policy.pdf").getByRole("button", {
      name: "Edit Tags for Leave policy.pdf",
    }),
  );
  const editor = within(
    screen.getByRole("group", { name: "Tags for Leave policy.pdf" }),
  );
  expect(editor.getByRole("checkbox", { name: "HR" })).toBeChecked();
  await userEvent.click(editor.getByRole("checkbox", { name: "Policy" }));
  await userEvent.click(editor.getByRole("checkbox", { name: "Sales" }));
  await userEvent.click(editor.getByRole("checkbox", { name: "Sales" }));
  await userEvent.click(editor.getByRole("button", { name: "Save Tags" }));

  await waitFor(() => {
    expect(tagsOf("Leave policy.pdf")).toEqual(["HR", "Policy"]);
  });
  expect(
    screen.queryByRole("group", { name: "Tags for Leave policy.pdf" }),
  ).not.toBeInTheDocument();
  expect(
    requests.filter((r) => r.route === "setTags").map((r) => r.body),
  ).toEqual([{ tag_ids: [hr.id, policy.id] }]);
});

test("editing one Document's Tags can be cancelled, and a refusal shows its reason", async () => {
  start();
  await screen.findByRole("table", { name: "Documents" });
  await userEvent.click(
    rowOf("Expenses.docx").getByRole("button", {
      name: "Edit Tags for Expenses.docx",
    }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(
    screen.queryByRole("group", { name: "Tags for Expenses.docx" }),
  ).not.toBeInTheDocument();

  server.use(
    http.put(
      "*/api/organisations/:organisationId/projects/:projectId/documents/:documentId/tags",
      () =>
        HttpResponse.json(
          { detail: "This Project is archived. An Owner can restore it." },
          { status: 409 },
        ),
    ),
  );
  await userEvent.click(
    rowOf("Expenses.docx").getByRole("button", {
      name: "Edit Tags for Expenses.docx",
    }),
  );
  await userEvent.click(screen.getByRole("checkbox", { name: "HR" }));
  await userEvent.click(screen.getByRole("button", { name: "Save Tags" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "This Project is archived. An Owner can restore it.",
  );
});

test("a Project without Tags says how to add them when editing a Document's Tags", async () => {
  start({ tags: [] });
  await screen.findByRole("table", { name: "Documents" });

  await userEvent.click(
    rowOf("Expenses.docx").getByRole("button", {
      name: "Edit Tags for Expenses.docx",
    }),
  );

  expect(
    screen.getByText("This Project has no Tags yet. Add one under Tags."),
  ).toBeInTheDocument();
});

test("an Editor bulk-applies a Tag to many Documents and takes it off again", async () => {
  const { requests } = start();
  await screen.findByRole("table", { name: "Documents" });
  expect(
    screen.queryByRole("group", { name: "Bulk tagging" }),
  ).not.toBeInTheDocument();

  await userEvent.click(
    screen.getByRole("checkbox", { name: "Select Leave policy.pdf" }),
  );
  await userEvent.click(
    screen.getByRole("checkbox", { name: "Select Expenses.docx" }),
  );
  const bulk = within(screen.getByRole("group", { name: "Bulk tagging" }));
  expect(bulk.getByText("2 selected")).toBeInTheDocument();
  await userEvent.selectOptions(bulk.getByLabelText("Tag"), "Policy");
  await userEvent.click(
    bulk.getByRole("button", { name: "Apply to selected" }),
  );

  await waitFor(() => {
    expect(tagsOf("Expenses.docx")).toEqual(["Policy"]);
  });
  expect(tagsOf("Leave policy.pdf")).toEqual(["HR", "Policy"]);

  await userEvent.selectOptions(bulk.getByLabelText("Tag"), "HR");
  await userEvent.click(
    bulk.getByRole("button", { name: "Remove from selected" }),
  );

  await waitFor(() => {
    expect(tagsOf("Leave policy.pdf")).toEqual(["Policy"]);
  });
  expect(
    requests.filter((r) => r.route === "bulkTag").map((r) => r.body),
  ).toEqual([
    { document_ids: [leave.id, expenses.id], add: [policy.id] },
    { document_ids: [leave.id, expenses.id], remove: [hr.id] },
  ]);

  await userEvent.click(bulk.getByRole("button", { name: "Clear selection" }));
  expect(
    screen.queryByRole("group", { name: "Bulk tagging" }),
  ).not.toBeInTheDocument();
});

test("select all picks every listed Document, and a bulk refusal shows its reason", async () => {
  const { requests } = start();
  await screen.findByRole("table", { name: "Documents" });
  server.use(
    http.post(
      "*/api/organisations/:organisationId/projects/:projectId/documents/tags",
      () =>
        HttpResponse.json(
          { detail: "One or more of these Documents aren't in this Project." },
          { status: 422 },
        ),
    ),
  );

  const all = screen.getByRole("checkbox", { name: "Select all Documents" });
  await userEvent.click(all);
  const bulk = within(screen.getByRole("group", { name: "Bulk tagging" }));
  expect(bulk.getByText("3 selected")).toBeInTheDocument();
  expect(
    bulk.getByRole("button", { name: "Apply to selected" }),
  ).toBeDisabled();
  await userEvent.selectOptions(bulk.getByLabelText("Tag"), "Sales");
  await userEvent.click(
    bulk.getByRole("button", { name: "Apply to selected" }),
  );

  expect(await bulk.findByRole("alert")).toHaveTextContent(
    "One or more of these Documents aren't in this Project.",
  );
  expect(requests.filter((r) => r.route === "bulkTag")).toHaveLength(0);

  await userEvent.click(
    screen.getByRole("checkbox", { name: "Select Sales deck.pptx" }),
  );
  expect(all).not.toBeChecked();
  expect(bulk.getByText("2 selected")).toBeInTheDocument();
  await userEvent.click(all);
  await userEvent.click(all);
  expect(
    screen.queryByRole("group", { name: "Bulk tagging" }),
  ).not.toBeInTheDocument();
});

test("the Document list is searched by name and filtered by status and Tag", async () => {
  const { requests } = start();
  expect(await documentNames()).toEqual([
    "Leave policy.pdf",
    "Expenses.docx",
    "Sales deck.pptx",
  ]);

  await userEvent.type(
    screen.getByRole("searchbox", { name: "Search by name" }),
    "e",
  );
  await userEvent.selectOptions(screen.getByLabelText("Status"), "Ready");
  await screen.findByText("Expenses.docx");
  expect(await documentNames()).toEqual(["Leave policy.pdf", "Expenses.docx"]);

  await userEvent.selectOptions(screen.getByLabelText("Filter by Tag"), "HR");
  await waitForGone(() => screen.queryByText("Expenses.docx"));
  expect(await documentNames()).toEqual(["Leave policy.pdf"]);
  expect(requests.filter((r) => r.route === "list").at(-1)?.body).toBe(
    `q=e&status=ready&tag_id=${hr.id}`,
  );

  await userEvent.selectOptions(screen.getByLabelText("Status"), "Failed");
  expect(
    await screen.findByText("No Documents match these filters."),
  ).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  await screen.findByText("Sales deck.pptx");
  expect(await documentNames()).toEqual([
    "Leave policy.pdf",
    "Expenses.docx",
    "Sales deck.pptx",
  ]);
  expect(screen.getByRole("searchbox", { name: "Search by name" })).toHaveValue(
    "",
  );
  expect(
    screen.queryByRole("button", { name: "Clear filters" }),
  ).not.toBeInTheDocument();
});

test("an archived Project's Tags are shown but can't be changed", async () => {
  start({}, oldProject.id);
  const panel = await tagsPanel();

  expect(await panel.findByText("Policy")).toBeInTheDocument();
  expect(panel.queryByLabelText("New Tag")).not.toBeInTheDocument();
  expect(
    panel.queryByRole("button", { name: "Rename HR" }),
  ).not.toBeInTheDocument();
  await screen.findByRole("table", { name: "Documents" });
  expect(
    screen.queryByRole("button", { name: /Edit Tags/ }),
  ).not.toBeInTheDocument();
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  expect(tagsOf("Leave policy.pdf")).toEqual(["HR"]);
});
