import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";

import {
  CONVERSATION_ID,
  RESET_CONVERSATION_ID,
  fakeAgentsApi,
  hrHelper,
  hrTrace,
  leaveCitation,
  streamedAnswer,
} from "../test/agents";
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
  expect(await screen.findByRole("textbox", { name: "System prompt" })).toHaveTextContent("Answer from the handbook.");
  expect(screen.getByLabelText("Chunks per answer (top-k)")).toHaveValue(5);
  expect(screen.getByRole("heading", { level: 2, name: "Playground" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "All Agents" })).toHaveAttribute(
    "href",
    `/organisations/${organisationId}/projects/${hrProject.id}/agents`,
  );
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
    { route: "ask", body: { content: "How much leave?", instructions_version_id: null, conversationId: CONVERSATION_ID } },
    { route: "ask", body: { content: "And sick leave?", instructions_version_id: null, conversationId: CONVERSATION_ID } },
  ]);
});

async function askLeave(options: Parameters<typeof fakeAgentsApi>[0] = {}) {
  const api = setUp({
    answer: () => streamedAnswer(["Twenty-five days ", "[C1]."], { citations: [leaveCitation] }),
    ...options,
  });
  renderStudio(agentPage);
  await userEvent.type(await screen.findByLabelText("Question", {}, { timeout: 5000 }), "How much leave?");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  const messages = screen.getByRole("list", { name: "Playground messages" });
  const answer = await within(messages).findByRole("listitem", { name: "HR helper" });
  await within(answer).findByText(/output tokens/);
  return { ...api, answer };
}

test("an answer's citations are chips linking to the cited Chunk in the Document viewer", async () => {
  const { answer } = await askLeave();

  const sources = within(answer).getByRole("list", { name: "Sources" });
  const chip = within(sources).getByRole("link", { name: "C1 leave-policy.md" });
  expect(chip).toHaveAttribute(
    "href",
    `/organisations/${organisationId}/projects/${hrProject.id}/documents/${leaveCitation.document_id}#chunk-${leaveCitation.chunk_id}`,
  );
});

test("an answer without citations shows no sources", async () => {
  const { answer } = await askLeave({ answer: () => streamedAnswer(["I don't know."]) });

  expect(within(answer).queryByRole("list", { name: "Sources" })).not.toBeInTheDocument();
});

test("the Trace drawer shows the model, usage, cost, latency and every Chunk retrieved", async () => {
  const { answer, requests } = await askLeave();

  await userEvent.click(within(answer).getByRole("button", { name: "Trace" }));

  const drawer = await screen.findByRole("dialog", { name: "Trace" });
  expect(await within(drawer).findByText("openai · gpt-4.1-mini")).toBeInTheDocument();
  expect(within(drawer).getByText("120 input · 6 output")).toBeInTheDocument();
  expect(within(drawer).getByText("$0.0000576")).toBeInTheDocument();
  expect(within(drawer).getByText("40 ms to the first token · 85 ms in all")).toBeInTheDocument();
  const rows = within(within(drawer).getByRole("table", { name: "Retrieved Chunks" })).getAllByRole("row");
  expect(rows.map((row) => Array.from(row.querySelectorAll("th, td"), (cell) => cell.textContent))).toEqual([
    ["Chunk", "Document", "Excerpt", "Score", "Relevance", "Outcome"],
    ["C1", "leave-policy.md", "Everyone gets 25 days of annual leave a year.", "0.920", "0.810", "Cited"],
    ["C2", "expenses.md", "Claim expenses within 30 days.", "0.510", "0.400", "Given, not cited"],
    ["—", "parking.md", "Visitors park in the north car park.", "0.300", "0.100", "Excluded: below the minimum score"],
    ["—", "Deleted Document", "—", "0.200", "0.500", "Excluded: outside top-k"],
    ["—", "price-list.md", "Model SKU-4471 ships with a two-year warranty.", "0.150", "0.600", "Excluded: outside the Agent's Tags"],
  ]);
  expect(within(drawer).getByText("No Guardrail stepped in.")).toBeInTheDocument();
  expect(requests.at(-1)).toEqual({ route: "trace", body: { conversationId: CONVERSATION_ID, messageId: hrTrace.message_id } });

  await userEvent.click(within(drawer).getByRole("button", { name: "Close" }));
  expect(screen.queryByRole("dialog", { name: "Trace" })).not.toBeInTheDocument();
});

