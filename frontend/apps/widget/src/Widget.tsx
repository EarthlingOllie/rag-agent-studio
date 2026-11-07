import { type SubmitEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  type Boot,
  type Citation,
  ChatError,
  NO_LONGER_AVAILABLE,
  ask,
  endConversation,
  resume,
  startConversation,
} from "./chat";
import { tokenStore } from "./storage";

type Message = { role: "visitor" | "agent"; text: string; citations: Citation[] };

/**
 * - `loading`: checking a kept Conversation token, to resume its Conversation.
 * - `chat`: the chat.
 * - `ended`: the Visitor ended the chat.
 * - `retired`: the Agent is archived or no longer live.
 */
type Phase = "loading" | "chat" | "ended" | "retired";

const GENERIC = "Something went wrong. Please try again.";

function message(failure: unknown): string {
  return failure instanceof ChatError ? failure.message : GENERIC;
}

/** The chat a Visitor sees inside the iframe: their questions and the Agent's streamed replies. */
export function Widget({ boot }: { boot: Boot }) {
  const store = useMemo(() => tokenStore(boot.agent), [boot.agent]);
  const [phase, setPhase] = useState<Phase>(() => (store.load() ? "loading" : "chat"));
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The Conversation token, once the bootstrap token has been exchanged for one (or kept from
  // an earlier page load).
  const token = useRef<string | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const focusInput = useRef(false);

  function forget() {
    token.current = null;
    store.clear();
  }

  function retire() {
    forget();
    setPhase("retired");
  }

  // A Visitor coming back within 24 hours gets their Conversation back.
  useEffect(() => {
    const kept = store.load();
    if (!kept) return;
    let current = true;
    resume(boot, kept).then(
      (resumed) => {
        if (!current) return;
        if (resumed === null) {
          store.clear();
        } else {
          token.current = kept;
          setMessages(
            resumed.map((m) => ({
              role: m.role === "user" ? "visitor" : "agent",
              text: m.content,
              citations: m.citations,
            })),
          );
        }
        setPhase("chat");
      },
      (failure: unknown) => {
        if (!current) return;
        if (failure instanceof ChatError && failure.status === 404) {
          store.clear();
          setPhase("retired");
          return;
        }
        // Keep the token: the Conversation can carry on even if its history didn't load.
        token.current = kept;
        setError(message(failure));
        setPhase("chat");
      },
    );
    return () => {
      current = false;
    };
  }, [boot, store]);

  useEffect(() => {
    if (focusInput.current && phase === "chat") {
      focusInput.current = false;
      input.current?.focus();
    }
  });

  function updateReply(update: (reply: Message) => Message) {
    setMessages((current) => [...current.slice(0, -1), update(current[current.length - 1] as Message)]);
  }

  async function send(question: string) {
    setError(null);
    setPending(true);
    setMessages((current) => [
      ...current,
      { role: "visitor", text: question, citations: [] },
      { role: "agent", text: "", citations: [] },
    ]);
    try {
      if (token.current === null) {
        token.current = await startConversation(boot);
        store.save(token.current);
      }
      await ask(boot, token.current, question, {
        onToken: (text) => {
          updateReply((reply) => ({ ...reply, text: reply.text + text }));
        },
        onReplace: (text) => {
          updateReply((reply) => ({ ...reply, text }));
        },
        onCitation: (citation) => {
          updateReply((reply) => ({ ...reply, citations: [...reply.citations, citation] }));
        },
      });
    } catch (failure) {
      if (failure instanceof ChatError && failure.status === 404) {
        retire();
        return;
      }
      // An expired or ended token: the next question starts a new Conversation.
      if (failure instanceof ChatError && failure.status === 401) forget();
      // Drop the reply and whatever of it streamed before the failure.
      setMessages((current) => current.slice(0, -1));
      setError(message(failure));
    } finally {
      setPending(false);
    }
  }

  function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = draft.trim();
    if (!question) return;
    setDraft("");
    void send(question);
  }

  /** Ends the current Conversation (if one started) and clears the chat. */
  function close(next: Phase) {
    if (token.current !== null) void endConversation(boot, token.current);
    forget();
    setMessages([]);
    setError(null);
    focusInput.current = next === "chat";
    setPhase(next);
  }

  if (phase === "retired") {
    return (
      <main className="widget">
        <p role="status">{NO_LONGER_AVAILABLE}</p>
      </main>
    );
  }

  return (
    <main className="widget">
      <header>
        <h1>{boot.name}</h1>
        {phase === "chat" && (
          <div className="controls">
            <button
              type="button"
              disabled={pending}
              onClick={() => {
                close("chat");
              }}
            >
              New chat
            </button>
            <button
              type="button"
              disabled={pending}
              onClick={() => {
                close("ended");
              }}
            >
              End chat
            </button>
          </div>
        )}
      </header>
      {phase === "loading" && <p role="status">Loading your chat…</p>}
      {phase === "ended" && (
        <div className="ended">
          <p role="status">You ended the chat.</p>
          <button
            type="button"
            onClick={() => {
              focusInput.current = true;
              setPhase("chat");
            }}
          >
            Start a new chat
          </button>
        </div>
      )}
      {phase === "chat" && (
        <>
          <ol role="log" aria-label="Conversation" className="messages">
            {messages.map((message, index) => (
              <li key={index} className={message.role} aria-label={message.role === "visitor" ? "You" : boot.name}>
                <p>{message.text}</p>
                {message.citations.length > 0 && (
                  <p className="sources">
                    Sources: {message.citations.map((citation) => citation.document_name ?? citation.label).join(", ")}
                  </p>
                )}
              </li>
            ))}
          </ol>
          {error && <p role="alert">{error}</p>}
          <form onSubmit={onSubmit}>
            <label htmlFor="message">Message</label>
            <textarea
              id="message"
              ref={input}
              rows={2}
              maxLength={4000}
              value={draft}
              onChange={(event) => {
                setDraft(event.target.value);
              }}
            />
            <button type="submit" disabled={pending}>
              {pending ? "Answering…" : "Send"}
            </button>
          </form>
        </>
      )}
    </main>
  );
}
