/**
 * Network seam: a Visitor calls the Agent (spec 20). With calling on, the Launcher's panel opens on
 * a choice of Message or Call. Choosing Call starts a Call through the widget API and holds it
 * with the scripted call client, which the fake voice layer answers: the log fills with the
 * Visitor's words, then the Agent's reply as our API saved it (its sources and Message ID), while
 * the Call view shows whether the Agent is speaking or listening, with Mute and End call.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../studio/src/test/server";
import { SCRIPT_PAUSE_MS } from "./call";
import type { Boot } from "./chat";
import { UNRATED } from "./Rating";
import { CALL_UNAVAILABLE, Widget } from "./Widget";

const boot: Boot = {
  agent: "agt_hr",
  name: "HR helper",
  bootstrap_token: "wb1.agt_hr.1.sig",
  theme: { mode: "light", launcher_type: "inline", launcher_position: "bottom-right", font: "Inter" },
  logo_url: null,
  avatar_url: null,
  greeting: "",
  starter_questions: ["How much leave do I get?"],
  ui_text: { send_button: null, rate_conversation: null, unavailable_message: null, searching_status: null },
  citations: true,
  rating_prompt_after: 0,
  calls: true,
};
const API = "*/api/widget/agents/agt_hr";
const UNAVAILABLE = "This assistant is temporarily unavailable. Please try again later.";
const DROPPED = "The Call dropped. You can still send a message.";

type Seen = { route: string; authorization?: string | null; body?: unknown };

const spokenMessages = [
  { id: "q1", role: "user", content: "How much leave do I get?", citations: [], feedback: null, spoken: true },
  {
    id: "r1",
    role: "assistant",
    content: "Twenty-five days [C1].",
    citations: [{ label: "C1", document_name: "handbook.pdf" }],
    feedback: null,
    spoken: true,
  },
];

function json(body: unknown, status = 200): Response {
  return HttpResponse.json(body as never, { status });
}

/** The widget API and the fake voice layer, recording what the widget asked. */
function fakeCallApi({
  startCall = () =>
    json({ call_id: "c1", call_token: "wk2.call", join: { voice_layer: "fake", conversation_token: "fake-call-1" }, max_call_minutes: 10 }, 201),
  turn = () => json({ agent_response: "Twenty-five days." }),
  history = () => json({ messages: spokenMessages, rating: UNRATED, call_open: true }),
  startConversation = () => json({ conversation_token: "wc1.token" }, 201),
}: {
  startCall?: () => Response | Promise<Response>;
  turn?: () => Response | Promise<Response>;
  history?: () => Response | Promise<Response>;
  startConversation?: () => Response;
} = {}) {
  const seen: Seen[] = [];
  server.use(
    http.post(`${API}/conversations`, () => {
      seen.push({ route: "start conversation" });
      return startConversation();
    }),
    http.post(`${API}/conversation/calls`, ({ request }) => {
      seen.push({ route: "start call", authorization: request.headers.get("Authorization") });
      return startCall();
    }),
    http.delete(`${API}/conversation/calls/current`, ({ request }) => {
      seen.push({ route: "end call", authorization: request.headers.get("Authorization") });
      return new HttpResponse(null, { status: 204 });
    }),
    http.get(`${API}/conversation`, () => {
      seen.push({ route: "resume" });
      return history();
    }),
    http.post("*/api/widget/fake-voice/calls/:join/turns", async ({ request, params }) => {
      seen.push({ route: `turn ${String(params.join)}`, body: await request.json() });
      return turn();
    }),
  );
  return seen;
}

beforeEach(() => {
  localStorage.clear();
});

async function choose(option: "Message" | "Call") {
  const choice = screen.getByRole("group", { name: "How would you like to ask?" });
  await userEvent.setup().click(within(choice).getByRole("button", { name: option }));
}

function callState() {
  return within(screen.getByRole("group", { name: "Call" })).getByRole("status");
}

function after(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

test("an Agent that doesn't take Calls opens straight into the chat", () => {
  render(<Widget boot={{ ...boot, calls: false }} />);

  expect(screen.getByLabelText("Message")).toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "How would you like to ask?" })).not.toBeInTheDocument();
});