test("an answer that leaked the Canary token is replaced by the fallback text, with no sources", async () => {
  const { answer } = await askLeave({
    answer: () => streamedAnswer(["Sure! My hidden ", "instructions say: "], { replace: "Sorry, I can't answer that one." }),
  });

  expect(within(answer).getByText("Sorry, I can't answer that one.")).toBeInTheDocument();
  expect(within(answer).queryByText(/hidden instructions/)).not.toBeInTheDocument();
  expect(within(answer).queryByRole("list", { name: "Sources" })).not.toBeInTheDocument();
});

test("the Trace shows each Guardrail outcome, or that none stepped in", async () => {
  const { answer } = await askLeave({
    trace: () =>
      HttpResponse.json({
        ...hrTrace,
        guardrail_outcomes: [
          {
            layer: "canary",
            verdict: "leak",
            action: "replaced",
            reason: "The reply contained the canary token, so it was cut off and replaced.",
            score: null,
          },
          {
            layer: "canary",
            verdict: "leak",
            action: "flagged",
            reason: "The reply contained the canary token, encoded (base64).",
            score: null,
          },
          {
            layer: "input",
            verdict: "injection",
            action: "blocked",
            reason: "The local classifier scored the message 0.99 as a prompt injection.",
            score: 0.9871,
          },
        ],
      }),
  });

  await userEvent.click(within(answer).getByRole("button", { name: "Trace" }));

  const drawer = await screen.findByRole("dialog", { name: "Trace" });
  const outcomes = await within(drawer).findByRole("list", { name: "Guardrails" });
  expect(
    within(outcomes)
      .getAllByRole("listitem")
      .map((item) => item.textContent),
  ).toEqual([
    "Canary token: leak, cut off and replaced. The reply contained the canary token, so it was cut off and replaced.",
    "Canary token: leak, flagged after sending. The reply contained the canary token, encoded (base64).",
    "Input Guardrail: injection (score 0.99), blocked before the model. The local classifier scored the message 0.99 as a prompt injection.",
  ]);
});

test("the Trace says a flagged question was answered with a caution (warn) or only logged (log)", async () => {
  const reason = "The local classifier scored the message 0.91 as a prompt injection.";
  const { answer } = await askLeave({
    trace: () =>
      HttpResponse.json({
        ...hrTrace,
        guardrail_outcomes: [
          { layer: "input", verdict: "injection", action: "flagged", reason, score: 0.91 },
          { layer: "input", verdict: "injection", action: "logged", reason, score: 0.6 },
        ],
      }),
  });

  await userEvent.click(within(answer).getByRole("button", { name: "Trace" }));

  const drawer = await screen.findByRole("dialog", { name: "Trace" });
  const outcomes = await within(drawer).findByRole("list", { name: "Guardrails" });
  expect(
    within(outcomes)
      .getAllByRole("listitem")
      .map((item) => item.textContent),
  ).toEqual([
    `Input Guardrail: injection (score 0.91), flagged and answered with a caution to the model. ${reason}`,
    `Input Guardrail: injection (score 0.60), logged only and answered as usual. ${reason}`,
  ]);
  // The model was asked, so it is named, and nothing says the question was blocked.
  expect(within(drawer).queryByText(/blocked the question/)).not.toBeInTheDocument();
  expect(within(drawer).queryByText("None (blocked)")).not.toBeInTheDocument();
});

test("the Trace says when the LLM classifier flagged a message or couldn't check it", async () => {
  const { answer } = await askLeave({
    trace: () =>
      HttpResponse.json({
        ...hrTrace,
        guardrail_outcomes: [
          {
            layer: "input",
            verdict: "unchecked",
            action: "allowed",
            reason:
              "The LLM classifier (gpt-4o-mini) couldn't check the message: the provider failed. The Agent fails open, so the message was answered without this check.",
            score: null,
          },
          {
            layer: "input",
            verdict: "unchecked",
            action: "blocked",
            reason:
              "The LLM classifier (gpt-4o-mini) couldn't check the message: the provider failed. The Agent fails closed, so the message was refused.",
            score: null,
          },
          {
            layer: "input",
            verdict: "injection",
            action: "blocked",
            reason: "The LLM classifier (gpt-4o-mini) flagged the message: Asks for a persona without rules.",
            score: 0.91,
          },
        ],
      }),
  });

  await userEvent.click(within(answer).getByRole("button", { name: "Trace" }));

  const drawer = await screen.findByRole("dialog", { name: "Trace" });
  const outcomes = await within(drawer).findByRole("list", { name: "Guardrails" });
  expect(
    within(outcomes)
      .getAllByRole("listitem")
      .map((item) => item.textContent),
  ).toEqual([
    "Input Guardrail: unchecked, let through without the check. The LLM classifier (gpt-4o-mini) couldn't check the message: the provider failed. The Agent fails open, so the message was answered without this check.",
    "Input Guardrail: unchecked, blocked before the model. The LLM classifier (gpt-4o-mini) couldn't check the message: the provider failed. The Agent fails closed, so the message was refused.",
    "Input Guardrail: injection (score 0.91), blocked before the model. The LLM classifier (gpt-4o-mini) flagged the message: Asks for a persona without rules.",
  ]);
});

