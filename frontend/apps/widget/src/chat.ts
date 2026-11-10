/**
 * The widget API, as the iframe calls it on its own origin (the API's, so no CORS): exchange the
 * shell's bootstrap token for a Conversation token, then send each question with it and read
 * the answer as it streams back as Server-Sent Events.
 */
import type { Schemas } from "@studio/api-client";

export type Launcher = "bubble" | "inline";

/**
 * What the shell hands the widget, in its `#widget-boot` element: the Agent, a bootstrap token,
 * the Theme's mode and Launcher (its colours are already inlined as CSS custom properties), the
 * images, and the public Experience of the Agent's Live Version.
 */
export type Boot = {
  agent: string;
  name: string;
  bootstrap_token: string;
  theme: {
    mode: "light" | "dark" | "auto";
    launcher_type: Launcher;
    launcher_position: "bottom-right" | "bottom-left";
    font: string;
  };
  logo_url: string | null;
  avatar_url: string | null;
  greeting: string;
  starter_questions: string[];
  ui_text: {
    send_button: string | null;
    rate_conversation: string | null;
    unavailable_message: string | null;
    searching_status: string | null;
  };
  citations: boolean;
  /** After how many replies the Visitor is asked to rate the Conversation; 0 asks only when they end the chat. */
  rating_prompt_after: number;
};

/** A source an answer cited; `passage` is the cited text, sent with a live answer but not with a resumed one. */
export type Citation = { label: string; document_name: string | null; passage?: string };

/**
 * Something the Visitor should be told instead of an answer; `status` is the API's, if any.
 * `unavailable` marks the Agent being temporarily unable to answer (a 503, a provider failure
 * mid-answer, or an `unavailable` event when a rate limit or the spent Token Budget refuses the
 * message), which the Agent's own text may replace.
 */
export class ChatError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly unavailable = status === 503,
  ) {
    super(message);
  }
}

/** What the API says once the Agent is archived or no longer has a Live Version. */
export const NO_LONGER_AVAILABLE = "This assistant is no longer available.";

const GENERIC = "Something went wrong. Please try again.";

async function refused(response: Response): Promise<ChatError> {
  try {
    const { detail } = (await response.json()) as { detail?: unknown };
    if (typeof detail === "string") return new ChatError(detail, response.status);
  } catch {
    // Not JSON: fall through to the generic message.
  }
  return new ChatError(GENERIC, response.status);
}

function base(boot: Boot): string {
  return `/api/widget/agents/${encodeURIComponent(boot.agent)}`;
}

function request(method: string, url: string, token?: string, body?: unknown): Promise<Response> {
  const init: RequestInit & { headers: Record<string, string> } = { method, headers: {} };
  if (token) init.headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  return fetch(new URL(url, window.location.origin), init);
}

function exchange(boot: Boot, bootstrapToken: string): Promise<Response> {
  const body: Schemas["StartConversationRequest"] = { bootstrap_token: bootstrapToken };
  return request("POST", `${base(boot)}/conversations`, undefined, body);
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
  /** An Agentic Agent started a Knowledge Search; the widget is never told its query. */
  onSearch: () => void;
  onToken: (text: string) => void;
  onCitation: (citation: Citation) => void;
  onReplace: (text: string) => void;
  /** The input Guardrail blocked the message: the Agent's refusal text is the whole reply. */
  onRefusal: (text: string) => void;
};

/** Asks the Agent's Live Version; resolves with the reply's Message ID once the answer is complete. */
export async function ask(boot: Boot, token: string, question: string, handlers: Handlers): Promise<string> {
  const body: Schemas["WidgetMessageRequest"] = { content: question };
  const response = await request("POST", `${base(boot)}/messages`, token, body);
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
      const data = JSON.parse(fields.data) as { text: string; message: string; passage: string; message_id: string } & Citation;
      switch (fields.event) {
        case "search":
          handlers.onSearch();
          break;
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
          handlers.onCitation({ label: data.label, document_name: data.document_name, passage: data.passage });
          break;
        // A provider failure, or admission control refusing the message (a rate limit): the
        // Agent's unavailable text.
        case "error":
        case "unavailable":
          throw new ChatError(data.message, undefined, true);
        case "done":
          return data.message_id;
      }
    }
  }
}

export type ResumedMessage = Schemas["WidgetMessageOut"];
export type Resumed = Schemas["WidgetConversationOut"];

/**
 * The token's Conversation, for a Visitor who has come back: its Messages and its Conversation
 * Rating; null when the token is no longer accepted (24 hours without activity, or the
 * Conversation was ended).
 */
export async function resume(boot: Boot, token: string): Promise<Resumed | null> {
  const response = await request("GET", `${base(boot)}/conversation`, token);
  if (response.status === 401) return null;
  if (!response.ok) throw await refused(response);
  return (await response.json()) as Resumed;
}

/** Ends the token's Conversation. Best effort: the widget forgets the token either way. */
export async function endConversation(boot: Boot, token: string): Promise<void> {
  try {
    await request("DELETE", `${base(boot)}/conversation`, token);
  } catch {
    // Unreachable: the token is forgotten anyway and expires in 24 hours.
  }
}

/** A Visitor's thumbs on one of the Agent's replies, with an optional comment (Message Feedback). */
export type Feedback = Schemas["MessageFeedbackOut"];

function feedbackUrl(boot: Boot, messageId: string): string {
  return `${base(boot)}/messages/${encodeURIComponent(messageId)}/feedback`;
}

/** Gives (or replaces) the Visitor's feedback on a reply; resolves with it as saved. */
export async function giveFeedback(boot: Boot, token: string, messageId: string, feedback: Schemas["MessageFeedbackIn"]): Promise<Feedback> {
  const response = await request("PUT", feedbackUrl(boot, messageId), token, feedback);
  if (!response.ok) throw await refused(response);
  return (await response.json()) as Feedback;
}

/** Removes the Visitor's feedback on a reply. */
export async function removeFeedback(boot: Boot, token: string, messageId: string): Promise<void> {
  const response = await request("DELETE", feedbackUrl(boot, messageId), token);
  if (!response.ok) throw await refused(response);
}

/** The Visitor's Conversation Rating (null until they rate) and whether they dismissed the rating prompt. */
export type Rating = Schemas["WidgetRatingOut"];

function ratingUrl(boot: Boot): string {
  return `${base(boot)}/conversation/rating`;
}

/** Rates the token's Conversation from 1 to 5, or changes its rating; resolves with it as saved. */
export async function rateConversation(boot: Boot, token: string, score: number): Promise<Rating> {
  const body: Schemas["ConversationRatingIn"] = { score };
  const response = await request("PUT", ratingUrl(boot), token, body);
  if (!response.ok) throw await refused(response);
  return (await response.json()) as Schemas["ConversationRatingOut"];
}

/** Saves that the Visitor dismissed the rating prompt. Best effort: the widget hides it either way. */
export async function dismissRatingPrompt(boot: Boot, token: string): Promise<void> {
  try {
    await request("POST", `${ratingUrl(boot)}/dismissal`, token);
  } catch {
    // Unreachable: the prompt stays hidden in this page anyway.
  }
}
