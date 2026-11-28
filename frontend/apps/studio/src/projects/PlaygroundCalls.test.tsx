/**
 * Network seam: an Editor calls the Draft from the Playground (spec 20, ticket 20-13). The
 * Playground offers a Call only while the Agent's calling is on, and says how to turn it on when
 * it is off. With the fake voice layer the Call is played without audio: the Editor "says" the
 * question box's text, the fake voice layer holds the turn, and the Playground reads the saved
 * Conversation back, showing each spoken reply with its Searches, sources and Trace.
 */
import type { Schemas } from "@studio/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { CONVERSATION_ID, RESET_CONVERSATION_ID, fakeAgentsApi, hrHelper, leaveCitation, streamedAnswer } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeProjectsApi, hrProject, instructionsVersion } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";
import { CALL_DROPPED, CALL_UNAVAILABLE } from "./AgentPage";

const organisationId = adaSession.organisations[0]?.id ?? "";
const agentPage = `/organisations/${organisationId}/projects/${hrProject.id}/agents/${hrHelper.id}`;
const CONVERSATIONS = "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/playground/conversations/:conversationId";

type Message = Schemas["PlaygroundMessageOut"];

const startedCall: Schemas["StartedCallOut"] = {
  call_id: "a0000000-0000-4000-8000-000000000001",
  call_token: "wp1.call.sig",
  join: { voice_layer: "fake", conversation_token: "fake-call-1", greet: true },
  max_call_minutes: 10,
};

function message(fields: Partial<Message> & Pick<Message, "id" | "role" | "content">): Message {
  return {
    created_at: "2026-11-05T09:00:00Z",
    config_source: null,
    instructions_source: null,
    instructions_version_id: null,
    instructions_version_number: null,
    agent_version_id: null,
    model_provider: null,
    model_name: null,
    input_tokens: null,
    output_tokens: null,
    first_token_ms: null,
    latency_ms: null,
    cost_usd: null,
    spoken: true,
    searches: [],
    citations: [],
    ...fields,
  };
}

/** The words and the spoken reply of one turn, as the API reads them back. */
function spokenTurn(words: string, reply: string, fields: Partial<Message> = {}): Message[] {
  return [
    message({ id: `q-${words}`, role: "user", content: words }),
    message({
      id: `r-${words}`,
      role: "assistant",
      content: reply,
      config_source: "draft",
      instructions_source: "draft",
      input_tokens: 90,
      output_tokens: 7,
      first_token_ms: 30,
      latency_ms: 70,
      ...fields,
    }),
  ];
}

type Options = {
  calling?: boolean;
  started?: Schemas["StartedCallOut"];
  /** Refuses the start with this status and detail. */
  refuse?: [number, string];
  /** What each read of the Conversation holds: its Messages and whether a Call is open. */
  saved?: () => { messages: Message[]; call_open: boolean } | Response;
  /** Decides each fake voice layer turn; by default the turn is held and answered. */
  turn?: () => Response | Promise<Response>;
  /** Decides each end of a Call; by default it ends. */
  end?: () => Response;
  /** The Project's Instructions Versions, the first Current. */
  versions?: ReturnType<typeof instructionsVersion>[];
};

function setUp(options: Options = {}) {
  fakeAuthApi({ signedInAs: adaSession });
  const versions = options.versions ?? [];
  fakeProjectsApi(versions.length > 0 ? { versions: { [hrProject.id]: { current_version_id: (versions[0] as { id: string }).id, versions } } } : {});
  const api = fakeAgentsApi({
    agents: [hrHelper],
    answer: () => streamedAnswer(["Twenty-five days."]),
    callSettings: { calls_enabled: options.calling ?? true },
  });
  const calls: { route: string; body?: unknown; conversationId?: unknown }[] = [];
  server.use(
    http.post(`${CONVERSATIONS}/calls`, async ({ request, params }) => {
      calls.push({ route: "start", body: await request.json(), conversationId: params.conversationId });
      if (options.refuse) return HttpResponse.json({ detail: options.refuse[1] }, { status: options.refuse[0] });
      return HttpResponse.json(options.started ?? startedCall, { status: 201 });
    }),
    http.delete(`${CONVERSATIONS}/calls/current`, ({ params }) => {
      calls.push({ route: "end", conversationId: params.conversationId });
      return options.end ? options.end() : new HttpResponse(null, { status: 204 });
    }),
    http.get(CONVERSATIONS, ({ params }) => {
      calls.push({ route: "read", conversationId: params.conversationId });
      const saved = options.saved?.() ?? { messages: spokenTurn("How much leave?", "Twenty-five days."), call_open: true };
      if (saved instanceof Response) return saved;
      return HttpResponse.json({
        id: params.conversationId as string,
        agent_id: hrHelper.id,
        is_playground: true,
        created_at: "2026-11-05T09:00:00Z",
        last_activity_at: "2026-11-05T09:00:00Z",
        ...saved,
      });
    }),
    http.post("*/api/widget/fake-voice/calls/:joinToken/turns", async ({ request, params }) => {
      calls.push({ route: "turn", body: await request.json(), conversationId: params.joinToken });
      return options.turn ? options.turn() : HttpResponse.json({ agent_response: "Twenty-five days." });
    }),
  );
  return { ...api, calls };
}