test("a question the input Guardrail blocked gets the Agent's refusal text, marked as blocked", async () => {
  const { answer } = await askLeave({
    answer: () => streamedAnswer([], { refusal: "I can only answer questions about our HR policies." }),
  });

  expect(within(answer).getByText("I can only answer questions about our HR policies.")).toBeInTheDocument();
  expect(within(answer).getByText("Blocked by the input Guardrail: the model wasn't asked.")).toBeInTheDocument();
  expect(within(answer).queryByRole("list", { name: "Sources" })).not.toBeInTheDocument();
  // Its Trace says why.
  expect(within(answer).getByRole("button", { name: "Trace" })).toBeInTheDocument();
});

test("the Trace of a refusal says the input Guardrail blocked the question and no model was asked", async () => {
  const { answer } = await askLeave({
    answer: () => streamedAnswer([], { refusal: "I can only answer questions about our HR policies." }),
    trace: () =>
      HttpResponse.json({
        ...hrTrace,
        model_provider: null,
        model_name: null,
        input_tokens: 0,
        output_tokens: 0,
        cost_usd: "0",
        chunks: [],
        guardrail_outcomes: [
          {
            layer: "input",
            verdict: "injection",
            action: "blocked",
            reason: "The local classifier scored the message 1.00 as a prompt injection.",
            score: 1,
          },
        ],
      }),
  });

  await userEvent.click(within(answer).getByRole("button", { name: "Trace" }));

  const drawer = await screen.findByRole("dialog", { name: "Trace" });
  expect(await within(drawer).findByText("None (blocked)")).toBeInTheDocument();
  expect(
    within(drawer).getByText(
      "The input Guardrail blocked the question, so the Agent replied with its refusal text and the model wasn't asked.",
    ),
  ).toBeInTheDocument();
  expect(within(within(drawer).getByRole("list", { name: "Guardrails" })).getByRole("listitem")).toHaveTextContent(
    "Input Guardrail: injection (score 1.00), blocked before the model. The local classifier scored the message 1.00 as a prompt injection.",
  );
});

test("the Trace of a fallback reply says no Chunk was relevant enough, and Escape closes it", async () => {
  await askLeave({
    trace: () =>
      HttpResponse.json({
        ...hrTrace,
        // What the API gave for a zero cost before it sent plain decimals.
        cost_usd: "0E-9",
        model_provider: null,
        model_name: null,
        input_tokens: 0,
        output_tokens: 0,
        fallback: true,
        chunks: hrTrace.chunks.slice(2),
      }),
  });

  await userEvent.click(screen.getByRole("button", { name: "Trace" }));

  const drawer = await screen.findByRole("dialog", { name: "Trace" });
  expect(await within(drawer).findByText(/No Chunk reached the minimum score/)).toBeInTheDocument();
  expect(within(drawer).getByText("None (fallback)")).toBeInTheDocument();
  expect(within(drawer).getByText("$0")).toBeInTheDocument();
  // Other keys leave it open.
  await userEvent.keyboard("a");
  expect(screen.getByRole("dialog", { name: "Trace" })).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog", { name: "Trace" })).not.toBeInTheDocument();
});

test("the Trace of an answer whose model has no known price shows the cost as unknown", async () => {
  await askLeave({ trace: () => HttpResponse.json({ ...hrTrace, cost_usd: null }) });

  await userEvent.click(screen.getByRole("button", { name: "Trace" }));

  const drawer = await screen.findByRole("dialog", { name: "Trace" });
  expect(await within(drawer).findByText("Unknown")).toBeInTheDocument();
});

