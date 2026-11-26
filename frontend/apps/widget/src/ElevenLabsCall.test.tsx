/**
 * Network seam: a Visitor holds a real Call (spec 20, ticket 20-05). When the API starts a Call
 * on the ElevenLabs voice layer, the widget joins it with ElevenLabs' browser client over WebRTC,
 * handing over the Call token as extra body. The client is replaced here by a fake at the module
 * boundary (`@elevenlabs/client`): each test drives what ElevenLabs would report (the Visitor's
 * transcribed words, the Agent's reply, speaking and listening) and checks what the Visitor sees.
 */
import type { Callbacks, MessagePayload, Role, VoiceConversation } from "@elevenlabs/client";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../studio/src/test/server";
import type { Boot } from "./chat";
import { UNRATED } from "./Rating";
import { Widget } from "./Widget";

type FakeSession = {
  setMicMuted: ReturnType<typeof vi.fn>;
  endSession: ReturnType<typeof vi.fn>;
};
type Started = {
  options: Partial<Callbacks> & Record<string, unknown>;
  session: FakeSession;
};
type FakeClient = {
  loads: number;
  sessions: Started[];
  // What the next `startSession` does: join, fail as a refused microphone would, or wait for `release`.
  next: "join" | "fail" | "hold";
  release: (() => void) | null;
};

/** The fake ElevenLabs client: how often the module was loaded, and the sessions it started. */
const elevenLabs = vi.hoisted((): FakeClient => ({ loads: 0, sessions: [], next: "join", release: null }));

/**
 * The browser's microphone: how often the widget asked for it, how many of the tracks it was given
 * it stopped, and how the next request is answered (allowed, refused by the Visitor, or with no
 * microphone to use).
 */
const microphone = {
  requests: 0,
  stopped: 0,
  answer: "allow" as "allow" | "refuse" | "missing",
};

function fakeMicrophone() {
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: (constraints: MediaStreamConstraints) => {
        expect(constraints).toEqual({ audio: true });
        microphone.requests += 1;
        if (microphone.answer === "refuse") return Promise.reject(new DOMException("Permission denied", "NotAllowedError"));
        if (microphone.answer === "missing") return Promise.reject(new DOMException("Requested device not found", "NotFoundError"));
        return Promise.resolve({ getTracks: () => [{ stop: () => (microphone.stopped += 1) }] });
      },
    },
  });
}

/** The host page's Permissions Policy, as the browser reports it to the frame. */
function hostPolicy(allowsMicrophone: boolean) {
  Object.defineProperty(document, "featurePolicy", {
    configurable: true,
    value: { allowsFeature: (feature: string) => feature !== "microphone" || allowsMicrophone },
  });
}

vi.mock("@elevenlabs/client", () => {
  elevenLabs.loads += 1;
  return {
    Conversation: {
      startSession: async (options: Record<string, unknown> & Partial<Callbacks>) => {
        const session: FakeSession = {
          setMicMuted: vi.fn(),
          endSession: vi.fn(async () => {}),
        };
        elevenLabs.sessions.push({ options, session });
        if (elevenLabs.next === "fail") throw new Error("Permission denied");
        if (elevenLabs.next === "hold") await new Promise<void>((resolve) => (elevenLabs.release = resolve));
        return session as unknown as VoiceConversation;
      },
    },
  };
});

const boot: Boot = {
  agent: "agt_hr",
  name: "HR helper",
  bootstrap_token: "wb1.agt_hr.1.sig",
  theme: {
    mode: "light",
    launcher_type: "inline",
    launcher_position: "bottom-right",
    font: "Inter",
  },
  logo_url: null,
  avatar_url: null,
  greeting: "",
  starter_questions: [],
  ui_text: {
    send_button: null,
    rate_conversation: null,
    unavailable_message: null,
    searching_status: null,
  },
  citations: true,
  rating_prompt_after: 0,
  calls: true,
};
const API = "*/api/widget/agents/agt_hr";
const DROPPED = "The Call dropped. You can still send a message.";
const MIC_REFUSED = "A Call needs your microphone, and it wasn't allowed. You can still send a message.";
const MIC_BLOCKED = "This site doesn't let the chat use a microphone, so you can't call from here. You can still send a message.";
const MIC_UNUSABLE = "Your microphone couldn't be used, so the Call can't start. You can still send a message.";

