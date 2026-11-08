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
  rating_prompt_after: 0,
};

const STORED = "rag-widget:conversation:agt_hr";
const FAILED = "Your feedback couldn't be saved. Please try again.";
const EXPIRED = "This chat has expired. Reload the page to start a new one.";

type Feedback = { rating: "up" | "down"; comment: string | null };
type Seen = { method: string; message: string; body?: unknown; authorization: string | null };

function sse(text: string, messageId: string): Response {
  return new HttpResponse(
    `event: token\ndata: ${JSON.stringify({ text })}\n\nevent: done\ndata: ${JSON.stringify({ message_id: messageId })}\n\n`,
    { headers: { "Content-Type": "text/event-stream" } },
  );
}

/**
 * The widget API: each answer gets the next reply ID (r1, r2, …), and feedback is kept per reply
 * like the API does. `refuse` answers feedback requests with that status instead.
 */
function fakeWidgetApi({ history, refuse }: { history?: unknown[]; refuse?: number } = {}) {
  const seen: Seen[] = [];
  const kept = new Map<string, Feedback>();
  let replies = 0;
  const feedback = "*/api/widget/agents/agt_hr/messages/:messageId/feedback";
  const refusal = () =>
    HttpResponse.json({ detail: refuse === 401 ? EXPIRED : "There is no such reply in this chat." }, { status: refuse ?? 500 });
  server.use(
    http.post("*/api/widget/agents/agt_hr/conversations", () =>
      HttpResponse.json({ conversation_token: "wc1.token" }, { status: 201 }),
    ),
    http.get("*/api/widget/agents/agt_hr/conversation", () => HttpResponse.json({ messages: history ?? [], rating: { score: null, prompt_dismissed: false } })),
    http.post("*/api/widget/agents/agt_hr/messages", async ({ request }) => {
      const { content } = (await request.json()) as { content: string };
      replies += 1;
      return sse(`Re: ${content}`, `r${String(replies)}`);
    }),
    http.put(feedback, async ({ request, params }) => {
      const body = (await request.json()) as { rating: "up" | "down"; comment?: string | null };
      const message = String(params.messageId);
      seen.push({ method: "PUT", message, body, authorization: request.headers.get("Authorization") });
      if (refuse) return refusal();
      const given = { rating: body.rating, comment: body.comment?.trim() || null };
      kept.set(message, given);
      return HttpResponse.json(given);
    }),
    http.delete(feedback, ({ request, params }) => {
      const message = String(params.messageId);
      seen.push({ method: "DELETE", message, authorization: request.headers.get("Authorization") });
      if (refuse) return refusal();
      kept.delete(message);
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return { seen, kept };
}

async function ask(question: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Message"), question);
  await user.click(screen.getByRole("button", { name: "Send" }));
  return (await screen.findByText(`Re: ${question}`)).closest("li") as HTMLElement;
}

function thumbs(reply: HTMLElement) {
  const group = within(reply).getByRole("group", { name: "Was this reply helpful?" });
  return {
    group,
    up: within(group).getByRole("button", { name: "Helpful" }),
    down: within(group).getByRole("button", { name: "Not helpful" }),
  };
}

beforeEach(() => {
  localStorage.clear();
});

test("a Visitor gives a reply a thumbs up, and only replies offer thumbs", async () => {
  const { seen } = fakeWidgetApi();
  render(<Widget boot={boot} />);

  const reply = await ask("How much leave?");
  const { up, down } = thumbs(reply);
  expect(up).toHaveAttribute("aria-pressed", "false");
  expect(down).toHaveAttribute("aria-pressed", "false");
  expect(within(screen.getByRole("listitem", { name: "You" })).queryByRole("group")).not.toBeInTheDocument();

  await userEvent.click(up);

  expect(up).toHaveAttribute("aria-pressed", "true");
  expect(down).toHaveAttribute("aria-pressed", "false");
  expect(await within(reply).findByRole("status")).toHaveTextContent("Thanks for your feedback.");
  expect(seen).toEqual([{ method: "PUT", message: "r1", body: { rating: "up", comment: null }, authorization: "Bearer wc1.token" }]);
});

test("a Visitor gives a thumbs down with a comment, edits the comment, and changes their mind", async () => {
  const { seen, kept } = fakeWidgetApi();
  render(<Widget boot={boot} />);
  const reply = await ask("How much leave?");
  const { down, up } = thumbs(reply);

  await userEvent.click(down);
  await userEvent.click(within(reply).getByRole("button", { name: "Add a comment" }));
  const comment = within(reply).getByRole("textbox", { name: "Comment (optional)" });
  expect(comment).toHaveFocus();
  await userEvent.type(comment, "It's 30 days here.");
  await userEvent.click(within(reply).getByRole("button", { name: "Save comment" }));

  expect(await within(reply).findByText("“It's 30 days here.”")).toBeInTheDocument();
  expect(within(reply).queryByRole("textbox")).not.toBeInTheDocument();
  expect(kept.get("r1")).toEqual({ rating: "down", comment: "It's 30 days here." });

  // Editing starts from the saved comment; Cancel leaves it as it was.
  await userEvent.click(within(reply).getByRole("button", { name: "Edit comment" }));
  const editing = within(reply).getByRole("textbox", { name: "Comment (optional)" });
  expect(editing).toHaveValue("It's 30 days here.");
  await userEvent.clear(editing);
  await userEvent.type(editing, "Never mind");
  await userEvent.click(within(reply).getByRole("button", { name: "Cancel" }));
  expect(within(reply).getByText("“It's 30 days here.”")).toBeInTheDocument();

  // Switching the thumbs keeps the comment.
  await userEvent.click(up);
  expect(up).toHaveAttribute("aria-pressed", "true");
  expect(down).toHaveAttribute("aria-pressed", "false");
  expect(kept.get("r1")).toEqual({ rating: "up", comment: "It's 30 days here." });

  // Clearing the comment removes it but keeps the thumbs.
  await userEvent.click(within(reply).getByRole("button", { name: "Edit comment" }));
  await userEvent.clear(within(reply).getByRole("textbox", { name: "Comment (optional)" }));
  await userEvent.click(within(reply).getByRole("button", { name: "Save comment" }));
  expect(await within(reply).findByRole("button", { name: "Add a comment" })).toBeInTheDocument();
  expect(kept.get("r1")).toEqual({ rating: "up", comment: null });
  expect(seen.map((s) => [s.method, s.body])).toEqual([
    ["PUT", { rating: "down", comment: null }],
    ["PUT", { rating: "down", comment: "It's 30 days here." }],
    ["PUT", { rating: "up", comment: "It's 30 days here." }],
    ["PUT", { rating: "up", comment: "" }],
  ]);
});

test("pressing the chosen thumb again removes the feedback, comment and all", async () => {
  const { seen, kept } = fakeWidgetApi();
  render(<Widget boot={boot} />);
  const reply = await ask("How much leave?");
  const { down } = thumbs(reply);
  await userEvent.click(down);
  await userEvent.click(within(reply).getByRole("button", { name: "Add a comment" }));
  await userEvent.type(within(reply).getByRole("textbox", { name: "Comment (optional)" }), "Wrong");
  await userEvent.click(within(reply).getByRole("button", { name: "Save comment" }));
  await within(reply).findByText("“Wrong”");

  await userEvent.click(down);

  expect(down).toHaveAttribute("aria-pressed", "false");
  expect(await within(reply).findByRole("status")).toHaveTextContent("Feedback removed.");
  expect(within(reply).queryByText("“Wrong”")).not.toBeInTheDocument();
  expect(within(reply).queryByRole("button", { name: /comment/ })).not.toBeInTheDocument();
  expect(kept.has("r1")).toBe(false);
  expect(seen.at(-1)).toEqual({ method: "DELETE", message: "r1", authorization: "Bearer wc1.token" });
});

test("each reply takes its own feedback", async () => {
  const { kept } = fakeWidgetApi();
  render(<Widget boot={boot} />);
  const first = await ask("One");
  const second = await ask("Two");

  await userEvent.click(thumbs(first).up);
  await userEvent.click(thumbs(second).down);

  expect(thumbs(first).up).toHaveAttribute("aria-pressed", "true");
  expect(thumbs(second).down).toHaveAttribute("aria-pressed", "true");
  expect(Object.fromEntries(kept)).toEqual({ r1: { rating: "up", comment: null }, r2: { rating: "down", comment: null } });
});

test("a Visitor who comes back sees the feedback they gave, and can change it", async () => {
  localStorage.setItem(STORED, "wc1.kept");
  const { seen } = fakeWidgetApi({
    history: [
      { id: "q1", role: "user", content: "How much leave?", citations: [], feedback: null },
      { id: "a1", role: "assistant", content: "Twenty-five days.", citations: [], feedback: { rating: "down", comment: "Too vague" } },
      { id: "q2", role: "user", content: "Thanks", citations: [], feedback: null },
      { id: "a2", role: "assistant", content: "You're welcome.", citations: [], feedback: null },
    ],
  });
  render(<Widget boot={boot} />);

  const first = (await screen.findByText("Twenty-five days.")).closest("li") as HTMLElement;
  const second = screen.getByText("You're welcome.").closest("li") as HTMLElement;
  expect(thumbs(first).down).toHaveAttribute("aria-pressed", "true");
  expect(within(first).getByText("“Too vague”")).toBeInTheDocument();
  expect(thumbs(second).up).toHaveAttribute("aria-pressed", "false");
  expect(thumbs(second).down).toHaveAttribute("aria-pressed", "false");

  await userEvent.click(thumbs(first).up);

  expect(seen).toEqual([{ method: "PUT", message: "a1", body: { rating: "up", comment: "Too vague" }, authorization: "Bearer wc1.kept" }]);
});

test("a reply still streaming, or one that failed, offers no thumbs", async () => {
  let finish: (() => void) | undefined;
  fakeWidgetApi();
  server.use(
    http.post("*/api/widget/agents/agt_hr/messages", () => {
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(new TextEncoder().encode(`event: token\ndata: {"text":"Thinking"}\n\n`));
          finish = () => {
            controller.enqueue(new TextEncoder().encode(`event: done\ndata: {"message_id":"r9"}\n\n`));
            controller.close();
          };
        },
      });
      return new HttpResponse(body, { headers: { "Content-Type": "text/event-stream" } });
    }),
  );
  render(<Widget boot={boot} />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Message"), "Hello");
  await user.click(screen.getByRole("button", { name: "Send" }));

  const reply = (await screen.findByText("Thinking")).closest("li") as HTMLElement;
  expect(within(reply).queryByRole("group")).not.toBeInTheDocument();
  finish?.();
  expect(await within(reply).findByRole("group", { name: "Was this reply helpful?" })).toBeInTheDocument();
});

test.each([
  [404, FAILED],
  [401, EXPIRED],
])("feedback the API refuses (%i) is undone and the Visitor told", async (status, shown) => {
  fakeWidgetApi({ refuse: status });
  render(<Widget boot={boot} />);
  const reply = await ask("How much leave?");
  const { up } = thumbs(reply);

  await userEvent.click(up);

  expect(await within(reply).findByRole("alert")).toHaveTextContent(shown);
  expect(up).toHaveAttribute("aria-pressed", "false");
});

test("a removal the API refuses keeps the feedback and tells the Visitor", async () => {
  localStorage.setItem(STORED, "wc1.kept");
  fakeWidgetApi({
    refuse: 404,
    history: [
      { id: "q1", role: "user", content: "Hi", citations: [], feedback: null },
      { id: "a1", role: "assistant", content: "Hello!", citations: [], feedback: { rating: "up", comment: null } },
    ],
  });
  render(<Widget boot={boot} />);
  const reply = (await screen.findByText("Hello!")).closest("li") as HTMLElement;

  await userEvent.click(thumbs(reply).up);

  expect(await within(reply).findByRole("alert")).toHaveTextContent(FAILED);
  expect(thumbs(reply).up).toHaveAttribute("aria-pressed", "true");
});

test("a comment the API refuses stays in the box to try again", async () => {
  localStorage.setItem(STORED, "wc1.kept");
  fakeWidgetApi({
    refuse: 404,
    history: [{ id: "a1", role: "assistant", content: "Hello!", citations: [], feedback: { rating: "down", comment: null } }],
  });
  render(<Widget boot={boot} />);
  const reply = (await screen.findByText("Hello!")).closest("li") as HTMLElement;
  await userEvent.click(within(reply).getByRole("button", { name: "Add a comment" }));
  await userEvent.type(within(reply).getByRole("textbox", { name: "Comment (optional)" }), "Rude");

  await userEvent.click(within(reply).getByRole("button", { name: "Save comment" }));

  expect(await within(reply).findByRole("alert")).toHaveTextContent(FAILED);
  expect(within(reply).getByRole("textbox", { name: "Comment (optional)" })).toHaveValue("Rude");
});

test("feedback that can't reach the API at all is undone", async () => {
  fakeWidgetApi();
  server.use(http.put("*/api/widget/agents/agt_hr/messages/:messageId/feedback", () => HttpResponse.error()));
  render(<Widget boot={boot} />);
  const reply = await ask("How much leave?");

  await userEvent.click(thumbs(reply).down);

  expect(await within(reply).findByRole("alert")).toHaveTextContent(FAILED);
  expect(thumbs(reply).down).toHaveAttribute("aria-pressed", "false");
});

test("the comment box is limited to the API's 1000 characters", async () => {
  fakeWidgetApi();
  render(<Widget boot={boot} />);
  const reply = await ask("How much leave?");
  await userEvent.click(thumbs(reply).down);
  await userEvent.click(within(reply).getByRole("button", { name: "Add a comment" }));

  expect(within(reply).getByRole("textbox", { name: "Comment (optional)" })).toHaveAttribute("maxlength", "1000");
});

test("after the chat expires, an earlier reply's thumbs say so instead of sending anything", async () => {
  const { seen } = fakeWidgetApi();
  render(<Widget boot={boot} />);
  const reply = await ask("How much leave?");
  server.use(http.post("*/api/widget/agents/agt_hr/messages", () => HttpResponse.json({ detail: EXPIRED }, { status: 401 })));
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Message"), "And sick days?");
  await user.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText(EXPIRED);

  await userEvent.click(thumbs(reply).up);

  expect(await within(reply).findByRole("alert")).toHaveTextContent(FAILED);
  expect(seen).toEqual([]);
});
