/**
 * Network seam: an Editor holds a real Playground Call (spec 20, ticket 20-13). When the API starts
 * the Call on the ElevenLabs voice layer, the Playground joins it with ElevenLabs' browser client
 * over WebRTC, handing over the Playground Call token as extra body. The client is replaced here by
 * a fake at the module boundary (`@elevenlabs/client`): each test drives what ElevenLabs would
 * report and checks what the Editor sees.
 */
import type { Callbacks, MessagePayload, VoiceConversation } from "@elevenlabs/client";
import type { Schemas } from "@studio/api-client";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { fakeAgentsApi, hrHelper } from "../test/agents";
import { adaSession, fakeAuthApi } from "../test/auth";
import { fakeProjectsApi, hrProject } from "../test/projects";
import { renderStudio } from "../test/render";
import { server } from "../test/server";
import { CALL_DROPPED } from "./AgentPage";

type FakeSession = { setMicMuted: ReturnType<typeof vi.fn>; endSession: ReturnType<typeof vi.fn> };
type Started = { options: Partial<Callbacks> & Record<string, unknown>; session: FakeSession };
type FakeClient = { sessions: Started[]; next: "join" | "fail" | "hold"; release: (() => void) | null };

const elevenLabs = vi.hoisted((): FakeClient => ({ sessions: [], next: "join", release: null }));

vi.mock("@elevenlabs/client", () => ({
  Conversation: {
    startSession: async (options: Record<string, unknown> & Partial<Callbacks>) => {
      const session: FakeSession = { setMicMuted: vi.fn(), endSession: vi.fn(async () => {}) };
      elevenLabs.sessions.push({ options, session });
      if (elevenLabs.next === "fail") throw new Error("Permission denied");
      if (elevenLabs.next === "hold") await new Promise<void>((resolve) => (elevenLabs.release = resolve));
      return session as unknown as VoiceConversation;
    },
  },
}));

const organisationId = adaSession.organisations[0]?.id ?? "";
const agentPage = `/organisations/${organisationId}/projects/${hrProject.id}/agents/${hrHelper.id}`;
const CONVERSATIONS = "*/api/organisations/:organisationId/projects/:projectId/agents/:agentId/playground/conversations/:conversationId";

function started(greet: boolean): Schemas["StartedCallOut"] {
  return {
    call_id: "a0000000-0000-4000-8000-000000000001",
    call_token: "wp1.call.sig",
    join: { voice_layer: "elevenlabs", conversation_token: "el-join-token", greet },
    max_call_minutes: 10,
  };
}

function setUp(greet = true) {
  elevenLabs.sessions = [];
  elevenLabs.next = "join";
  elevenLabs.release = null;
  fakeAuthApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: [hrHelper], callSettings: { calls_enabled: true } });
  const ended: string[] = [];
  server.use(
    http.post(`${CONVERSATIONS}/calls`, () => HttpResponse.json(started(greet), { status: 201 })),
    http.delete(`${CONVERSATIONS}/calls/current`, ({ params }) => {
      ended.push(params.conversationId as string);
      return new HttpResponse(null, { status: 204 });
    }),
    http.get(CONVERSATIONS, ({ params }) =>
      HttpResponse.json({
        id: params.conversationId as string,
        agent_id: hrHelper.id,
        is_playground: true,
        created_at: "2026-11-05T09:00:00Z",
        last_activity_at: "2026-11-05T09:00:00Z",
        messages: [],
        call_open: true,
      }),
    ),
  );
  return { ended };
}

async function call() {
  renderStudio(agentPage);
  await userEvent.click(await screen.findByRole("button", { name: "Call the Draft" }, { timeout: 5000 }));
  return screen.findByRole("group", { name: "Call" });
}

async function joined(): Promise<Started> {
  await waitFor(() => {
    expect(elevenLabs.sessions).toHaveLength(1);
  });
  return elevenLabs.sessions[0] as Started;
}

