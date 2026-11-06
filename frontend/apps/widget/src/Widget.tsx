import { type SubmitEvent, useRef, useState } from "react";

import { type Boot, type Citation, ChatError, ask, startConversation } from "./chat";

type Message = { role: "visitor" | "agent"; text: string; citations: Citation[] };

/** The chat a Visitor sees inside the iframe: their questions and the Agent's streamed replies. */
export function Widget({ boot }: { boot: Boot }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The Conversation token, once the bootstrap token has been exchanged for one.
  const token = useRef<string | null>(null);

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
      setError(failure instanceof ChatError ? failure.message : "Something went wrong. Please try again.");
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

  return (
    <main className="widget">
      <h1>{boot.name}</h1>
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
    </main>
  );
}
