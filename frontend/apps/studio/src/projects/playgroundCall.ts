/**
 * The Playground's call client: what holds a Playground Call with the voice layer once the API has
 * started it. The voice layer listens, takes turns and speaks; the call client tells the Playground
 * what the Editor said, when the Draft has spoken a reply, and whether it is speaking or listening.
 * The reply itself (its text, Searches, sources and Trace) the Playground reads from the API.
 *
 * With ElevenLabs, the browser joins the Call over WebRTC with ElevenLabs' own client, loaded only
 * when an Editor starts a Call. It hands ElevenLabs the Playground Call token as extra body, which
 * ElevenLabs passes to the turn endpoint with every turn.
 *
 * With the fake voice layer (`docker compose` and tests) the Call is played without audio: the
 * Editor "says" a script one turn at a time, and the fake voice layer holds each turn through the
 * turn endpoint, as ElevenLabs would.
 */
import type { VoiceConversation } from "@elevenlabs/client";

import type { StartedCall } from "./agents";

/** Whether the Draft is speaking, or listening to the Editor. */
export type CallMode = "listening" | "speaking";

export type CallHandlers = {
  /** The voice layer heard the Editor say this. */
  onWords: (words: string) => void;
  /** The Draft has spoken its reply to the Editor's last words. */
  onReply: () => void;
  onMode: (mode: CallMode) => void;
  /** The Call can't go on. */
  onDropped: () => void;
};

/** A Call the call client holds. */
export type CallSession = {
  /** Stops (or restarts) sending the Editor's microphone to the voice layer. */
  setMuted: (muted: boolean) => void;
  /** Leaves the Call. */
  end: () => void;
};

/** How long the scripted Call waits between what is said, so each state can be seen. */
export const SCRIPT_PAUSE_MS = 400;

/** The handlers, silenced once the Call has ended: nothing the voice layer reports after the
 * Editor left reaches the Playground. */
function untilEnded(handlers: CallHandlers, isEnded: () => boolean): CallHandlers {
  const live =
    <A extends unknown[]>(handler: (...args: A) => void) =>
    (...args: A) => {
      if (!isEnded()) handler(...args);
    };
  return {
    onWords: live(handlers.onWords),
    onReply: live(handlers.onReply),
    onMode: live(handlers.onMode),
    onDropped: live(handlers.onDropped),
  };
}

function pause(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Plays a scripted Call against the fake voice layer, with no audio. */
function scripted(started: StartedCall, words: string[], handlers: CallHandlers): CallSession {
  let ended = false;
  let muted = false;
  let unmuted: (() => void) | null = null;
  const live = untilEnded(handlers, () => ended);

  async function play() {
    live.onMode("listening");
    for (const said of words) {
      await pause(SCRIPT_PAUSE_MS);
      // A muted Editor says nothing until they unmute.
      while (muted && !ended) await new Promise<void>((resolve) => (unmuted = resolve));
      if (ended) return;
      live.onWords(said);
      const response = await fetch(
        new URL(`/api/widget/fake-voice/calls/${encodeURIComponent(started.join.conversation_token)}/turns`, window.location.origin),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ words: said, call_token: started.call_token }),
        },
      );
      if (!response.ok) throw new Error("The turn was refused.");
      live.onMode("speaking");
      live.onReply();
      await pause(SCRIPT_PAUSE_MS);
      live.onMode("listening");
    }
  }

  play().catch(live.onDropped);
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

/** Holds the Call with ElevenLabs' browser client, loaded now. */
function elevenLabs(started: StartedCall, handlers: CallHandlers): CallSession {
  let ended = false;
  let muted = false;
  let session: VoiceConversation | null = null;
  const live = untilEnded(handlers, () => ended);

  import("@elevenlabs/client")
    .then(({ Conversation }) =>
      Conversation.startSession({
        conversationToken: started.join.conversation_token,
        connectionType: "webrtc",
        textOnly: false,
        // ElevenLabs sends it to the turn endpoint with every turn: which Call the turn is in.
        customLlmExtraBody: { call_token: started.call_token },
        // The spoken greeting opens only a Conversation with no Messages.
        ...(started.join.greet ? {} : { overrides: { agent: { firstMessage: "" } } }),
        onConnect: () => {
          live.onMode("listening");
        },
        onModeChange: ({ mode }) => {
          live.onMode(mode);
        },
        // The Editor's transcribed words; for the Draft, only that it has replied.
        onMessage: ({ role, message }) => {
          if (role === "user") live.onWords(message);
          else live.onReply();
        },
        onDisconnect: (details) => {
          if (details.reason !== "user") live.onDropped();
        },
      }),
    )
    .then((joined) => {
      if (ended) {
        void joined.endSession();
        return;
      }
      session = joined;
      joined.setMicMuted(muted);
    })
    // The client couldn't load, the microphone was refused, or ElevenLabs couldn't be joined.
    .catch(() => {
      live.onDropped();
    });
  return {
    setMuted(next) {
      muted = next;
      session?.setMicMuted(next);
    },
    end() {
      ended = true;
      void session?.endSession();
      session = null;
    },
  };
}

/** Joins the Playground Call the API started, with the call client for its voice layer. With the
 * fake voice layer the Editor "says" `script`. */
export function joinCall(started: StartedCall, script: string[], handlers: CallHandlers): CallSession {
  if (started.join.voice_layer === "fake") return scripted(started, script, handlers);
  return elevenLabs(started, handlers);
}