const reply = {
  id: "r1",
  role: "assistant",
  content: "Twenty-five days [C1].",
  citations: [{ label: "C1", document_name: "handbook.pdf" }],
  feedback: null,
  spoken: true,
};
const question = {
  id: "q1",
  role: "user",
  content: "How much leave do I get?",
  citations: [],
  feedback: null,
  spoken: true,
};

function elevenLabsApi({ greet = true }: { greet?: boolean } = {}) {
  const seen: string[] = [];
  server.use(
    http.post(`${API}/conversations`, () => HttpResponse.json({ conversation_token: "wc1.token" }, { status: 201 })),
    http.post(`${API}/conversation/calls`, () => {
      seen.push("start call");
      return HttpResponse.json(
        {
          call_id: "c1",
          call_token: "wk2.call",
          join: {
            voice_layer: "elevenlabs",
            conversation_token: "livekit-room-token",
            greet,
          },
          max_call_minutes: 10,
        },
        { status: 201 },
      );
    }),
    http.delete(`${API}/conversation/calls/current`, () => {
      seen.push("end call");
      return new HttpResponse(null, { status: 204 });
    }),
    http.get(`${API}/conversation`, () => {
      seen.push("resume");
      return HttpResponse.json({
        messages: [question, reply],
        rating: UNRATED,
        call_open: true,
      });
    }),
  );
  return seen;
}

/** Why the Call ended: shown in the chat, and announced politely with its end rather than as an alert. */
async function saysWhy(reason: string): Promise<HTMLElement> {
  const note = await screen.findByText((_, element) => element?.matches("p.error") === true && element.textContent.includes(reason));
  expect(note).not.toHaveAttribute("role");
  await waitFor(() => {
    expect(screen.getByRole("status", { name: "Announcements" })).toHaveTextContent(reason);
  });
  return note;
}

beforeEach(() => {
  localStorage.clear();
  elevenLabs.sessions = [];
  elevenLabs.next = "join";
  elevenLabs.release = null;
  Object.assign(microphone, { requests: 0, stopped: 0, answer: "allow" });
  fakeMicrophone();
});

afterEach(() => {
  Reflect.deleteProperty(document, "featurePolicy");
  Reflect.deleteProperty(navigator, "mediaDevices");
});

async function choose(option: "Message" | "Call") {
  const choice = screen.getByRole("group", {
    name: "How would you like to ask?",
  });
  await userEvent.setup().click(within(choice).getByRole("button", { name: option }));
}

function callState() {
  return within(screen.getByRole("group", { name: "Call" })).getByRole("status");
}

/** A message as ElevenLabs reports it: the Visitor's transcribed words, or the Agent's reply. */
function said(role: Role, message: string, event_id: number): MessagePayload {
  return { role, message, event_id } as MessagePayload;
}

async function joined(): Promise<Started> {
  await waitFor(() => {
    expect(elevenLabs.sessions).toHaveLength(1);
  });
  const [started] = elevenLabs.sessions;
  if (!started) throw new Error("ElevenLabs was never joined");
  return started;
}

// Runs first: the module is loaded once per file.
test("Visitors who don't call never load the ElevenLabs client", async () => {
  elevenLabsApi();
  render(<Widget boot={boot} />);

  await choose("Message");
  expect(screen.getByLabelText("Message")).toBeInTheDocument();
  expect(elevenLabs.loads).toBe(0);
  expect(microphone.requests).toBe(0);
});

test("the microphone is asked for only once the Visitor picks Call, before ElevenLabs is joined", async () => {
  elevenLabsApi();
  render(<Widget boot={boot} />);
  expect(microphone.requests).toBe(0);

  await choose("Call");

  await joined();
  expect(microphone.requests).toBe(1);
  // Only asked: ElevenLabs' client opens the microphone it listens with.
  expect(microphone.stopped).toBe(1);
});

test("picking Call joins ElevenLabs over WebRTC with the Call token as extra body", async () => {
  elevenLabsApi();
  render(<Widget boot={boot} />);

  await choose("Call");

  const { options } = await joined();
  expect(elevenLabs.loads).toBe(1);
  expect(options).toMatchObject({
    conversationToken: "livekit-room-token",
    connectionType: "webrtc",
    customLlmExtraBody: { call_token: "wk2.call" },
  });
});