async function callButton() {
  return screen.findByRole("button", { name: "Call the Draft" }, { timeout: 5000 });
}

async function callPanel() {
  return screen.findByRole("group", { name: "Call" });
}

test("with calling off, the Playground offers no Call and says where to turn it on", async () => {
  setUp({ calling: false });
  renderStudio(agentPage);

  const off = await screen.findByText(/Calling is off for this Agent/, {}, { timeout: 5000 });

  expect(off).toHaveTextContent("Calling is off for this Agent. Turn it on in Embed & limits to call the Draft.");
  expect(within(off).getByRole("link", { name: "Embed & limits" })).toHaveAttribute("href", `${agentPage}/embed`);
  expect(screen.queryByRole("button", { name: "Call the Draft" })).not.toBeInTheDocument();
});

test("an Editor calls the Draft and each spoken reply shows with its Searches, sources and Trace", async () => {
  const { calls } = setUp({
    saved: () => ({
      messages: spokenTurn("How much leave?", "You get 25 days [C1].", {
        searches: ["leave", "annual leave"],
        citations: [leaveCitation],
      }),
      call_open: true,
    }),
  });
  renderStudio(agentPage);
  await userEvent.type(await screen.findByLabelText("Question", {}, { timeout: 5000 }), "How much leave?");

  await userEvent.click(await callButton());

  const panel = await callPanel();
  expect(screen.queryByRole("form", { name: "Ask the Draft" })).not.toBeInTheDocument();
  const messages = screen.getByRole("list", { name: "Playground messages" });
  const answer = await within(messages).findByRole("listitem", { name: "HR helper" });
  expect(answer).toHaveTextContent("You get 25 days [C1].");
  expect(within(answer).getByRole("list", { name: "Searches" })).toHaveTextContent("Searching: leaveSearching: annual leave");
  expect(within(answer).getByRole("link", { name: /C1/ })).toHaveAttribute(
    "href",
    `/organisations/${organisationId}/projects/${hrProject.id}/documents/${leaveCitation.document_id}#chunk-${leaveCitation.chunk_id}`,
  );
  expect(within(answer).getByText("Spoken")).toBeInTheDocument();
  expect(within(answer).getByText("Instructions: Draft")).toBeInTheDocument();
  expect(within(answer).getByText("90 input and 7 output tokens · 70 ms")).toBeInTheDocument();
  expect(within(messages).getByRole("listitem", { name: "You" })).toHaveTextContent("How much leave?Spoken");
  expect(within(panel).getByRole("status")).toHaveTextContent(/Listening…|The Draft is speaking…/);
  expect(calls.slice(0, 2)).toEqual([
    { route: "start", body: { instructions_version_id: null }, conversationId: CONVERSATION_ID },
    { route: "turn", body: { words: "How much leave?", call_token: "wp1.call.sig" }, conversationId: "fake-call-1" },
  ]);

  await userEvent.click(within(panel).getByRole("button", { name: "End call" }));

  expect(await screen.findByRole("form", { name: "Ask the Draft" })).toBeInTheDocument();
  expect(calls.filter((call) => call.route === "end")).toEqual([{ route: "end", conversationId: CONVERSATION_ID }]);
  expect(screen.queryByRole("group", { name: "Call" })).not.toBeInTheDocument();
});

