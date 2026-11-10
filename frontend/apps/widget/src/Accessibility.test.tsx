// WCAG 2.2 AA behaviour a keyboard or screen-reader Visitor relies on, through the widget's
// network seam: the Widget rendered as the iframe renders it, with the widget API faked by MSW.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../studio/src/test/server";
import type { Boot } from "./chat";
import { Widget } from "./Widget";

const boot: Boot = {
  agent: "agt_hr",
  name: "HR helper",
  bootstrap_token: "wb1.agt_hr.1.sig",
  theme: { mode: "light", launcher_type: "bubble", launcher_position: "bottom-right", font: "Inter" },
  logo_url: null,
  avatar_url: null,
  greeting: "Hi!",
  starter_questions: [],
  ui_text: { send_button: null, rate_conversation: null, unavailable_message: null, searching_status: null },
  citations: true,
  rating_prompt_after: 0,
};

beforeEach(() => {
  localStorage.clear();
});

test("a keyboard Visitor opens the bubble, Tab stays inside the chat, and closing returns focus to the Launcher", async () => {
  const user = userEvent.setup();
  render(<Widget boot={boot} />);

  await user.tab();
  expect(screen.getByRole("button", { name: "Open chat" })).toHaveFocus();
  await user.keyboard("{Enter}");

  const chat = screen.getByRole("region", { name: "Chat with HR helper" });
  expect(within(chat).getByLabelText("Message")).toHaveFocus();
  await user.tab();
  expect(within(chat).getByRole("button", { name: "Send" })).toHaveFocus();
  // Past the last control focus wraps to the first, never out to the Launcher.
  await user.tab();
  expect(within(chat).getByRole("button", { name: "New chat" })).toHaveFocus();
  await user.tab({ shift: true });
  expect(within(chat).getByRole("button", { name: "Send" })).toHaveFocus();
  await user.tab();
  await user.tab();
  await user.tab();
  expect(within(chat).getByRole("button", { name: "Close chat" })).toHaveFocus();

  await user.keyboard("{Enter}");

  expect(screen.queryByRole("region", { name: "Chat with HR helper" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Open chat", expanded: false })).toHaveFocus();

  // Space opens it too, and Escape closes it from anywhere inside.
  await user.keyboard(" ");
  expect(screen.getByLabelText("Message")).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(screen.getByRole("button", { name: "Open chat" })).toHaveFocus();
});

/** A reply stream the test feeds event by event. */
function controlledReply() {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  server.use(
    http.post("*/api/widget/agents/agt_hr/conversations", () => HttpResponse.json({ conversation_token: "wc1.t" }, { status: 201 })),
    http.post("*/api/widget/agents/agt_hr/messages", () => new HttpResponse(body, { headers: { "Content-Type": "text/event-stream" } })),
  );
  return {
    send(event: string, data: unknown) {
      controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
    },
    end() {
      controller.close();
    },
  };
}

test("a screen reader hears each reply once, when it is complete, not token by token", async () => {
  const user = userEvent.setup();
  const reply = controlledReply();
  render(<Widget boot={boot} launcher="inline" />);
  const announcements = screen.getByRole("status", { name: "Announcements" });
  // The Conversation is a log for reading back, but it is not live: tokens would be read out one by one.
  expect(screen.getByRole("log", { name: "Conversation" })).toHaveAttribute("aria-live", "off");
  expect(announcements).toHaveAttribute("aria-live", "polite");

  await user.type(screen.getByLabelText("Message"), "How much leave?{Enter}");
  reply.send("token", { text: "Twenty-five " });
  expect(await screen.findByText("Twenty-five")).toBeInTheDocument();
  expect(announcements).toBeEmptyDOMElement();

  reply.send("token", { text: "days." });
  reply.send("done", { message_id: "m1" });
  reply.end();

  expect(await within(announcements).findByText("HR helper: Twenty-five days.")).toBeInTheDocument();
  expect(announcements).not.toHaveTextContent("How much leave?");
});

test("while an Agentic Agent searches the Visitor sees a status, announced once per reply, until the answer streams", async () => {
  const user = userEvent.setup();
  const reply = controlledReply();
  render(<Widget boot={boot} launcher="inline" />);
  const announcements = screen.getByRole("status", { name: "Announcements" });
  const log = screen.getByRole("log", { name: "Conversation" });

  await user.type(screen.getByLabelText("Message"), "How much leave?{Enter}");
  reply.send("search", {});

  const answer = await within(log).findByRole("listitem", { name: "HR helper" });
  expect(await within(answer).findByText("Searching the knowledge base…")).toBeInTheDocument();
  const announced = await within(announcements).findByText("Searching the knowledge base…");
  // A second Search in the same reply keeps the status and is not announced again.
  reply.send("search", {});
  reply.send("search", {});
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(within(answer).getByText("Searching the knowledge base…")).toBeInTheDocument();
  expect(within(announcements).getByText("Searching the knowledge base…")).toBe(announced);
  expect(announcements.childElementCount).toBe(1);

  // The answer replaces the status as soon as it starts streaming.
  reply.send("token", { text: "Twenty-five days." });
  expect(await within(answer).findByText("Twenty-five days.")).toBeInTheDocument();
  expect(within(answer).queryByText("Searching the knowledge base…")).not.toBeInTheDocument();
  reply.send("done", { message_id: "m1" });
  reply.end();
  expect(await within(announcements).findByText("HR helper: Twenty-five days.")).toBeInTheDocument();
});

test("each reply that searches announces the status again", async () => {
  const user = userEvent.setup();
  server.use(
    http.post("*/api/widget/agents/agt_hr/conversations", () => HttpResponse.json({ conversation_token: "wc1.t" }, { status: 201 })),
    http.post("*/api/widget/agents/agt_hr/messages", () => {
      // The Search, then a moment later (as the model reads what it found) the answer.
      const encoder = new TextEncoder();
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(encoder.encode("event: search\ndata: {}\n\n"));
          setTimeout(() => {
            controller.enqueue(encoder.encode('event: token\ndata: {"text":"Yes."}\n\nevent: done\ndata: {"message_id":"m"}\n\n'));
            controller.close();
          }, 50);
        },
      });
      return new HttpResponse(body, { headers: { "Content-Type": "text/event-stream" } });
    }),
  );
  render(<Widget boot={boot} launcher="inline" />);
  const announcements = screen.getByRole("status", { name: "Announcements" });
  const said: string[] = [];
  new MutationObserver((records) => {
    for (const record of records) for (const node of record.addedNodes) said.push(node.textContent ?? "");
  }).observe(announcements, { childList: true });

  await user.type(screen.getByLabelText("Message"), "One{Enter}");
  await within(announcements).findByText("HR helper: Yes.");
  await user.type(screen.getByLabelText("Message"), "Two{Enter}");
  await waitFor(() => {
    expect(said).toHaveLength(4);
  });

  expect(said).toEqual(["Searching the knowledge base…", "HR helper: Yes.", "Searching the knowledge base…", "HR helper: Yes."]);
});