test("a Call that opens a Conversation with no Messages lets the remote agent speak its greeting", async () => {
  elevenLabsApi({ greet: true });
  render(<Widget boot={boot} />);

  await choose("Call");

  const { options } = await joined();
  expect(options).not.toHaveProperty("overrides");
});

test("any other Call opens with the Agent listening: its greeting is silenced", async () => {
  elevenLabsApi({ greet: false });
  render(<Widget boot={boot} />);

  await choose("Call");

  const { options } = await joined();
  expect(options).toMatchObject({ overrides: { agent: { firstMessage: "" } } });
});

test("the Visitor's words and the Agent's reply reach the log, with speaking and listening shown", async () => {
  const seen = elevenLabsApi();
  render(<Widget boot={boot} />);
  await choose("Call");
  const { options } = await joined();
  expect(callState()).toHaveTextContent("Connecting your call…");

  options.onConnect?.({ conversationId: "conv_1" });
  await waitFor(() => {
    expect(callState()).toHaveTextContent("Listening…");
  });
  options.onMessage?.(said("user", "How much leave do I get?", 1));
  expect(await screen.findByText("How much leave do I get?")).toBeInTheDocument();
  options.onModeChange?.({ mode: "speaking" });
  await waitFor(() => {
    expect(callState()).toHaveTextContent("HR helper is speaking…");
  });
  options.onMessage?.(said("agent", "Twenty-five days.", 2));

  // The reply as our API saved it, with its sources.
  expect(await screen.findByText(/Twenty-five days/)).toBeInTheDocument();
  expect(screen.getByText("handbook.pdf")).toBeInTheDocument();
  expect(seen).toContain("resume");
  options.onModeChange?.({ mode: "listening" });
  await waitFor(() => {
    expect(callState()).toHaveTextContent("Listening…");
  });
});

test("Mute mutes the microphone and unmuting turns it back on", async () => {
  elevenLabsApi();
  render(<Widget boot={boot} />);
  await choose("Call");
  const { options, session } = await joined();
  options.onConnect?.({ conversationId: "conv_1" });
  const user = userEvent.setup();
  const mute = await screen.findByRole("button", { name: "Mute" });
  await waitFor(() => {
    expect(mute).toBeEnabled();
  });

  await user.click(mute);
  expect(session.setMicMuted).toHaveBeenLastCalledWith(true);
  expect(callState()).toHaveTextContent("You're muted.");
  await user.click(mute);
  expect(session.setMicMuted).toHaveBeenLastCalledWith(false);
});

test("End call leaves the ElevenLabs session and ends the Call", async () => {
  const seen = elevenLabsApi();
  render(<Widget boot={boot} />);
  await choose("Call");
  const { options, session } = await joined();
  options.onConnect?.({ conversationId: "conv_1" });
  const end = await screen.findByRole("button", { name: "End call" });
  await waitFor(() => {
    expect(end).toBeEnabled();
  });

  await userEvent.setup().click(end);

  await waitFor(() => {
    expect(screen.getByLabelText("Message")).toBeInTheDocument();
  });
  expect(session.endSession).toHaveBeenCalled();
  expect(seen).toContain("end call");
  // ElevenLabs reports the Visitor's own hang-up; that is no failure.
  options.onDisconnect?.({ reason: "user" });
  // Nor is the connection closing after the Call ended.
  options.onDisconnect?.({ reason: "error", message: "Connection closed", context: { type: "close" } });
  expect(screen.queryByText(DROPPED)).not.toBeInTheDocument();
});

test("a Call ElevenLabs drops returns to messaging", async () => {
  const seen = elevenLabsApi();
  render(<Widget boot={boot} />);
  await choose("Call");
  const { options } = await joined();

  options.onDisconnect?.({
    reason: "error",
    message: "Connection lost",
    context: { type: "error" },
  });

  await saysWhy(DROPPED);
  expect(screen.getByLabelText("Message")).toBeInTheDocument();
  expect(seen).toContain("end call");
});

test("a Call ElevenLabs can't join returns to messaging", async () => {
  elevenLabs.next = "fail";
  const seen = elevenLabsApi();
  render(<Widget boot={boot} />);

  await choose("Call");

  await saysWhy(DROPPED);
  expect(screen.getByLabelText("Message")).toBeInTheDocument();
  expect(seen).toContain("end call");
});