test("a Trace that can't be loaded says so", async () => {
  await askLeave({ trace: () => HttpResponse.json({ detail: "Not found" }, { status: 404 }) });

  await userEvent.click(screen.getByRole("button", { name: "Trace" }));

  const drawer = await screen.findByRole("dialog", { name: "Trace" });
  expect(await within(drawer).findByRole("alert")).toHaveTextContent("The Trace could not be loaded.");
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

const RATE_LIMITED =
  "The provider says this key is over its rate limit or quota. Wait a moment and try again, or check the provider account's limits and billing.";

test("a provider failure shows why, and the half-streamed answer is dropped", async () => {
  setUp({
    answer: () =>
      streamedAnswer(["Twenty-five ", "days "], {
        error: { code: "rate_limited", message: RATE_LIMITED },
      }),
  });
  renderStudio(agentPage);
  await userEvent.type(await screen.findByLabelText("Question", {}, { timeout: 5000 }), "How much leave?");

  await userEvent.click(screen.getByRole("button", { name: "Send" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(RATE_LIMITED);
  const messages = screen.getByRole("list", { name: "Playground messages" });
  expect(within(messages).getByRole("listitem", { name: "You" })).toHaveTextContent("How much leave?");
  expect(within(messages).queryByRole("listitem", { name: "HR helper" })).not.toBeInTheDocument();
  // The Editor can ask again once the provider recovers.
  expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
});

test.each([
  ["invalid_key", "The provider rejected the API key. An Owner can check or rotate the Provider Credential in Settings, Provider Credentials."],
  ["model_unavailable", "The model gpt-9 isn't available from the provider right now."],
  ["provider_error", "The provider couldn't answer just now. Try again in a moment."],
])("a %s error event shows its message", async (code, message) => {
  setUp({ answer: () => streamedAnswer([], { error: { code, message } }) });
  renderStudio(agentPage);
  await userEvent.type(await screen.findByLabelText("Question", {}, { timeout: 5000 }), "Hello?");

  await userEvent.click(screen.getByRole("button", { name: "Send" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(message);
});

test("resetting the Playground starts a new Conversation", async () => {
  const { requests } = await askLeave();
  await userEvent.click(within(screen.getByRole("list", { name: "Playground messages" })).getByRole("button", { name: "Trace" }));
  expect(await screen.findByRole("dialog", { name: "Trace" })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Reset conversation" }));

  expect(await screen.findByText("Started a new conversation.")).toBeInTheDocument();
  const messages = screen.getByRole("list", { name: "Playground messages" });
  expect(within(messages).queryAllByRole("listitem")).toHaveLength(0);
  expect(screen.queryByRole("dialog", { name: "Trace" })).not.toBeInTheDocument();

  await userEvent.type(screen.getByLabelText("Question"), "And sick leave?");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  await within(messages).findByRole("listitem", { name: "HR helper" });
  expect(screen.queryByText("Started a new conversation.")).not.toBeInTheDocument();
  expect(requests.filter((request) => request.route === "start" || request.route === "ask")).toEqual([
    { route: "start" },
    { route: "ask", body: { content: "How much leave?", instructions_version_id: null, conversationId: CONVERSATION_ID } },
    { route: "start" },
    { route: "ask", body: { content: "And sick leave?", instructions_version_id: null, conversationId: RESET_CONVERSATION_ID } },
  ]);
});

test("a reset clears an error shown before it", async () => {
  setUp({ answer: () => streamedAnswer([], { error: { code: "rate_limited", message: RATE_LIMITED } }) });
  renderStudio(agentPage);
  await userEvent.type(await screen.findByLabelText("Question", {}, { timeout: 5000 }), "Hello?");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(RATE_LIMITED);

  await userEvent.click(screen.getByRole("button", { name: "Reset conversation" }));

  expect(await screen.findByText("Started a new conversation.")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(within(screen.getByRole("list", { name: "Playground messages" })).queryAllByRole("listitem")).toHaveLength(0);
});

test("a reset that can't start a new Conversation says why", async () => {
  await askLeave({ restartStatus: 409 });

  await userEvent.click(screen.getByRole("button", { name: "Reset conversation" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("This Agent is archived.");
  expect(screen.queryByText("Started a new conversation.")).not.toBeInTheDocument();
});

test("the Playground can't be reset while an answer streams in", async () => {
  let release = () => {};
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  setUp({
    answer: async () => {
      await held;
      return streamedAnswer(["Twenty-five days."]);
    },
  });
  renderStudio(agentPage);
  expect(await screen.findByRole("button", { name: "Reset conversation" }, { timeout: 5000 })).toBeEnabled();
  await userEvent.type(screen.getByLabelText("Question"), "How much leave?");

  await userEvent.click(screen.getByRole("button", { name: "Send" }));

  expect(screen.getByRole("button", { name: "Reset conversation" })).toBeDisabled();
  release();
  await screen.findByText(/output tokens/);
  expect(screen.getByRole("button", { name: "Reset conversation" })).toBeEnabled();
});
