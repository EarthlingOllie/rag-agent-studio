/**
 * Network seam: the Conversation lifecycle in the widget. The Conversation token is kept in the
 * iframe's storage so a reload within 24 hours resumes the Conversation; a Visitor can start a
 * new one or end it; a retired Agent says so; and without storage the widget still chats.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../studio/src/test/server";
import type { Boot } from "./chat";
import { Widget } from "./Widget";

const boot: Boot = {
  agent: "agt_hr",
  name: "HR helper",
  bootstrap_token: "wb1.agt_hr.1.sig",
  theme: { mode: "light", launcher_type: "inline", launcher_position: "bottom-right", font: "Inter" },
  logo_url: null,
  avatar_url: null,
  greeting: "",
  starter_questions: [],
  ui_text: { send_button: null, rate_conversation: null, unavailable_message: null },
  citations: true,
};
const STORED = "rag-widget:conversation:agt_hr";
const RETIRED = "This assistant is no longer available.";
const EXPIRED = "This chat has expired. Reload the page to start a new one.";

type Seen = { route: string; authorization?: string | null };

function sse(text: string): Response {
  return new HttpResponse(`event: token\ndata: ${JSON.stringify({ text })}\n\nevent: done\ndata: {"message_id":"m"}\n\n`, {
    headers: { "Content-Type": "text/event-stream" },
  });
}

/** The widget API with one Conversation per exchange; `history` is what a resume returns. */
function fakeWidgetApi({
  history = () => HttpResponse.json({ messages: [] }),
  answer = (question: string) => sse(`Re: ${question}`),
  ended = () => new HttpResponse(null, { status: 204 }),
}: {
  history?: () => Response;
  answer?: ((question: string) => Response) | undefined;
  ended?: () => Response;
} = {}) {
  const seen: Seen[] = [];
  let issued = 0;
  server.use(
    http.post("*/api/widget/agents/agt_hr/conversations", () => {
      issued += 1;
      seen.push({ route: "start" });
      return HttpResponse.json({ conversation_token: `wc1.token${String(issued)}` }, { status: 201 });
    }),
    http.get("*/api/widget/agents/agt_hr/conversation", ({ request }) => {
      seen.push({ route: "resume", authorization: request.headers.get("Authorization") });
      return history();
    }),
    http.delete("*/api/widget/agents/agt_hr/conversation", ({ request }) => {
      seen.push({ route: "end", authorization: request.headers.get("Authorization") });
      return ended();
    }),
    http.post("*/api/widget/agents/agt_hr/messages", async ({ request }) => {
      const { content } = (await request.json()) as { content: string };
      seen.push({ route: "message", authorization: request.headers.get("Authorization") });
      return answer(content);
    }),
  );
  return seen;
}

async function ask(question: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Message"), question);
  await user.click(screen.getByRole("button", { name: "Send" }));
}

function log() {
  return screen.getByRole("log", { name: "Conversation" });
}

beforeEach(() => {
  localStorage.clear();
});

test("the Conversation token is kept in the iframe's storage once the chat starts", async () => {
  fakeWidgetApi();
  render(<Widget boot={boot} />);

  await ask("Hello");

  expect(await screen.findByText("Re: Hello")).toBeInTheDocument();
  expect(localStorage.getItem(STORED)).toBe("wc1.token1");
});

test("a Visitor who reloads gets their Conversation back, sources included, and carries on in it", async () => {
  localStorage.setItem(STORED, "wc1.kept");
  const seen = fakeWidgetApi({
    history: () =>
      HttpResponse.json({
        messages: [
          { role: "user", content: "How much leave?", citations: [] },
          {
            role: "assistant",
            content: "Twenty-five days [C1].",
            citations: [
              { label: "C1", document_name: "handbook.pdf" },
              { label: "C2", document_name: null },
            ],
          },
        ],
      }),
  });
  render(<Widget boot={boot} />);

  const reply = await screen.findByText("Twenty-five days [C1].");
  expect(within(log()).getByRole("listitem", { name: "You" })).toHaveTextContent("How much leave?");
  expect(reply.closest("li")).toHaveAccessibleName("HR helper");
  expect(reply.closest("li")).toHaveTextContent("Sources: handbook.pdf, C2");

  await ask("And sick days?");

  expect(await screen.findByText("Re: And sick days?")).toBeInTheDocument();
  expect(seen).toEqual([
    { route: "resume", authorization: "Bearer wc1.kept" },
    { route: "message", authorization: "Bearer wc1.kept" },
  ]);
});