test("a Call says Hello when the question box is empty, in the Conversation already open, and shows connecting first", async () => {
  let release: () => void = () => undefined;
  const { calls } = setUp({
    saved: () => ({ messages: spokenTurn("Hello.", "Hi! How can I help?"), call_open: true }),
  });
  server.use(
    http.post(`${CONVERSATIONS}/calls`, async () => {
      await new Promise<void>((resolve) => (release = resolve));
      return HttpResponse.json(startedCall, { status: 201 });
    }),
  );
  renderStudio(agentPage);
  await userEvent.type(await screen.findByLabelText("Question", {}, { timeout: 5000 }), "How much leave?");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText("Twenty-five days.");

  await userEvent.click(await callButton());

  const panel = await callPanel();
  expect(within(panel).getByRole("status")).toHaveTextContent("Connecting the call…");
  expect(within(panel).getByRole("button", { name: "End call" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Reset conversation" })).toBeDisabled();
  release();
  expect(await screen.findByText("Hi! How can I help?")).toBeInTheDocument();
  expect(calls.find((call) => call.route === "turn")).toEqual({
    route: "turn",
    body: { words: "Hello.", call_token: "wp1.call.sig" },
    conversationId: "fake-call-1",
  });
});

test("the picked Instructions Version answers the Call", async () => {
  const v1 = instructionsVersion(1, { note: "First rules" });
  const { calls } = setUp({ versions: [v1] });
  renderStudio(agentPage);
  const picker = await screen.findByRole("combobox", { name: "Instructions" }, { timeout: 5000 });
  await within(picker).findByRole("option", { name: /^v1/ });
  await userEvent.selectOptions(picker, v1.id);

  await userEvent.click(await callButton());

  await waitFor(() => {
    expect(calls.find((call) => call.route === "start")).toEqual({
      route: "start",
      body: { instructions_version_id: v1.id },
      conversationId: CONVERSATION_ID,
    });
  });
});

test("muting stops the Editor being heard until they unmute", async () => {
  const { calls } = setUp();
  renderStudio(agentPage);
  await userEvent.click(await callButton());
  const panel = await callPanel();
  const mute = await within(panel).findByRole("button", { name: "Mute" });
  await waitFor(() => {
    expect(mute).toBeEnabled();
  });

  await userEvent.click(mute);

  expect(mute).toHaveAttribute("aria-pressed", "true");
  expect(within(panel).getByRole("status")).toHaveTextContent("Muted: the Draft can't hear you.");
  await new Promise((resolve) => setTimeout(resolve, 600));
  expect(calls.filter((call) => call.route === "turn")).toHaveLength(0);

  await userEvent.click(mute);

  expect(mute).toHaveAttribute("aria-pressed", "false");
  await waitFor(() => {
    expect(calls.filter((call) => call.route === "turn")).toHaveLength(1);
  });
});

test("ending a muted Call says nothing more", async () => {
  const { calls } = setUp();
  renderStudio(agentPage);
  await userEvent.click(await callButton());
  const panel = await callPanel();
  const mute = within(panel).getByRole("button", { name: "Mute" });
  await waitFor(() => {
    expect(mute).toBeEnabled();
  });
  await userEvent.click(mute);

  await userEvent.click(within(panel).getByRole("button", { name: "End call" }));

  await screen.findByRole("form", { name: "Ask the Draft" });
  await new Promise((resolve) => setTimeout(resolve, 600));
  expect(calls.filter((call) => call.route === "turn")).toHaveLength(0);
});

test("ending the Call while a turn is held, or while the Draft speaks, stops the script", async () => {
  let held: () => void = () => undefined;
  const { calls } = setUp({
    turn: async () => {
      await new Promise<void>((resolve) => (held = resolve));
      return HttpResponse.json({ agent_response: "Twenty-five days." });
    },
  });
  renderStudio(agentPage);
  await userEvent.click(await callButton());
  const panel = await callPanel();
  await waitFor(() => {
    expect(calls.filter((call) => call.route === "turn")).toHaveLength(1);
  });

  await userEvent.click(within(panel).getByRole("button", { name: "End call" }));
  held();

  await screen.findByRole("form", { name: "Ask the Draft" });
  await new Promise((resolve) => setTimeout(resolve, 100));
  expect(calls.filter((call) => call.route === "read")).toHaveLength(1);
});

test("ending the Call while the Draft speaks leaves it ended", async () => {
  setUp();
  renderStudio(agentPage);
  await userEvent.click(await callButton());
  const panel = await callPanel();
  await within(panel).findByText("The Draft is speaking…");

  await userEvent.click(within(panel).getByRole("button", { name: "End call" }));

  await screen.findByRole("form", { name: "Ask the Draft" });
  await new Promise((resolve) => setTimeout(resolve, 600));
  expect(screen.queryByRole("group", { name: "Call" })).not.toBeInTheDocument();
});

test("a refused start says why and keeps the question box", async () => {
  setUp({ refuse: [409, "This Playground Conversation already has a Call open. End it first."] });
  renderStudio(agentPage);

  await userEvent.click(await callButton());

  expect(await screen.findByRole("alert")).toHaveTextContent("This Playground Conversation already has a Call open. End it first.");
  expect(screen.getByRole("form", { name: "Ask the Draft" })).toBeInTheDocument();
});

test("a voice layer that can't start the Call says so", async () => {
  setUp({ refuse: [502, "ElevenLabs couldn't be reached with this credential."] });
  renderStudio(agentPage);

  await userEvent.click(await callButton());

  expect(await screen.findByRole("alert")).toHaveTextContent("ElevenLabs couldn't be reached with this credential.");
});

test("a Draft that couldn't answer ends the Call and says so", async () => {
  const { calls } = setUp({ saved: () => ({ messages: spokenTurn("Hello.", "This assistant is temporarily unavailable."), call_open: false }) });
  renderStudio(agentPage);

  await userEvent.click(await callButton());

  expect(await screen.findByText(CALL_UNAVAILABLE)).toBeInTheDocument();
  expect(await screen.findByRole("form", { name: "Ask the Draft" })).toBeInTheDocument();
  expect(calls.filter((call) => call.route === "end")).toHaveLength(1);
});

test("a dropped Call returns to the question box and says so", async () => {
  setUp({ turn: () => HttpResponse.json({ detail: "refused" }, { status: 502 }) });
  renderStudio(agentPage);

  await userEvent.click(await callButton());

  expect(await screen.findByText(CALL_DROPPED)).toBeInTheDocument();
  expect(screen.getByRole("form", { name: "Ask the Draft" })).toBeInTheDocument();
});

test("a reply that can't be read back, or a Call that can't be ended, is an error", async () => {
  setUp({
    saved: () => HttpResponse.json({ detail: "Not found" }, { status: 404 }),
    end: () => HttpResponse.json({ detail: "Not found" }, { status: 404 }),
  });
  renderStudio(agentPage);
  await userEvent.click(await callButton());
  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Try again.");

  await userEvent.click(within(await callPanel()).getByRole("button", { name: "End call" }));

  expect(await screen.findByRole("form", { name: "Ask the Draft" })).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong. Try again.");
});

test("Reset ends an open Call before starting a new Conversation", async () => {
  const { calls } = setUp();
  renderStudio(agentPage);
  await userEvent.click(await callButton());
  const panel = await callPanel();
  await within(panel).findByText(/Listening…|The Draft is speaking…/);

  await userEvent.click(screen.getByRole("button", { name: "Reset conversation" }));

  expect(await screen.findByText("Started a new conversation.")).toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "Call" })).not.toBeInTheDocument();
  expect(calls.filter((call) => call.route === "end")).toEqual([{ route: "end", conversationId: CONVERSATION_ID }]);
  expect(within(screen.getByRole("list", { name: "Playground messages" })).queryAllByRole("listitem")).toHaveLength(0);
  expect(RESET_CONVERSATION_ID).not.toBe(CONVERSATION_ID);
});

test("leaving the Playground during a Call ends it", async () => {
  const { calls } = setUp({ end: () => HttpResponse.json({ detail: "Not found" }, { status: 404 }) });
  renderStudio(agentPage);
  await userEvent.click(await callButton());
  await within(await callPanel()).findByText(/Listening…|The Draft is speaking…/);

  await userEvent.click(within(screen.getByRole("navigation", { name: "Agent views" })).getByRole("link", { name: "Versions" }));

  await waitFor(() => {
    expect(calls.filter((call) => call.route === "end")).toEqual([{ route: "end", conversationId: CONVERSATION_ID }]);
  });
});