test("a refused microphone says so and opens the chat, without joining ElevenLabs", async () => {
  microphone.answer = "refuse";
  const seen = elevenLabsApi();
  render(<Widget boot={boot} />);

  await choose("Call");

  await saysWhy(MIC_REFUSED);
  expect(screen.getByLabelText("Message")).toHaveFocus();
  expect(elevenLabs.sessions).toHaveLength(0);
  expect(seen).toContain("end call");
});

test("a host page whose policy blocks the microphone says so and opens the chat, without asking for it", async () => {
  hostPolicy(false);
  const seen = elevenLabsApi();
  render(<Widget boot={boot} />);

  await choose("Call");

  await saysWhy(MIC_BLOCKED);
  expect(screen.getByLabelText("Message")).toBeInTheDocument();
  expect(microphone.requests).toBe(0);
  expect(elevenLabs.sessions).toHaveLength(0);
  expect(seen).toContain("end call");
});

test("a host page whose policy allows the microphone asks for it", async () => {
  hostPolicy(true);
  elevenLabsApi();
  render(<Widget boot={boot} />);

  await choose("Call");

  await joined();
  expect(microphone.requests).toBe(1);
});

test("a page with no microphone access at all (not a secure context) says the site blocks it", async () => {
  Reflect.deleteProperty(navigator, "mediaDevices");
  elevenLabsApi();
  render(<Widget boot={boot} />);

  await choose("Call");

  await saysWhy(MIC_BLOCKED);
  expect(screen.getByLabelText("Message")).toBeInTheDocument();
});

test("a microphone that can't be used says so and opens the chat", async () => {
  microphone.answer = "missing";
  elevenLabsApi();
  render(<Widget boot={boot} />);

  await choose("Call");

  await saysWhy(MIC_UNUSABLE);
  expect(screen.getByLabelText("Message")).toBeInTheDocument();
  expect(elevenLabs.sessions).toHaveLength(0);
});

test("a widget that leaves the page while ElevenLabs is still joining leaves the session once it joins", async () => {
  elevenLabs.next = "hold";
  const seen = elevenLabsApi();
  const { unmount } = render(<Widget boot={boot} />);
  await choose("Call");
  const { session } = await joined();

  unmount();
  elevenLabs.release?.();

  await waitFor(() => {
    expect(session.endSession).toHaveBeenCalled();
  });
  expect(session.setMicMuted).not.toHaveBeenCalled();
  await waitFor(() => {
    expect(seen).toContain("end call");
  });
});

// Interruptions (ticket 20-11)

test("when the Visitor talks over a reply the widget tells the API, and the Call goes on", async () => {
  const seen = elevenLabsApi();
  const interruptions: (string | null)[] = [];
  server.use(
    http.post(`${API}/conversation/calls/current/interruptions`, ({ request }) => {
      interruptions.push(request.headers.get("Authorization"));
      return new HttpResponse(null, { status: 204 });
    }),
  );
  render(<Widget boot={boot} />);
  await choose("Call");
  const { options } = await joined();
  options.onConnect?.({ conversationId: "conv_1" });
  options.onMessage?.(said("user", "How much leave do I get?", 1));
  options.onModeChange?.({ mode: "speaking" });
  options.onMessage?.(said("agent", "Twenty-five days.", 2));
  expect(await screen.findByText(/Twenty-five days/)).toBeInTheDocument();

  options.onInterruption?.({ event_id: 2 });
  options.onModeChange?.({ mode: "listening" });

  await waitFor(() => {
    expect(interruptions).toEqual(["Bearer wc1.token"]);
  });
  await waitFor(() => {
    expect(callState()).toHaveTextContent("Listening…");
  });
  expect(seen).not.toContain("end call");
});

test("an interruption the API can't be told of leaves the Call going", async () => {
  elevenLabsApi();
  server.use(http.post(`${API}/conversation/calls/current/interruptions`, () => HttpResponse.error()));
  render(<Widget boot={boot} />);
  await choose("Call");
  const { options } = await joined();
  options.onConnect?.({ conversationId: "conv_1" });

  options.onInterruption?.({ event_id: 1 });

  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(screen.getByRole("group", { name: "Call" })).toBeInTheDocument();
  expect(screen.queryByText(DROPPED)).not.toBeInTheDocument();
});
