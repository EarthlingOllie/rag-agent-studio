/**
 * The widget's call client: what holds a Call with the voice layer once the API has started it.
 * The voice layer listens, takes turns and speaks; the call client tells the widget what the
 * Visitor said, when the Agent has spoken a reply, and whether the Agent is speaking or
 * listening. What the reply was (its text, sources and Message ID) the widget reads from our
 * API, so the Conversation log works as it does for a typed reply.
 *
 * The scripted implementation plays a Call without audio. It is used when the stack runs the
 * fake voice layer (`docker compose` and tests): it "says" its script one turn at a time, and the
 * fake voice layer holds each turn through the platform's turn endpoint, as ElevenLabs would.
 */
import { type Boot, ChatError, type StartedCall } from "./chat";

/** Whether the Agent is speaking, or listening to the Visitor. */
export type CallMode = "listening" | "speaking";

export type CallHandlers = {
  /** The voice layer heard the Visitor say this. */
  onVisitorWords: (words: string) => void;
  /** The Agent has spoken its reply to the Visitor's last words. */
  onReply: () => void;
  onMode: (mode: CallMode) => void;
  /** The Call can't go on. */
  onFailure: (failure: ChatError) => void;
};

/** A Call the call client holds. */
export type CallSession = {
  /** Stops (or restarts) sending the Visitor's microphone to the voice layer. */
  setMuted: (muted: boolean) => void;
  /** Leaves the Call. */
  end: () => void;
};

/** How long the scripted Call waits between what is said, so each state can be seen. */
export const SCRIPT_PAUSE_MS = 400;

const UNSUPPORTED = "Calls aren't available here yet. You can still send a message.";
const DROPPED = "The Call dropped. You can still send a message.";

/** What the scripted Visitor says: the Agent's first starter question, or a hello. */
export function script(boot: Boot): string[] {
  return [boot.starter_questions[0] ?? "Hello."];
}

function pause(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Plays a scripted Call against the fake voice layer, with no audio. */
function scripted(started: StartedCall, words: string[], handlers: CallHandlers): CallSession {
  let ended = false;
  let muted = false;
  let unmuted: (() => void) | null = null;
  // Read through a call: the Visitor may end the Call while a turn is awaited.
  const isEnded = () => ended;

  async function play() {
    handlers.onMode("listening");
    for (const said of words) {
      await pause(SCRIPT_PAUSE_MS);
      // A muted Visitor says nothing until they unmute.
      while (muted && !ended) await new Promise<void>((resolve) => (unmuted = resolve));
      if (ended) return;
      handlers.onVisitorWords(said);
      const response = await fetch(
        new URL(`/api/widget/fake-voice/calls/${encodeURIComponent(started.join.conversation_token)}/turns`, window.location.origin),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ words: said, call_token: started.call_token }),
        },
      );
      if (isEnded()) return;
      if (!response.ok) throw new ChatError(DROPPED, response.status);
      handlers.onMode("speaking");
      handlers.onReply();
      await pause(SCRIPT_PAUSE_MS);
      if (!isEnded()) handlers.onMode("listening");
    }
  }

  void play().catch((failure: unknown) => {
    if (!ended) handlers.onFailure(failure instanceof ChatError ? failure : new ChatError(DROPPED));
  });
  return {
    setMuted(next) {
      muted = next;
      if (!next) {
        unmuted?.();
        unmuted = null;
      }
    },
    end() {
      ended = true;
      unmuted?.();
      unmuted = null;
    },
  };
}

/**
 * Joins the Call the API started, with the call client for its voice layer. ElevenLabs' own
 * client comes with the real voice layer (ticket 20-05); until then such a Call can't be held.
 */
export function joinCall(boot: Boot, started: StartedCall, handlers: CallHandlers): CallSession {
  if (started.join.voice_layer !== "fake") throw new ChatError(UNSUPPORTED);
  return scripted(started, script(boot), handlers);
}
