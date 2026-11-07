import { ChatWindow, Composer, Launcher as LauncherButton, MessageBubble } from "@studio/ui";
import { type KeyboardEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import {
  type Boot,
  type Citation,
  ChatError,
  type Launcher,
  NO_LONGER_AVAILABLE,
  ask,
  endConversation,
  resume,
  startConversation,
} from "./chat";
import { LAYOUT_MESSAGE, type Layout } from "./embed";
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

/** What Tab can reach inside the open chat. */
const FOCUSABLE = 'button:not([disabled]), input:not([disabled]), summary, a[href], [tabindex]:not([tabindex="-1"])';

/**
 * Keeps Tab inside `panel` while the bubble is open: past the last control focus wraps to the
 * first, and Shift+Tab before the first wraps to the last.
 */
function trapFocus(event: KeyboardEvent<HTMLElement>) {
  if (event.key !== "Tab") return;
  const focusable = [...event.currentTarget.querySelectorAll<HTMLElement>(FOCUSABLE)];
  const first = focusable[0];
  const last = focusable.at(-1);
  const active = document.activeElement;
  if (event.shiftKey ? active === first : active === last) {
    event.preventDefault();
    ((event.shiftKey ? last : first) as HTMLElement).focus();
  }
}

function message(failure: unknown): string {
  return failure instanceof ChatError ? failure.message : GENERIC;
}

/** The host page's origin, from the frame's address, if it is one; layout goes only there. */
export function hostOrigin(host: string | null): string | null {
  if (!host) return null;
  try {
    const url = new URL(host);
    return /^https?:$/.test(url.protocol) && url.origin === host ? host : null;
  } catch {
    return null;
  }
}

/** An answer's sources; each expands to the passage it cited, when the widget was sent one. */
function Sources({ citations }: { citations: Citation[] }) {
  return (
    <div className="sources">
      Sources:{" "}
      {citations.map((citation, index) => {
        const name = citation.document_name ?? citation.label;
        return (
          <span key={index}>
            {index > 0 && ", "}
            {citation.passage === undefined ? (
              name
            ) : (
              <details>
                <summary>{name}</summary>
                <blockquote>{citation.passage}</blockquote>
              </details>
            )}
          </span>
        );
      })}
    </div>
  );
}

/**
 * The chat a Visitor sees inside the iframe, in the Organisation's Theme: the Agent's greeting
 * and starter questions, their questions and the Agent's streamed replies with expandable
 * sources. As a bubble it opens from a Launcher in the corner; inline it is always open. It
 * tells the host page (`host`, the only origin it posts to) how to size its frame. The
 * Conversation token is kept in the iframe's storage, so a Visitor who comes back resumes their
 * Conversation; they can start a new chat or end it.
 */
export function Widget({ boot, launcher, host = null }: { boot: Boot; launcher?: Launcher | null; host?: string | null }) {
  const type = launcher ?? boot.theme.launcher_type;
  const bubble = type === "bubble";
  const [open, setOpen] = useState(!bubble);
  const store = useMemo(() => tokenStore(boot.agent), [boot.agent]);
  const [phase, setPhase] = useState<Phase>(() => (store.load() ? "loading" : "chat"));
  const [messages, setMessages] = useState<Message[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The last completed reply, for screen readers; its `id` makes a repeated reply a new node.
  const [announcement, setAnnouncement] = useState<{ id: number; text: string } | null>(null);
  // The Conversation token, once the bootstrap token has been exchanged for one (or kept from
  // an earlier page load).
  const token = useRef<string | null>(null);
  const root = useRef<HTMLDivElement | null>(null);
  const opened = useRef(false);
  const focusInput = useRef(false);

  function messageBox() {
    return root.current?.querySelector<HTMLInputElement>('input[name="message"]');
  }

  useEffect(() => {
    const target = hostOrigin(host);
    if (target && window.parent !== window) {
      const layout: Layout & { type: string } = { type: LAYOUT_MESSAGE, launcher: type, open, position: boot.theme.launcher_position };
      window.parent.postMessage(layout, target);
    }
    // Opening moves focus into the chat; closing returns it to the Launcher.
    if (!bubble) return;
    if (open) messageBox()?.focus();
    else if (opened.current) root.current?.querySelector<HTMLButtonElement>(".launcher button")?.focus();
    opened.current ||= open;
  }, [open, type, bubble, host, boot.theme.launcher_position]);

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
    // Nothing to cancel on unmount: the widget is the iframe's whole page.
    void resume(boot, kept).then(
      (resumed) => {
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
  }, [boot, store]);

  useEffect(() => {
    if (focusInput.current && phase === "chat") {
      focusInput.current = false;
      messageBox()?.focus();
    }
  });

  // The newest Message scrolls into view as it arrives, without animation for Visitors who
  // prefer reduced motion.
  useEffect(() => {
    const newest = root.current?.querySelector("li[data-from]:last-of-type");
    if (!newest || messages.length === 0) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    newest.scrollIntoView({ block: "end", behavior: reduce ? "auto" : "smooth" });
  }, [messages]);

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
      let answer = "";
      await ask(boot, token.current, question, {
        onToken: (text) => {
          answer += text;
          updateReply((reply) => ({ ...reply, text: reply.text + text }));
        },
        onReplace: (text) => {
          answer = text;
          updateReply((reply) => ({ ...reply, text }));
        },
        onCitation: (citation) => {
          updateReply((reply) => ({ ...reply, citations: [...reply.citations, citation] }));
        },
      });
      setAnnouncement((last) => ({ id: (last?.id ?? 0) + 1, text: `${boot.name}: ${answer}` }));
    } catch (failure) {
      if (failure instanceof ChatError && failure.status === 404) {
        retire();
        return;
      }
      // An expired or ended token: the next question starts a new Conversation.
      if (failure instanceof ChatError && failure.status === 401) forget();
      // Drop the reply and whatever of it streamed before the failure.
      setMessages((current) => current.slice(0, -1));
      const unavailable = failure instanceof ChatError && failure.unavailable ? boot.ui_text.unavailable_message : null;
      setError(unavailable ?? message(failure));
    } finally {
      setPending(false);
    }
  }

  function onSend(text: string) {
    const question = text.trim();
    if (question) void send(question);
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

  const name = boot.name;
  const chatting = phase === "chat";
  let footer: ReactNode;
  if (phase === "retired") {
    footer = (
      <p role="status" className="notice">
        {NO_LONGER_AVAILABLE}
      </p>
    );
  } else if (phase === "loading") {
    footer = (
      <p role="status" className="notice">
        Loading your chat…
      </p>
    );
  } else if (phase === "ended") {
    footer = (
      <div className="notice ended">
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
    );
  } else {
    footer = (
      <>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {messages.length === 0 && boot.starter_questions.length > 0 && (
          <ul aria-label="Suggested questions" className="starters">
            {boot.starter_questions.map((question) => (
              <li key={question}>
                <button
                  type="button"
                  onClick={() => {
                    onSend(question);
                  }}
                >
                  {question}
                </button>
              </li>
            ))}
          </ul>
        )}
        <Composer onSend={onSend} disabled={pending} sendLabel={pending ? "Answering…" : (boot.ui_text.send_button ?? "Send")} />
      </>
    );
  }

  return (
    <div
      ref={root}
      className="widget"
      data-launcher={type}
      data-open={open}
      data-position={boot.theme.launcher_position}
      onKeyDown={(event) => {
        if (bubble && event.key === "Escape") setOpen(false);
      }}
    >
      {open && (
        <div className="panel" {...(bubble ? { onKeyDown: trapFocus } : {})}>
          <ChatWindow
            className="chat"
            agentName={name}
            logoUrl={boot.logo_url}
            avatarUrl={boot.avatar_url}
            {...(chatting
              ? { logLabel: "Conversation", announcements: announcement && <p key={announcement.id}>{announcement.text}</p> }
              : {})}
            actions={
              <>
                {chatting && (
                  <span className="controls">
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
                  </span>
                )}
                {bubble && (
                  <button
                    type="button"
                    className="close"
                    aria-label="Close chat"
                    onClick={() => {
                      setOpen(false);
                    }}
                  >
                    ×
                  </button>
                )}
              </>
            }
            composer={footer}
          >
            {chatting && boot.greeting && (
              <MessageBubble from="agent" label={`${name}'s greeting`}>
                {boot.greeting}
              </MessageBubble>
            )}
            {chatting &&
              messages.map((message, index) => (
                <MessageBubble key={index} from={message.role} label={message.role === "visitor" ? "You" : name}>
                  <p>{message.text}</p>
                  {boot.citations && message.citations.length > 0 && <Sources citations={message.citations} />}
                </MessageBubble>
              ))}
          </ChatWindow>
        </div>
      )}
      {bubble && (
        <span className="launcher">
          <LauncherButton
            open={open}
            position={boot.theme.launcher_position}
            onToggle={() => {
              setOpen((current) => !current);
            }}
          />
        </span>
      )}
    </div>
  );
}