test("the Playground joins ElevenLabs with the Playground Call token and follows what it reports", async () => {
  setUp();
  const panel = await call();
  const { options, session } = await joined();

  expect(options).toMatchObject({
    conversationToken: "el-join-token",
    connectionType: "webrtc",
    customLlmExtraBody: { call_token: "wp1.call.sig" },
  });
  expect(options).not.toHaveProperty("overrides");
  act(() => {
    options.onConnect?.({ conversationId: "el-1" });
  });
  expect(within(panel).getByRole("status")).toHaveTextContent("Listening…");
  act(() => {
    options.onMessage?.({ role: "user", message: "How much leave?" } as MessagePayload);
  });
  expect(await screen.findByText("How much leave?")).toBeInTheDocument();
  act(() => {
    options.onModeChange?.({ mode: "speaking" });
  });
  expect(within(panel).getByRole("status")).toHaveTextContent("The Draft is speaking…");
  act(() => {
    options.onMessage?.({ role: "agent", message: "Twenty-five days." } as MessagePayload);
  });

  await userEvent.click(within(panel).getByRole("button", { name: "Mute" }));
  expect(session.setMicMuted).toHaveBeenLastCalledWith(true);
  await userEvent.click(within(panel).getByRole("button", { name: "End call" }));

  expect(session.endSession).toHaveBeenCalled();
  // ElevenLabs reports the Editor's own hang-up, and a late mode change, after the Call ended.
  act(() => {
    options.onDisconnect?.({ reason: "user" } as never);
    options.onModeChange?.({ mode: "listening" });
  });
  expect(screen.queryByText(CALL_DROPPED)).not.toBeInTheDocument();
});

test("a Conversation with Messages is joined without the greeting", async () => {
  setUp(false);
  await call();

  const { options } = await joined();

  expect(options).toMatchObject({ overrides: { agent: { firstMessage: "" } } });
});

test("ElevenLabs dropping the Call returns to the question box", async () => {
  const { ended } = setUp();
  await call();
  const { options } = await joined();

  act(() => {
    options.onDisconnect?.({ reason: "error", message: "lost" } as never);
  });

  expect(await screen.findByText(CALL_DROPPED)).toBeInTheDocument();
  expect(ended.length).toBeGreaterThan(0);
});

test("a refused microphone drops the Call", async () => {
  setUp();
  elevenLabs.next = "fail";
  await call();

  expect(await screen.findByText(CALL_DROPPED)).toBeInTheDocument();
});

test("a Call ended while ElevenLabs is still joining leaves it once joined", async () => {
  setUp();
  elevenLabs.next = "hold";
  const panel = await call();
  await waitFor(() => {
    expect(elevenLabs.release).not.toBeNull();
  });
  await waitFor(() => {
    expect(within(panel).getByRole("button", { name: "Mute" })).toBeEnabled();
  });
  await userEvent.click(within(panel).getByRole("button", { name: "Mute" }));

  await userEvent.click(within(panel).getByRole("button", { name: "End call" }));
  act(() => {
    elevenLabs.release?.();
  });

  const { session } = elevenLabs.sessions[0] as Started;
  await waitFor(() => {
    expect(session.endSession).toHaveBeenCalled();
  });
  expect(session.setMicMuted).not.toHaveBeenCalled();
});

test("a Call joined after the Editor muted it starts muted", async () => {
  setUp();
  elevenLabs.next = "hold";
  const panel = await call();
  await waitFor(() => {
    expect(elevenLabs.release).not.toBeNull();
  });
  await waitFor(() => {
    expect(within(panel).getByRole("button", { name: "Mute" })).toBeEnabled();
  });
  await userEvent.click(within(panel).getByRole("button", { name: "Mute" }));

  act(() => {
    elevenLabs.release?.();
  });

  const { session } = elevenLabs.sessions[0] as Started;
  await waitFor(() => {
    expect(session.setMicMuted).toHaveBeenCalledWith(true);
  });
});
