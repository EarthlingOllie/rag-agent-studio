import { ChatWindow, Composer, Launcher as LauncherButton, MessageBubble } from "@studio/ui";
import { useEffect, useRef, useState } from "react";

import { type Boot, type Citation, ChatError, type Launcher, ask, startConversation } from "./chat";
import { LAYOUT_MESSAGE, type Layout } from "./embed";

type Message = { role: "visitor" | "agent"; text: string; citations: Citation[] };

const GENERIC = "Something went wrong. Please try again.";

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

function Sources({ citations }: { citations: Citation[] }) {
  return (
    <div className="sources">
      Sources:{" "}
      {citations.map((citation, index) => (
        <details key={index}>
          <summary>{citation.document_name ?? citation.label}</summary>
          <blockquote>{citation.passage}</blockquote>
        </details>
      ))}
    </div>
  );
}

/**
 * The chat a Visitor sees inside the iframe, in the Organisation's Theme: the Agent's greeting
 * and starter questions, their questions and the Agent's streamed replies with expandable
 * sources. As a bubble it opens from a Launcher in the corner; inline it is always open. It
 * tells the host page (`host`, the only origin it posts to) how to size its frame.
 */
export function Widget({ boot, launcher, host = null }: { boot: Boot; launcher?: Launcher | null; host?: string | null }) {
  const type = launcher ?? boot.theme.launcher_type;
  const bubble = type === "bubble";
  const [open, setOpen] = useState(!bubble);
  const [messages, setMessages] = useState<Message[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The Conversation token, once the bootstrap token has been exchanged for one.
  const token = useRef<string | null>(null);
  const root = useRef<HTMLDivElement | null>(null);
  const opened = useRef(false);

  useEffect(() => {
    const target = hostOrigin(host);
    if (target && window.parent !== window) {
      const layout: Layout & { type: string } = { type: LAYOUT_MESSAGE, launcher: type, open, position: boot.theme.launcher_position };
      window.parent.postMessage(layout, target);
    }
    // Opening moves focus into the chat; closing returns it to the Launcher.
    if (!bubble) return;
    if (open) root.current?.querySelector<HTMLInputElement>('input[name="message"]')?.focus();
    else if (opened.current) root.current?.querySelector<HTMLButtonElement>(".launcher button")?.focus();
    opened.current ||= open;
  }, [open, type, bubble, host, boot.theme.launcher_position]);

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
      token.current ??= await startConversation(boot);
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
      // Drop the reply and whatever of it streamed before the failure.
      setMessages((current) => current.slice(0, -1));
      const unavailable = failure instanceof ChatError && failure.unavailable ? boot.ui_text.unavailable_message : null;
      setError(unavailable ?? (failure instanceof ChatError ? failure.message : GENERIC));
    } finally {
      setPending(false);
    }
  }

  function onSend(text: string) {
    const question = text.trim();
    if (question) void send(question);
  }

  const name = boot.name;
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
        <div className="panel">
          <ChatWindow
            className="chat"
            agentName={name}
            logoUrl={boot.logo_url}
            avatarUrl={boot.avatar_url}
            logLabel="Conversation"
            actions={
              bubble && (
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
              )
            }
            composer={
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
                <Composer
                  onSend={onSend}
                  disabled={pending}
                  sendLabel={pending ? "Answering…" : (boot.ui_text.send_button ?? "Send")}
                />
              </>
            }
          >
            {boot.greeting && (
              <MessageBubble from="agent" label={`${name}'s greeting`}>
                {boot.greeting}
              </MessageBubble>
            )}
            {messages.map((message, index) => (
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