test("a Conversation past its 24 hours is forgotten and the next question starts a new one", async () => {
  localStorage.setItem(STORED, "wc1.old");
  const seen = fakeWidgetApi({ history: () => HttpResponse.json({ detail: EXPIRED }, { status: 401 }) });
  render(<Widget boot={boot} />);

  expect(await screen.findByLabelText("Message")).toBeInTheDocument();
  expect(localStorage.getItem(STORED)).toBeNull();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(within(log()).queryAllByRole("listitem")).toEqual([]);

  await ask("Hello");

  expect(await screen.findByText("Re: Hello")).toBeInTheDocument();
  expect(seen.map((s) => s.route)).toEqual(["resume", "start", "message"]);
  expect(localStorage.getItem(STORED)).toBe("wc1.token1");
});

test("when the earlier messages can't be fetched, the Visitor is told and the Conversation carries on", async () => {
  localStorage.setItem(STORED, "wc1.kept");
  const seen = fakeWidgetApi({ history: () => new HttpResponse("Bad gateway", { status: 502 }) });
  render(<Widget boot={boot} />);

  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Please try again.");

  await ask("Still there?");

  expect(await screen.findByText("Re: Still there?")).toBeInTheDocument();
  expect(seen.at(-1)).toEqual({ route: "message", authorization: "Bearer wc1.kept" });
  expect(localStorage.getItem(STORED)).toBe("wc1.kept");
});

test("an Agent retired since the last visit shows the no longer available message", async () => {
  localStorage.setItem(STORED, "wc1.kept");
  fakeWidgetApi({ history: () => HttpResponse.json({ detail: RETIRED }, { status: 404 }) });
  render(<Widget boot={boot} />);

  expect(await screen.findByText(RETIRED)).toHaveAttribute("role", "status");
  expect(screen.queryByLabelText("Message")).not.toBeInTheDocument();
  expect(screen.queryByText("Loading your chat…")).not.toBeInTheDocument();
  expect(localStorage.getItem(STORED)).toBeNull();
});

test.each([
  ["when the chat starts", { answer: undefined, stored: false }],
  ["mid-Conversation", { answer: () => HttpResponse.json({ detail: RETIRED }, { status: 404 }), stored: true }],
])("an Agent retired %s shows the no longer available message instead of the chat", async (_, { answer, stored }) => {
  if (stored) localStorage.setItem(STORED, "wc1.kept");
  fakeWidgetApi({ answer });
  if (!stored) {
    server.use(http.post("*/api/widget/agents/agt_hr/conversations", () => HttpResponse.json({ detail: RETIRED }, { status: 404 })));
  }
  render(<Widget boot={boot} />);

  await ask("Hello");

  expect(await screen.findByRole("status")).toHaveTextContent(RETIRED);
  expect(screen.queryByRole("log")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
  expect(localStorage.getItem(STORED)).toBeNull();
});

test("an expired token mid-Conversation is forgotten, so the next question starts a new Conversation", async () => {
  let refuse = true;
  const seen = fakeWidgetApi({
    answer: (question) => {
      if (refuse) {
        refuse = false;
        return HttpResponse.json({ detail: EXPIRED }, { status: 401 });
      }
      return sse(`Re: ${question}`);
    },
  });
  localStorage.setItem(STORED, "wc1.kept");
  render(<Widget boot={boot} />);

  await ask("Hello");
  expect(await screen.findByRole("alert")).toHaveTextContent(EXPIRED);
  expect(localStorage.getItem(STORED)).toBeNull();
  await ask("Hello again");

  expect(await screen.findByText("Re: Hello again")).toBeInTheDocument();
  expect(seen.map((s) => s.route)).toEqual(["resume", "message", "start", "message"]);
  expect(seen.at(-1)?.authorization).toBe("Bearer wc1.token1");
});

test("a Visitor starts a new Conversation: the old one is ended and the next question starts afresh", async () => {
  const seen = fakeWidgetApi();
  render(<Widget boot={boot} />);
  const user = userEvent.setup();
  await ask("First topic");
  expect(await screen.findByText("Re: First topic")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "New chat" }));

  expect(within(log()).queryAllByRole("listitem")).toEqual([]);
  expect(screen.getByLabelText("Message")).toHaveFocus();
  expect(localStorage.getItem(STORED)).toBeNull();
  await ask("Second topic");
  expect(await screen.findByText("Re: Second topic")).toBeInTheDocument();
  expect(seen).toEqual([
    { route: "start" },
    { route: "message", authorization: "Bearer wc1.token1" },
    { route: "end", authorization: "Bearer wc1.token1" },
    { route: "start" },
    { route: "message", authorization: "Bearer wc1.token2" },
  ]);
  expect(localStorage.getItem(STORED)).toBe("wc1.token2");
});

