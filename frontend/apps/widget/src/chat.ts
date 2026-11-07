/**
 * The widget API, as the iframe calls it on its own origin (the API's, so no CORS): exchange the
 * shell's bootstrap token for a Conversation token, then send each question with it and read
 * the answer as it streams back as Server-Sent Events.
 */
import type { Schemas } from "@studio/api-client";

/** What the shell hands the widget, in its `#widget-boot` element. */
export type Boot = { agent: string; name: string; bootstrap_token: string };

export type Citation = { label: string; document_name: string | null };

/** Something the Visitor should be told instead of an answer. */
export class ChatError extends Error {}

const GENERIC = "Something went wrong. Please try again.";

async function refused(response: Response): Promise<ChatError> {
  try {
    const { detail } = (await response.json()) as { detail?: unknown };
    if (typeof detail === "string") return new ChatError(detail);
  } catch {
    // Not JSON: fall through to the generic message.
  }
  return new ChatError(GENERIC);
}

function base(boot: Boot): string {
  return `/api/widget/agents/${encodeURIComponent(boot.agent)}`;
}

function post(url: string, body: unknown, token?: string): Promise<Response> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(new URL(url, window.location.origin), { method: "POST", headers, body: JSON.stringify(body) });
}

function exchange(boot: Boot, bootstrapToken: string): Promise<Response> {
  const body: Schemas["StartConversationRequest"] = { bootstrap_token: bootstrapToken };
  return post(`${base(boot)}/conversations`, body);
}

/** A new bootstrap token from a fresh copy of the shell, or null when there is none. */
async function freshBootstrapToken(boot: Boot): Promise<string | null> {
  const response = await fetch(new URL(`/widget/a/${encodeURIComponent(boot.agent)}`, window.location.origin));
  if (!response.ok) return null;
  const page = new DOMParser().parseFromString(await response.text(), "text/html");
  const data = page.getElementById("widget-boot")?.textContent;
  return data ? (JSON.parse(data) as Boot).bootstrap_token : null;
}

/**
 * Starts the Visitor's Conversation; returns its Conversation token. The shell's bootstrap
 * token lasts 15 minutes, so a Visitor who waits longer before asking gets a fresh one from
 * the shell and the exchange is tried once more.
 */
export async function startConversation(boot: Boot): Promise<string> {
  let response = await exchange(boot, boot.bootstrap_token);
  if (response.status === 401) {
    const fresh = await freshBootstrapToken(boot);
    if (fresh) response = await exchange(boot, fresh);
  }
  if (!response.ok) throw await refused(response);
  return ((await response.json()) as Schemas["ConversationTokenOut"]).conversation_token;
}

export type Handlers = {
  onToken: (text: string) => void;
  onCitation: (citation: Citation) => void;
  onReplace: (text: string) => void;
  /** The input Guardrail blocked the message: the Agent's refusal text is the whole reply. */
  onRefusal: (text: string) => void;
};

/** Asks the Agent's Live Version; resolves once the answer is complete. */
export async function ask(boot: Boot, token: string, question: string, handlers: Handlers): Promise<void> {
  const body: Schemas["WidgetMessageRequest"] = { content: question };
  const response = await post(`${base(boot)}/messages`, body, token);
  if (!response.ok || !response.body) throw await refused(response);
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffered = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) throw new ChatError(GENERIC);
    buffered += value;
    let end = buffered.indexOf("\n\n");
    while (end !== -1) {
      const block = buffered.slice(0, end);
      buffered = buffered.slice(end + 2);
      end = buffered.indexOf("\n\n");
      const fields = Object.fromEntries(
        block.split("\n").map((line) => [line.slice(0, line.indexOf(": ")), line.slice(line.indexOf(": ") + 2)]),
      ) as { event: string; data: string };
      const data = JSON.parse(fields.data) as { text: string; message: string } & Citation;
      switch (fields.event) {
        case "token":
          handlers.onToken(data.text);
          break;
        case "replace":
          handlers.onReplace(data.text);
          break;
        case "refusal":
          handlers.onRefusal(data.text);
          break;
        case "citation":
          handlers.onCitation({ label: data.label, document_name: data.document_name });
          break;
        case "error":
          throw new ChatError(data.message);
        case "done":
          return;
      }
    }
  }
}
