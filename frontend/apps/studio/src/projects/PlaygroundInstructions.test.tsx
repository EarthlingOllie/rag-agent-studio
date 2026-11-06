import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";

import { CONVERSATION_ID, fakeAgentsApi, hrHelper, hrTrace } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeProjectsApi, hrProject, instructionsVersion } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";

const organisationId = adaSession.organisations[0]?.id ?? "";
const agentPage = `/organisations/${organisationId}/projects/${hrProject.id}/agents/${hrHelper.id}`;

const v1 = instructionsVersion(1, { note: "First rules" });
const v2 = instructionsVersion(2, { note: "Salaries", previous_version_id: v1.id });
const v3 = instructionsVersion(3, { note: "Shorter", previous_version_id: v2.id });

/** Three Versions, v2 Current (v3 was published, then reverted). */
function setUp(options: Parameters<typeof fakeAgentsApi>[0] = {}) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi({ versions: { [hrProject.id]: { current_version_id: v2.id, versions: [v3, v2, v1] } } });
  return fakeAgentsApi({ agents: [hrHelper], ...options });
}

async function picker() {
  return screen.findByRole("combobox", { name: "Instructions" }, { timeout: 5000 });
}

async function ask(question: string) {
  await userEvent.type(screen.getByLabelText("Question"), question);
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  const answers = await within(screen.getByRole("list", { name: "Playground messages" })).findAllByRole("listitem", {
    name: "HR helper",
  });
  const answer = answers.at(-1) as HTMLElement;
  await within(answer).findByText(/output tokens/);
  return answer;
}

function asked(requests: { route: string; body?: unknown }[]) {
  return requests.filter((request) => request.route === "ask").map((request) => request.body);
}

test("the picker offers the Instructions Draft, the default, and every Version newest first", async () => {
  setUp();
  renderStudio(agentPage);

  const select = await picker();
  await within(select).findByRole("option", { name: "v3 · Shorter" });

  expect(within(select).getAllByRole("option").map((option) => option.textContent)).toEqual([
    "Instructions Draft",
    "v3 · Shorter",
    "v2 (Current) · Salaries",
    "v1 · First rules",
  ]);
  expect(select).toHaveDisplayValue("Instructions Draft");
  expect(screen.getByText(/Answers follow the Instructions Draft unless you choose a Version/)).toBeInTheDocument();
});

test("a question is asked with the chosen Instructions, and each answer says which it ran with", async () => {
  const { requests } = setUp();
  renderStudio(agentPage);
  const select = await picker();
  await within(select).findByRole("option", { name: "v1 · First rules" });

  const draftAnswer = await ask("How much leave?");
  await userEvent.selectOptions(select, "v1 · First rules");
  const v1Answer = await ask("And now?");
  await userEvent.selectOptions(select, "v2 (Current) · Salaries");
  const v2Answer = await ask("And with the Current Version?");
  await userEvent.selectOptions(select, "Instructions Draft");
  const backToDraft = await ask("And with the Draft again?");

  expect(asked(requests)).toEqual([
    { content: "How much leave?", instructions_version_id: null, conversationId: CONVERSATION_ID },
    { content: "And now?", instructions_version_id: v1.id, conversationId: CONVERSATION_ID },
    { content: "And with the Current Version?", instructions_version_id: v2.id, conversationId: CONVERSATION_ID },
    { content: "And with the Draft again?", instructions_version_id: null, conversationId: CONVERSATION_ID },
  ]);
  // The label comes from what the API says the answer ran with.
  expect(within(draftAnswer).getByText("Instructions: Draft")).toBeInTheDocument();
  expect(within(v1Answer).getByText("Instructions: v1")).toBeInTheDocument();
  expect(within(v2Answer).getByText("Instructions: v2")).toBeInTheDocument();
  expect(within(backToDraft).getByText("Instructions: Draft")).toBeInTheDocument();
  // The choice stays for the next question.
  expect(select).toHaveDisplayValue("Instructions Draft");
});

test("with no Versions published the picker offers only the Instructions Draft", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  const { requests } = fakeAgentsApi({ agents: [hrHelper] });
  renderStudio(agentPage);

  const select = await picker();
  expect(await screen.findByText(/No Instructions Versions are published yet/)).toBeInTheDocument();
  expect(within(select).getAllByRole("option").map((option) => option.textContent)).toEqual(["Instructions Draft"]);
  const answer = await ask("How much leave?");
  expect(within(answer).getByText("Instructions: Draft")).toBeInTheDocument();
  expect(asked(requests)).toEqual([{ content: "How much leave?", instructions_version_id: null, conversationId: CONVERSATION_ID }]);
});

test("when the Versions can't be loaded the Playground still answers with the Instructions Draft", async () => {
  setUp();
  server.use(
    http.get("*/api/organisations/:organisationId/projects/:projectId/instructions/versions", () =>
      HttpResponse.json({ detail: "Boom" }, { status: 500 }),
    ),
  );
  renderStudio(agentPage);

  expect(await screen.findByText(/The Instructions Versions could not be loaded, so answers follow the Instructions Draft/, {}, { timeout: 5000 })).toBeInTheDocument();
  const select = await picker();
  expect(within(select).getAllByRole("option").map((option) => option.textContent)).toEqual(["Instructions Draft"]);
  const answer = await ask("How much leave?");
  expect(within(answer).getByText("Instructions: Draft")).toBeInTheDocument();
});

test("a Version the API refuses is explained and the question isn't answered", async () => {
  setUp({
    answer: () =>
      HttpResponse.json({ detail: "That Instructions Version isn't one of this Project's." }, { status: 422 }),
  });
  renderStudio(agentPage);
  const select = await picker();
  await userEvent.selectOptions(select, await within(select).findByRole("option", { name: "v3 · Shorter" }));

  await userEvent.type(screen.getByLabelText("Question"), "How much leave?");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));

  expect(await screen.findByText("That Instructions Version isn't one of this Project's.")).toBeInTheDocument();
  expect(
    within(screen.getByRole("list", { name: "Playground messages" })).queryByRole("listitem", { name: "HR helper" }),
  ).not.toBeInTheDocument();
});

test("the Trace names the Instructions the answer ran with", async () => {
  setUp({
    trace: () =>
      HttpResponse.json({
        ...hrTrace,
        instructions_source: "version",
        instructions_version_id: v1.id,
        instructions_version_number: 1,
      }),
  });
  renderStudio(agentPage);
  const select = await picker();
  await userEvent.selectOptions(select, await within(select).findByRole("option", { name: "v1 · First rules" }));
  const answer = await ask("How much leave?");

  await userEvent.click(within(answer).getByRole("button", { name: "Trace" }));

  const drawer = await screen.findByRole("dialog", { name: "Trace" });
  const instructions = await within(drawer).findByText("Instructions");
  expect(instructions.nextElementSibling).toHaveTextContent("v1");
});

test("the Trace of an answer run with the Instructions Draft says so", async () => {
  setUp();
  renderStudio(agentPage);
  await picker();
  const answer = await ask("How much leave?");

  await userEvent.click(within(answer).getByRole("button", { name: "Trace" }));

  const drawer = await screen.findByRole("dialog", { name: "Trace" });
  const instructions = await within(drawer).findByText("Instructions");
  expect(instructions.nextElementSibling).toHaveTextContent("Draft");
});
