import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";

import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeProjectsApi, hrProject, oldProject, PROJECT_ARCHIVED } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const instructionsTab = (projectId: string) => `/organisations/${organisationId}/projects/${projectId}/instructions`;

const RULES = "# House rules\n\n- Answer in **British English**.\n- Never quote salaries.\n";

function setUp(instructions: Record<string, string> = { [hrProject.id]: RULES }) {
  fakeAuthApi({ signedInAs: adaSession });
  return fakeProjectsApi({ instructions });
}

async function openMarkdownView() {
  await userEvent.click(await screen.findByRole("button", { name: "Markdown" }, { timeout: 5000 }));
  return screen.getByRole("textbox", { name: "Project Instructions (Markdown)" });
}

test("the Project Instructions show formatted in the markdown editor", async () => {
  setUp();
  renderStudio(instructionsTab(hrProject.id));

  const editor = await screen.findByRole("textbox", { name: "Project Instructions" }, { timeout: 5000 });
  expect(within(editor).getByRole("heading", { level: 1, name: "House rules" })).toBeInTheDocument();
  expect(within(editor).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
    "Answer in British English.",
    "Never quote salaries.",
  ]);
  expect(within(editor).getByText("British English").tagName).toBe("STRONG");
  expect(screen.getByText(/They come before each Agent's system prompt/)).toBeInTheDocument();
});

test("an Editor rewrites the Instructions and saves exactly the markdown written", async () => {
  const { requests } = setUp();
  renderStudio(instructionsTab(hrProject.id));
  const source = await openMarkdownView();
  // The Markdown view starts from the saved text, unchanged.
  expect(source).toHaveValue(RULES);

  await userEvent.clear(source);
  await userEvent.type(source, "Use <context> & cite [[C1]. Answer in snake_case{enter}");
  await userEvent.click(screen.getByRole("button", { name: "Save Instructions" }));

  expect(await screen.findByRole("status")).toHaveTextContent("Instructions saved");
  expect(requests).toEqual([
    { route: "instructions", projectId: hrProject.id, body: { markdown: "Use <context> & cite [C1]. Answer in snake_case\n" } },
  ]);
});

test("saving untouched Instructions sends them back unchanged", async () => {
  // A spelling the rich editor would write differently is still what is saved.
  const { requests } = setUp({ [hrProject.id]: "* one\n* two" });
  renderStudio(instructionsTab(hrProject.id));
  await screen.findByRole("textbox", { name: "Project Instructions" }, { timeout: 5000 });

  await userEvent.click(screen.getByRole("button", { name: "Save Instructions" }));

  expect(await screen.findByRole("status")).toHaveTextContent("Instructions saved");
  expect(requests).toEqual([{ route: "instructions", projectId: hrProject.id, body: { markdown: "* one\n* two" } }]);
});

test("a new Project starts with empty Instructions", async () => {
  setUp({});
  renderStudio(instructionsTab(hrProject.id));

  expect(await openMarkdownView()).toHaveValue("");
});

test("Instructions the API refuses show why", async () => {
  setUp();
  renderStudio(instructionsTab(hrProject.id));
  const source = await openMarkdownView();
  source.removeAttribute("maxlength");

  await userEvent.clear(source);
  await userEvent.click(source);
  await userEvent.paste("x".repeat(20_001));
  await userEvent.click(screen.getByRole("button", { name: "Save Instructions" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Instructions can be up to 20,000 characters.");
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

test("a Project archived elsewhere refuses the save with the API's reason", async () => {
  setUp();
  server.use(
    http.put("*/api/organisations/:organisationId/projects/:projectId/instructions", () =>
      HttpResponse.json({ detail: PROJECT_ARCHIVED }, { status: 409 }),
    ),
  );
  renderStudio(instructionsTab(hrProject.id));
  await screen.findByRole("textbox", { name: "Project Instructions" }, { timeout: 5000 });

  await userEvent.click(screen.getByRole("button", { name: "Save Instructions" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(PROJECT_ARCHIVED);
});

test("a save shows its progress, and a failure asks to try again", async () => {
  setUp();
  server.use(
    http.put("*/api/organisations/:organisationId/projects/:projectId/instructions", async () => {
      await delay(100);
      return HttpResponse.json({ detail: "boom" }, { status: 500 });
    }),
  );
  renderStudio(instructionsTab(hrProject.id));
  await screen.findByRole("textbox", { name: "Project Instructions" }, { timeout: 5000 });

  await userEvent.click(screen.getByRole("button", { name: "Save Instructions" }));

  expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("an archived Project's Instructions are read-only", async () => {
  setUp({ [oldProject.id]: "Old rules" });
  renderStudio(instructionsTab(oldProject.id));

  const editor = await screen.findByRole("textbox", { name: "Project Instructions" }, { timeout: 5000 });
  expect(editor).toHaveTextContent("Old rules");
  expect(editor).toHaveAttribute("contenteditable", "false");
  expect(screen.queryByRole("button", { name: "Save Instructions" })).not.toBeInTheDocument();
  expect(screen.getByText(/Restore the Project to edit its Instructions/)).toBeInTheDocument();
});

test("Instructions that can't be loaded say so", async () => {
  setUp();
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/instructions", () =>
      HttpResponse.json({ detail: "boom" }, { status: 500 }),
    ),
  );
  renderStudio(instructionsTab(hrProject.id));

  expect(await screen.findByText("The Instructions could not be loaded. Try again shortly.", {}, { timeout: 5000 })).toBeInTheDocument();
});