test("a Visitor ends the chat, and can start another one afterwards", async () => {
  const seen = fakeWidgetApi();
  render(<Widget boot={boot} />);
  const user = userEvent.setup();
  await ask("Hello");
  expect(await screen.findByText("Re: Hello")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "End chat" }));

  expect(await screen.findByRole("status")).toHaveTextContent("You ended the chat.");
  expect(screen.queryByText("Re: Hello")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Message")).not.toBeInTheDocument();
  expect(localStorage.getItem(STORED)).toBeNull();
  expect(seen.at(-1)).toEqual({ route: "end", authorization: "Bearer wc1.token1" });

  await user.click(screen.getByRole("button", { name: "Start a new chat" }));
  expect(screen.getByLabelText("Message")).toHaveFocus();
  await ask("Back again");
  expect(await screen.findByText("Re: Back again")).toBeInTheDocument();
  expect(seen.slice(-2)).toEqual([{ route: "start" }, { route: "message", authorization: "Bearer wc1.token2" }]);
});

test("ending a chat that never started asks the API nothing", async () => {
  const seen = fakeWidgetApi();
  render(<Widget boot={boot} />);
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "End chat" }));

  expect(await screen.findByRole("status")).toHaveTextContent("You ended the chat.");
  expect(seen).toEqual([]);
});

test.each([
  ["refuses", () => HttpResponse.json({ detail: EXPIRED }, { status: 401 })],
  ["can't be reached", () => HttpResponse.error()],
])("when the API %s the end of a chat, the chat still ends in the widget", async (_, ended) => {
  localStorage.setItem(STORED, "wc1.kept");
  fakeWidgetApi({ ended });
  render(<Widget boot={boot} />);
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "End chat" }));

  expect(await screen.findByRole("status")).toHaveTextContent("You ended the chat.");
  expect(localStorage.getItem(STORED)).toBeNull();
});

test("the chat controls wait while an answer is coming", async () => {
  let finish: (response: Response) => void = () => undefined;
  fakeWidgetApi({ answer: () => new Promise<Response>((resolve) => { finish = resolve; }) as unknown as Response });
  render(<Widget boot={boot} />);

  await ask("Slow?");

  expect(await screen.findByRole("button", { name: "Answering…" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "New chat" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "End chat" })).toBeDisabled();
  finish(sse("Done."));
  expect(await screen.findByText("Done.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "End chat" })).toBeEnabled();
});

describe("when the browser blocks the iframe's storage", () => {
  beforeEach(() => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new DOMException("The operation is insecure.", "SecurityError");
    });
  });

  test("the widget still chats, without resume, and can start a new chat", async () => {
    const seen = fakeWidgetApi();
    render(<Widget boot={boot} />);
    const user = userEvent.setup();

    await ask("Hello");
    expect(await screen.findByText("Re: Hello")).toBeInTheDocument();
    await ask("Again");
    expect(await screen.findByText("Re: Again")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New chat" }));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(seen).toEqual([
      { route: "start" },
      { route: "message", authorization: "Bearer wc1.token1" },
      { route: "message", authorization: "Bearer wc1.token1" },
      { route: "end", authorization: "Bearer wc1.token1" },
    ]);
  });
});