test("the same reply twice is announced twice, and a failed reply is left to the alert", async () => {
  const user = userEvent.setup();
  server.use(
    http.post("*/api/widget/agents/agt_hr/conversations", () => HttpResponse.json({ conversation_token: "wc1.t" }, { status: 201 })),
    http.post("*/api/widget/agents/agt_hr/messages", async ({ request }) => {
      const { content } = (await request.json()) as { content: string };
      if (content === "Break") return HttpResponse.json({ detail: "Not now." }, { status: 503 });
      return new HttpResponse('event: token\ndata: {"text":"Yes."}\n\nevent: done\ndata: {"message_id":"m"}\n\n', {
        headers: { "Content-Type": "text/event-stream" },
      });
    }),
  );
  render(<Widget boot={boot} launcher="inline" />);
  const announcements = screen.getByRole("status", { name: "Announcements" });

  await user.type(screen.getByLabelText("Message"), "One{Enter}");
  const first = await within(announcements).findByText("HR helper: Yes.");
  await user.type(screen.getByLabelText("Message"), "Two{Enter}");
  expect(await screen.findAllByText("Yes.")).toHaveLength(2);
  // A new node with the same words: live regions announce additions, so it is read again.
  await waitFor(() => {
    expect(within(announcements).getByText("HR helper: Yes.")).not.toBe(first);
  });
  const second = within(announcements).getByText("HR helper: Yes.");

  await user.type(screen.getByLabelText("Message"), "Break{Enter}");
  expect(await screen.findByRole("alert")).toHaveTextContent("Not now.");
  expect(within(announcements).getByText("HR helper: Yes.")).toBe(second);
});

function prefersReducedMotion(reduce: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: reduce && query === "(prefers-reduced-motion: reduce)" }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test.each([
  [false, "smooth"],
  [true, "auto"],
])("with reduced motion %s the newest Message scrolls into view %s", async (reduce, behavior) => {
  prefersReducedMotion(reduce);
  const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
  const reply = controlledReply();
  render(<Widget boot={boot} launcher="inline" />);

  await userEvent.setup().type(screen.getByLabelText("Message"), "Hello{Enter}");
  reply.send("token", { text: "Hi there." });
  const answer = await screen.findByText("Hi there.");

  expect(scrolled).toHaveBeenLastCalledWith({ block: "end", behavior });
  expect(scrolled.mock.contexts.at(-1)).toBe(answer.closest("li"));
  reply.end();
});

test("the Conversation log holds a list of Messages, so each is announced as a list item", () => {
  render(<Widget boot={boot} launcher="inline" />);

  const log = screen.getByRole("log", { name: "Conversation" });
  const list = within(log).getByRole("list");
  expect(within(list).getByRole("listitem", { name: "HR helper's greeting" })).toHaveTextContent("Hi!");
});

test("the searching status override is what the reply shows and what is announced", async () => {
  const user = userEvent.setup();
  const reply = controlledReply();
  const ui_text = { ...boot.ui_text, searching_status: "Hana is looking that up…" };
  render(<Widget boot={{ ...boot, ui_text }} launcher="inline" />);
  const announcements = screen.getByRole("status", { name: "Announcements" });

  await user.type(screen.getByLabelText("Message"), "How much leave?{Enter}");
  reply.send("search", {});

  const answer = await within(screen.getByRole("log", { name: "Conversation" })).findByRole("listitem", { name: "HR helper" });
  expect(await within(answer).findByText("Hana is looking that up…")).toBeInTheDocument();
  expect(await within(announcements).findByText("Hana is looking that up…")).toBeInTheDocument();
  expect(screen.queryByText("Searching the knowledge base…")).not.toBeInTheDocument();
  reply.send("token", { text: "Twenty-five days." });
  reply.send("done", { message_id: "m1" });
  reply.end();
  expect(await within(announcements).findByText("HR helper: Twenty-five days.")).toBeInTheDocument();
});