test("with calling on the panel opens on a choice, and Message opens the chat", async () => {
  render(<Widget boot={boot} />);
  expect(screen.queryByLabelText("Message")).not.toBeInTheDocument();
  expect(screen.queryByRole("list", { name: "Suggested questions" })).not.toBeInTheDocument();

  await choose("Message");

  expect(screen.getByLabelText("Message")).toHaveFocus();
  expect(screen.getByRole("list", { name: "Suggested questions" })).toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "How would you like to ask?" })).not.toBeInTheDocument();
});

test("a Visitor holds a scripted Call: the log fills with what was said, then End call returns to the chat", async () => {
  const seen = fakeCallApi();
  render(<Widget boot={boot} />);

  await choose("Call");

  const log = screen.getByRole("log", { name: "Conversation" });
  expect(screen.queryByLabelText("Message")).not.toBeInTheDocument();
  expect(callState()).toHaveTextContent(/Connecting your call…|Listening…/);
  await waitFor(() => {
    expect(callState()).toHaveTextContent("Listening…");
  });
  // The Visitor's words appear as the voice layer hears them…
  expect(await within(log).findByText("How much leave do I get?")).toBeInTheDocument();
  // …then the Agent's full reply, from our API, with its sources and Message Feedback.
  const reply = (await within(log).findByText("Twenty-five days [C1].")).closest("li") as HTMLElement;
  expect(reply).toHaveTextContent("Sources: handbook.pdf");
  expect(within(reply).getByRole("button", { name: "Helpful" })).toBeInTheDocument();
  expect(callState()).toHaveTextContent("HR helper is speaking…");
  await waitFor(() => {
    expect(callState()).toHaveTextContent("Listening…");
  });

  await userEvent.setup().click(screen.getByRole("button", { name: "End call" }));

  expect(await screen.findByLabelText("Message")).toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "Call" })).not.toBeInTheDocument();
  expect(within(log).getByText("Twenty-five days [C1].")).toBeInTheDocument();
  expect(seen).toEqual([
    { route: "start conversation" },
    { route: "start call", authorization: "Bearer wc1.token" },
    { route: "turn fake-call-1", body: { words: "How much leave do I get?", call_token: "wk2.call" } },
    { route: "resume" },
    { route: "end call", authorization: "Bearer wc1.token" },
    { route: "resume" },
  ]);
});

test("a muted Visitor says nothing until they unmute", async () => {
  const seen = fakeCallApi();
  render(<Widget boot={{ ...boot, starter_questions: [] }} />);
  await choose("Call");
  const mute = await screen.findByRole("button", { name: "Mute" });
  await waitFor(() => {
    expect(mute).toBeEnabled();
  });
  const user = userEvent.setup();

  await user.click(mute);

  expect(mute).toHaveAttribute("aria-pressed", "true");
  expect(callState()).toHaveTextContent("You're muted.");
  await after(SCRIPT_PAUSE_MS * 2);
  expect(seen.filter((s) => s.route.startsWith("turn"))).toEqual([]);

  await user.click(mute);

  expect(mute).toHaveAttribute("aria-pressed", "false");
  // With no starter question, the scripted Visitor says hello.
  expect(await screen.findByText("Twenty-five days [C1].")).toBeInTheDocument();
  expect(seen.find((s) => s.route.startsWith("turn"))?.body).toEqual({ words: "Hello.", call_token: "wk2.call" });
});

test("ending a muted Call says nothing more", async () => {
  const seen = fakeCallApi();
  render(<Widget boot={boot} />);
  await choose("Call");
  const user = userEvent.setup();
  const mute = await screen.findByRole("button", { name: "Mute" });
  await waitFor(() => {
    expect(mute).toBeEnabled();
  });
  await user.click(mute);
  await after(SCRIPT_PAUSE_MS * 2);

  await user.click(screen.getByRole("button", { name: "End call" }));

  expect(await screen.findByLabelText("Message")).toBeInTheDocument();
  await after(SCRIPT_PAUSE_MS);
  expect(seen.filter((s) => s.route.startsWith("turn"))).toEqual([]);
});

