import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";

import { CONVERSATION_ID, fakeAgentsApi, hrHelper, streamedAnswer } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";

const organisationId = adaSession.organisations[0]?.id ?? "";
const agentPage = `/organisations/${organisationId}/projects/${hrProject.id}/agents/${hrHelper.id}`;

function setUp(options: Parameters<typeof fakeAgentsApi>[0] = {}) {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  return fakeAgentsApi({ agents: [hrHelper], ...options });
}

test("the Agent page shows the Draft beside the Playground", async () => {
  setUp();
  renderStudio(agentPage);

  expect(await screen.findByRole("heading", { level: 2, name: "HR helper" }, { timeout: 5000 })).toBeInTheDocument();
  expect(screen.getByLabelText("System prompt")).toHaveValue("Answer from the handbook.");
  expect(screen.getByLabelText("Chunks per answer (top-k)")).toHaveValue(5);
  expect(screen.getByRole("heading", { level: 2, name: "Playground" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "All Agents" })).toHaveAttribute(
    "href",
    `/organisations/${organisationId}/projects/${hrProject.id}/agents`,
  );
});

test("an Editor edits the system prompt and top-k and saves the Draft, keeping its other settings", async () => {
  const { requests } = setUp();
  renderStudio(agentPage);
  const prompt = await screen.findByLabelText("System prompt", {}, { timeout: 5000 });

  await userEvent.clear(prompt);
  await userEvent.type(prompt, "# Role{enter}{enter}Be brief.");
  await userEvent.clear(screen.getByLabelText("Chunks per answer (top-k)"));
  await userEvent.type(screen.getByLabelText("Chunks per answer (top-k)"), "3");
  await userEvent.click(screen.getByRole("button", { name: "Save Draft" }));

  expect(await screen.findByText("Draft saved")).toBeInTheDocument();
  expect(requests).toEqual([
    {
      route: "draft",
      body: {
        behaviour: { system_prompt: "# Role\n\nBe brief.", fallback_text: "Ask HR, please." },
        retrieval: { top_k: 3, hybrid_weight: 0.7, min_score: 0.25 },
      },
    },
  ]);
});

test("a Draft the API refuses shows why", async () => {
  setUp();
  renderStudio(agentPage);
  const topK = await screen.findByLabelText("Chunks per answer (top-k)", {}, { timeout: 5000 });
  topK.removeAttribute("max");

  await userEvent.clear(topK);
  await userEvent.type(topK, "50");
  await userEvent.click(screen.getByRole("button", { name: "Save Draft" }));

  const draft = screen.getByRole("form", { name: "Draft" });
  expect(await within(draft).findByRole("alert")).toHaveTextContent(/top-k from 1 to 20/);
});

test("a question is answered in the Playground as the answer streams in", async () => {
  const { requests } = setUp({ answer: () => streamedAnswer(["Twenty-five ", "days ", "a year."]) });
  renderStudio(agentPage);
  await userEvent.type(await screen.findByLabelText("Question", {}, { timeout: 5000 }), "How much leave?");

  await userEvent.click(screen.getByRole("button", { name: "Send" }));

  const messages = screen.getByRole("list", { name: "Playground messages" });
  expect(within(messages).getByRole("listitem", { name: "You" })).toHaveTextContent("How much leave?");
  const answer = await within(messages).findByRole("listitem", { name: "HR helper" });
  expect(await within(answer).findByText("Twenty-five days a year.")).toBeInTheDocument();
  expect(await within(answer).findByText("120 input and 6 output tokens · 85 ms")).toBeInTheDocument();
  expect(screen.getByLabelText("Question")).toHaveValue("");

  // The next question continues the same Conversation.
  await userEvent.type(screen.getByLabelText("Question"), "And sick leave?");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(await within(messages).findAllByRole("listitem", { name: "HR helper" })).toHaveLength(2);
  expect(requests.filter((request) => request.route !== "draft")).toEqual([
    { route: "start" },
    { route: "ask", body: { content: "How much leave?", conversationId: CONVERSATION_ID } },
    { route: "ask", body: { content: "And sick leave?", conversationId: CONVERSATION_ID } },
  ]);
});

test("a blank question isn't sent", async () => {
  const { requests } = setUp();
  renderStudio(agentPage);
  await userEvent.type(await screen.findByLabelText("Question", {}, { timeout: 5000 }), "   ");

  await userEvent.click(screen.getByRole("button", { name: "Send" }));

  expect(requests).toEqual([]);
});

test("a refused question shows the API's reason", async () => {
  const detail = "This Organisation has no Default Model. An Owner can choose one in Settings, Models.";
  setUp({ answer: () => HttpResponse.json({ detail }, { status: 409 }) });
  renderStudio(agentPage);
  await userEvent.type(await screen.findByLabelText("Question", {}, { timeout: 5000 }), "Hello?");

  await userEvent.click(screen.getByRole("button", { name: "Send" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(detail);
  const messages = screen.getByRole("list", { name: "Playground messages" });
  expect(within(messages).queryByRole("listitem", { name: "HR helper" })).not.toBeInTheDocument();
});

test("a Playground that can't start says so", async () => {
  setUp({ startStatus: 409 });
  renderStudio(agentPage);
  await userEvent.type(await screen.findByLabelText("Question", {}, { timeout: 5000 }), "Hello?");

  await userEvent.click(screen.getByRole("button", { name: "Send" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("This Project is archived. An Owner can restore it.");
});

test("an answer cut off before it ends shows an error", async () => {
  setUp({ answer: () => streamedAnswer(["Twenty-five "], { end: false }) });
  renderStudio(agentPage);
  await userEvent.type(await screen.findByLabelText("Question", {}, { timeout: 5000 }), "How much leave?");

  await userEvent.click(screen.getByRole("button", { name: "Send" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("an Agent that doesn't exist says so", async () => {
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi();
  renderStudio(agentPage);

  expect(await screen.findByText("The Agent could not be found.", {}, { timeout: 5000 })).toBeInTheDocument();
});