test("a Call ended before anything is said sends no words", async () => {
  const seen = fakeCallApi();
  render(<Widget boot={boot} />);
  await choose("Call");
  const end = await screen.findByRole("button", { name: "End call" });
  await waitFor(() => {
    expect(end).toBeEnabled();
  });

  await userEvent.setup().click(end);

  expect(await screen.findByLabelText("Message")).toBeInTheDocument();
  await after(SCRIPT_PAUSE_MS * 2);
  expect(seen.filter((s) => s.route.startsWith("turn"))).toEqual([]);
});

test("a Call ended while the Agent answers takes no reply", async () => {
  let answer: (response: Response) => void = () => undefined;
  const seen = fakeCallApi({
    turn: () =>
      new Promise<Response>((resolve) => {
        answer = resolve;
      }),
    history: () => json({ messages: [spokenMessages[0]], rating: UNRATED }),
  });
  render(<Widget boot={boot} />);
  await choose("Call");
  expect(await screen.findByText("How much leave do I get?")).toBeInTheDocument();

  await userEvent.setup().click(screen.getByRole("button", { name: "End call" }));
  await screen.findByLabelText("Message");
  answer(json({ agent_response: "Too late." }));
  await after(50);

  expect(seen.filter((s) => s.route === "resume")).toHaveLength(1);
  expect(screen.queryByText("Twenty-five days [C1].")).not.toBeInTheDocument();
});

test("a Call ended while the Agent speaks stays ended", async () => {
  fakeCallApi();
  render(<Widget boot={boot} />);
  await choose("Call");
  expect(await screen.findByText("HR helper is speaking…")).toBeInTheDocument();

  await userEvent.setup().click(screen.getByRole("button", { name: "End call" }));
  await screen.findByLabelText("Message");
  await after(SCRIPT_PAUSE_MS * 2);

  expect(screen.queryByRole("group", { name: "Call" })).not.toBeInTheDocument();
});

test("a Call that reaches the Maximum Call length returns to the chat saying why", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    const seen = fakeCallApi({
      startCall: () =>
        json({ call_id: "c1", call_token: "wk2.call", join: { voice_layer: "fake", conversation_token: "fake-call-1" }, max_call_minutes: 3 }, 201),
    });
    render(<Widget boot={boot} />);
    await choose("Call");
    const log = screen.getByRole("log", { name: "Conversation" });
    expect(await within(log).findByText("Twenty-five days [C1].")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    vi.advanceTimersByTime(3 * 60_000);

    expect(await screen.findByRole("alert")).toHaveTextContent("The Call reached its 3-minute limit. You can still send a message.");
    expect(screen.getByLabelText("Message")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Call" })).not.toBeInTheDocument();
    expect(seen.map((s) => s.route)).toContain("end call");
  } finally {
    vi.useRealTimers();
  }
});

test("a widget closed while its Call is starting doesn't join the Call, and ends it", async () => {
  let answer: (response: Response) => void = () => undefined;
  const seen = fakeCallApi({ startCall: () => new Promise<Response>((resolve) => (answer = resolve)) });
  const { unmount } = render(<Widget boot={boot} />);
  await choose("Call");
  await waitFor(() => {
    expect(seen.map((s) => s.route)).toContain("start call");
  });

  unmount();
  answer(json({ call_id: "c1", call_token: "wk2.call", join: { voice_layer: "fake", conversation_token: "fake-call-1" }, max_call_minutes: 1 }, 201));

  await waitFor(() => {
    expect(seen.map((s) => s.route)).toEqual(["start conversation", "start call", "end call"]);
  });
  await after(SCRIPT_PAUSE_MS * 2);
  expect(seen.map((s) => s.route)).toEqual(["start conversation", "start call", "end call"]);
});

test("a widget that leaves the page during its Call leaves the Call and ends it", async () => {
  const seen = fakeCallApi();
  const { unmount } = render(<Widget boot={boot} />);
  await choose("Call");
  await waitFor(() => {
    expect(callState()).toHaveTextContent("Listening…");
  });

  unmount();

  await waitFor(() => {
    expect(seen.map((s) => s.route)).toEqual(["start conversation", "start call", "end call"]);
  });
  // The voice session stopped too: the Visitor's words never reach the voice layer.
  await after(SCRIPT_PAUSE_MS * 2);
  expect(seen.map((s) => s.route)).toEqual(["start conversation", "start call", "end call"]);
});

test("a Call refused by the Call limits offers messaging with the unavailable text", async () => {
  for (const reason of ["call_open", "too_many_calls", "call_minutes_exhausted"]) {
    fakeCallApi({ startCall: () => json({ detail: UNAVAILABLE, reason }, 503) });
    const { unmount } = render(<Widget boot={boot} />);

    await choose("Call");

    expect(await screen.findByRole("alert")).toHaveTextContent(UNAVAILABLE);
    expect(screen.getByLabelText("Message")).toBeInTheDocument();
    unmount();
    localStorage.clear();
  }
});

test("a Call the voice layer drops returns to the chat saying so", async () => {
  fakeCallApi({ turn: () => json({ detail: "The Call token is invalid." }, 502) });
  render(<Widget boot={boot} />);

  await choose("Call");

  expect(await screen.findByRole("alert")).toHaveTextContent(DROPPED);
  expect(screen.getByLabelText("Message")).toBeInTheDocument();
});

test("a Call whose voice layer can't be reached returns to the chat saying so", async () => {
  fakeCallApi({ turn: () => HttpResponse.error() });
  render(<Widget boot={boot} />);

  await choose("Call");

  expect(await screen.findByRole("alert")).toHaveTextContent(DROPPED);
});

test("a Call refused by admission control shows the Agent's unavailable text, or its override", async () => {
  const seen = fakeCallApi({ startCall: () => json({ detail: UNAVAILABLE, reason: "rate_limited" }, 503) });
  const { unmount } = render(<Widget boot={boot} />);

  await choose("Call");

  expect(await screen.findByRole("alert")).toHaveTextContent(UNAVAILABLE);
  expect(screen.getByLabelText("Message")).toBeInTheDocument();
  expect(seen.map((s) => s.route)).toEqual(["start conversation", "start call", "end call", "resume"]);
  unmount();
  localStorage.clear();

  render(<Widget boot={{ ...boot, ui_text: { ...boot.ui_text, unavailable_message: "Calls are busy." } }} />);
  await choose("Call");
  expect(await screen.findByRole("alert")).toHaveTextContent("Calls are busy.");
});

test("a Call the widget can't hold yet says so", async () => {
  fakeCallApi({
    startCall: () => json({ call_id: "c1", call_token: "wk2.call", join: { voice_layer: "elevenlabs", conversation_token: "lk" } }, 201),
  });
  render(<Widget boot={boot} />);

  await choose("Call");

  expect(await screen.findByRole("alert")).toHaveTextContent("Calls aren't available here yet. You can still send a message.");
});

test("a Call that can't start a Conversation says so", async () => {
  const seen = fakeCallApi({ startConversation: () => json({ detail: "Nope." }, 500) });
  render(<Widget boot={boot} />);

  await choose("Call");

  expect(await screen.findByRole("alert")).toHaveTextContent("Nope.");
  expect(seen.map((s) => s.route)).toEqual(["start conversation"]);
});

test("an expired chat forgets its token when a Call is refused", async () => {
  localStorage.setItem("rag-widget:conversation:agt_hr", "wc1.old");
  const seen = fakeCallApi({
    history: () => json({ messages: [], rating: UNRATED }),
    startCall: () => json({ detail: "This chat has expired. Reload the page to start a new one." }, 401),
  });
  render(<Widget boot={boot} />);
  await screen.findByRole("group", { name: "How would you like to ask?" });

  await choose("Call");

  expect(await screen.findByRole("alert")).toHaveTextContent("This chat has expired.");
  expect(localStorage.getItem("rag-widget:conversation:agt_hr")).toBeNull();
  expect(seen.map((s) => s.route)).toEqual(["resume", "start call"]);
});

test("a retired Agent says so when a Call is chosen", async () => {
  fakeCallApi({ startCall: () => json({ detail: "This assistant is no longer available." }, 404) });
  render(<Widget boot={boot} />);

  await choose("Call");

  expect(await screen.findByText("This assistant is no longer available.")).toBeInTheDocument();
});

test("the log keeps what was heard when the Conversation can't be read back", async () => {
  fakeCallApi({ history: () => json({ detail: "Down." }, 500) });
  render(<Widget boot={boot} />);
  await choose("Call");
  expect(await screen.findByText("HR helper is speaking…")).toBeInTheDocument();

  await userEvent.setup().click(screen.getByRole("button", { name: "End call" }));

  expect(await screen.findByLabelText("Message")).toBeInTheDocument();
  expect(screen.getByText("How much leave do I get?")).toBeInTheDocument();
});

test("a Call ended before its voice layer fails says nothing of the failure", async () => {
  let fail: (response: Response) => void = () => undefined;
  fakeCallApi({
    turn: () =>
      new Promise<Response>((resolve) => {
        fail = resolve;
      }),
  });
  render(<Widget boot={boot} />);
  await choose("Call");
  expect(await screen.findByText("How much leave do I get?")).toBeInTheDocument();

  await userEvent.setup().click(screen.getByRole("button", { name: "End call" }));
  await screen.findByLabelText("Message");
  fail(HttpResponse.error());
  await after(50);

  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("an Agent that can't answer in a Call returns the Visitor to messaging, saying so", async () => {
  // The Agent spoke its Unavailable text and the platform ended the Call.
  const unanswered = [spokenMessages[0]];
  const seen = fakeCallApi({ history: () => json({ messages: unanswered, rating: UNRATED, call_open: false }) });
  const { unmount } = render(<Widget boot={boot} />);

  await choose("Call");

  expect(await screen.findByRole("alert")).toHaveTextContent(CALL_UNAVAILABLE);
  expect(screen.getByLabelText("Message")).toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "Call" })).not.toBeInTheDocument();
  expect(screen.getByText("How much leave do I get?")).toBeInTheDocument();
  expect(seen.map((s) => s.route).slice(-3)).toEqual(["resume", "end call", "resume"]);
  unmount();
  localStorage.clear();

  fakeCallApi({ history: () => json({ messages: unanswered, rating: UNRATED, call_open: false }) });
  render(<Widget boot={{ ...boot, ui_text: { ...boot.ui_text, unavailable_message: "We're closed. Please type." } }} />);
  await choose("Call");
  expect(await screen.findByRole("alert")).toHaveTextContent("We're closed. Please type.");
});

test("a Call whose chat expired returns the Visitor to messaging", async () => {
  fakeCallApi({ history: () => json({ detail: "This chat has expired." }, 401) });
  render(<Widget boot={boot} />);

  await choose("Call");

  expect(await screen.findByRole("alert")).toHaveTextContent(CALL_UNAVAILABLE);
  expect(screen.getByLabelText("Message")).toBeInTheDocument();
});

test("an Agent retired during a Call is shown retired", async () => {
  const seen = fakeCallApi({ history: () => json({ detail: "This assistant is no longer available." }, 404) });
  render(<Widget boot={boot} />);

  await choose("Call");

  expect(await screen.findByText("This assistant is no longer available.")).toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "Call" })).not.toBeInTheDocument();
  expect(localStorage.getItem("rag-widget:conversation:agt_hr")).toBeNull();
  // The platform ended the Call with the unavailable turn; the widget only leaves it.
  expect(seen.map((s) => s.route)).not.toContain("end call");
});

test("a Call ended while its reply is read back stays ended without an alert", async () => {
  let readBack: (response: Response) => void = () => undefined;
  let reads = 0;
  fakeCallApi({
    history: () => {
      reads += 1;
      if (reads > 1) return json({ messages: spokenMessages, rating: UNRATED, call_open: false });
      return new Promise<Response>((resolve) => {
        readBack = resolve;
      });
    },
  });
  render(<Widget boot={boot} />);
  await choose("Call");
  await waitFor(() => {
    expect(reads).toBe(1);
  });

  await userEvent.setup().click(screen.getByRole("button", { name: "End call" }));
  await screen.findByLabelText("Message");
  readBack(json({ messages: spokenMessages, rating: UNRATED, call_open: false }));
  await after(50);

  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
