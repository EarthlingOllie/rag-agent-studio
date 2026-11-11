/**
 * Network seam: the Conversation Rating in the widget. The prompt appears after the Live
 * Version's Nth reply and on "End chat" when the Visitor hasn't rated; a dismissal is saved so
 * it doesn't come back in that Conversation; the rating can be changed. The widget API is faked
 * by MSW and keeps the rating like the API does.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../studio/src/test/server";
import type { Boot, Rating } from "./chat";
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
  ui_text: { send_button: null, rate_conversation: null, unavailable_message: null, searching_status: null },
  citations: true,
  rating_prompt_after: 2,
};

const STORED = "rag-widget:conversation:agt_hr";
const QUESTION = "How would you rate this chat?";
const FAILED = "Your rating couldn't be saved. Please try again.";
const EXPIRED = "This chat has expired. Reload the page to start a new one.";

type Seen = { route: string; body?: unknown; authorization: string | null };

function sse(text: string, messageId: string): Response {
  return new HttpResponse(
    `event: token\ndata: ${JSON.stringify({ text })}\n\nevent: done\ndata: ${JSON.stringify({ message_id: messageId })}\n\n`,
    { headers: { "Content-Type": "text/event-stream" } },
  );
}

/**
 * The widget API. `rating` is what a resume returns with `history`; `refuseRating` answers a
 * rating with that status (or a network error); `refuseAsk` answers questions after the first
 * with that status.
 */
function fakeWidgetApi({
  history = [],
  rating = { score: null, prompt_dismissed: false },
  refuseRating,
  refuseAsk,
}: { history?: unknown[]; rating?: Rating; refuseRating?: number | "network"; refuseAsk?: number } = {}) {
  const seen: Seen[] = [];
  let kept = rating;
  let replies = 0;
  server.use(
    http.post("*/api/widget/agents/agt_hr/conversations", () => HttpResponse.json({ conversation_token: "wc1.token" }, { status: 201 })),
    http.get("*/api/widget/agents/agt_hr/conversation", () => HttpResponse.json({ messages: history, rating: kept })),
    http.post("*/api/widget/agents/agt_hr/messages", async ({ request }) => {
      const { content } = (await request.json()) as { content: string };
      replies += 1;
      if (refuseAsk && replies > 1) return HttpResponse.json({ detail: EXPIRED }, { status: refuseAsk });
      return sse(`Re: ${content}`, `r${String(replies)}`);
    }),
    http.put("*/api/widget/agents/agt_hr/conversation/rating", async ({ request }) => {
      const body = (await request.json()) as { score: number };
      seen.push({ route: "rate", body, authorization: request.headers.get("Authorization") });
      if (refuseRating === "network") return HttpResponse.error();
      if (refuseRating) return HttpResponse.json({ detail: EXPIRED }, { status: refuseRating });
      kept = { ...kept, score: body.score };
      return HttpResponse.json(kept);
    }),
    http.post("*/api/widget/agents/agt_hr/conversation/rating/dismissal", ({ request }) => {
      seen.push({ route: "dismiss", authorization: request.headers.get("Authorization") });
      kept = { ...kept, prompt_dismissed: true };
      return new HttpResponse(null, { status: 204 });
    }),
    http.delete("*/api/widget/agents/agt_hr/conversation", ({ request }) => {
      seen.push({ route: "end", authorization: request.headers.get("Authorization") });
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return seen;
}

async function ask(question: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Message"), question);
  await user.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText(`Re: ${question}`);
}

function prompt() {
  return screen.queryByRole("group", { name: QUESTION });
}

function score(n: number) {
  return screen.getByRole("button", { name: `${String(n)} out of 5` });
}

const BEARER = "Bearer wc1.token";

beforeEach(() => {
  localStorage.clear();
});

test("the prompt appears after the Nth reply, and the Visitor rates the Conversation", async () => {
  const seen = fakeWidgetApi();
  render(<Widget boot={boot} />);

  await ask("How much leave?");
  expect(prompt()).not.toBeInTheDocument();
  await ask("And sick days?");

  const group = prompt() as HTMLElement;
  expect(within(group).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual([
    "1 out of 5",
    "2 out of 5",
    "3 out of 5",
    "4 out of 5",
    "5 out of 5",
  ]);
  expect(score(4)).toHaveAttribute("aria-pressed", "false");
  // The prompt doesn't take focus from where the Visitor is.
  expect(within(group).queryByRole("button", { name: "1 out of 5" })).not.toHaveFocus();

  await userEvent.click(score(4));

  expect(await screen.findByText(/You rated this chat 4 out of 5\./)).toBeInTheDocument();
  expect(screen.getByText("Thanks for rating this chat.")).toHaveAttribute("role", "status");
  expect(prompt()).not.toBeInTheDocument();
  expect(seen).toEqual([{ route: "rate", body: { score: 4 }, authorization: BEARER }]);
});

test("the prompt uses the Live Version's own wording when it has one", async () => {
  fakeWidgetApi();
  render(<Widget boot={{ ...boot, rating_prompt_after: 1, ui_text: { ...boot.ui_text, rate_conversation: "How did Hana do?" } }} />);

  await ask("How much leave?");

  expect(screen.getByRole("group", { name: "How did Hana do?" })).toBeInTheDocument();
});

test("a Visitor changes their rating, or thinks better of it", async () => {
  const seen = fakeWidgetApi();
  render(<Widget boot={{ ...boot, rating_prompt_after: 1 }} />);
  await ask("How much leave?");
  await userEvent.click(score(4));
  await screen.findByText(/You rated this chat 4 out of 5\./);

  await userEvent.click(screen.getByRole("button", { name: "Change rating" }));
  expect(score(1)).toHaveFocus();
  expect(score(4)).toHaveAttribute("aria-pressed", "true");
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.getByText(/You rated this chat 4 out of 5\./)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Change rating" }));
  await userEvent.click(score(2));

  expect(await screen.findByText(/You rated this chat 2 out of 5\./)).toBeInTheDocument();
  expect(seen.map((s) => s.body)).toEqual([{ score: 4 }, { score: 2 }]);
});

test("a dismissal is saved, and the prompt doesn't come back during the chat", async () => {
  const seen = fakeWidgetApi();
  render(<Widget boot={{ ...boot, rating_prompt_after: 1 }} />);
  await ask("How much leave?");

  await userEvent.click(screen.getByRole("button", { name: "Not now" }));

  expect(prompt()).not.toBeInTheDocument();
  await ask("And sick days?");
  expect(prompt()).not.toBeInTheDocument();
  expect(seen).toEqual([{ route: "dismiss", authorization: BEARER }]);
});

test("with N set to 0 the Visitor is asked only when they end the chat", async () => {
  fakeWidgetApi();
  render(<Widget boot={{ ...boot, rating_prompt_after: 0 }} />);

  await ask("One");
  await ask("Two");
  await ask("Three");

  expect(prompt()).not.toBeInTheDocument();
});

test.each([
  ["dismissed the prompt", { score: null, prompt_dismissed: true }, null],
  ["rated it", { score: 3, prompt_dismissed: false }, /You rated this chat 3 out of 5\./],
])("a Visitor who comes back having %s isn't asked again", async (_, rating, shown) => {
  localStorage.setItem(STORED, "wc1.token");
  fakeWidgetApi({
    rating,
    history: [
      { id: "a1", role: "assistant", content: "One", citations: [], feedback: null },
      { id: "a2", role: "assistant", content: "Two", citations: [], feedback: null },
    ],
  });
  render(<Widget boot={boot} />);

  await screen.findByText("Two");

  expect(prompt()).not.toBeInTheDocument();
  if (shown) expect(screen.getByText(shown)).toBeInTheDocument();
});

test("a Visitor who comes back after the Nth reply is asked", async () => {
  localStorage.setItem(STORED, "wc1.token");
  fakeWidgetApi({ history: [{ id: "a1", role: "assistant", content: "One", citations: [], feedback: null }] });
  render(<Widget boot={{ ...boot, rating_prompt_after: 1 }} />);

  await screen.findByText("One");

  expect(prompt()).toBeInTheDocument();
});

describe("on End chat", () => {
  test("a Visitor who hasn't rated is asked first, even after dismissing the prompt, and rating ends the chat", async () => {
    const seen = fakeWidgetApi();
    render(<Widget boot={{ ...boot, rating_prompt_after: 1 }} />);
    await ask("How much leave?");
    await userEvent.click(screen.getByRole("button", { name: "Not now" }));

    await userEvent.click(screen.getByRole("button", { name: "End chat" }));

    const group = screen.getByRole("group", { name: `Before you go: ${QUESTION}` });
    expect(within(group).getByRole("button", { name: "1 out of 5" })).toHaveFocus();
    // The Conversation stays in view; the chat's controls go.
    expect(screen.getByText("Re: How much leave?")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "End chat" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Message")).not.toBeInTheDocument();

    await userEvent.click(score(2));

    expect(await screen.findByRole("status")).toHaveTextContent("You ended the chat.");
    expect(localStorage.getItem(STORED)).toBeNull();
    expect(seen).toEqual([
      { route: "dismiss", authorization: BEARER },
      { route: "rate", body: { score: 2 }, authorization: BEARER },
      { route: "end", authorization: BEARER },
    ]);
  });

  test("a Visitor who has rated isn't asked again", async () => {
    const seen = fakeWidgetApi();
    render(<Widget boot={{ ...boot, rating_prompt_after: 1 }} />);
    await ask("How much leave?");
    await userEvent.click(score(5));
    await screen.findByText(/You rated this chat 5 out of 5\./);

    await userEvent.click(screen.getByRole("button", { name: "End chat" }));

    expect(await screen.findByRole("status")).toHaveTextContent("You ended the chat.");
    expect(seen.map((s) => s.route)).toEqual(["rate", "end"]);
  });

  test("Keep chatting goes back to the chat without asking the API anything", async () => {
    const seen = fakeWidgetApi();
    render(<Widget boot={{ ...boot, rating_prompt_after: 0 }} />);
    await ask("How much leave?");
    await userEvent.click(screen.getByRole("button", { name: "End chat" }));

    await userEvent.click(screen.getByRole("button", { name: "Keep chatting" }));

    expect(screen.getByLabelText("Message")).toHaveFocus();
    expect(prompt()).not.toBeInTheDocument();
    expect(seen).toEqual([]);
  });

  test("a refused rating is announced and the Visitor can still end without rating", async () => {
    const seen = fakeWidgetApi({ refuseRating: "network" });
    render(<Widget boot={{ ...boot, rating_prompt_after: 0 }} />);
    await ask("How much leave?");
    await userEvent.click(screen.getByRole("button", { name: "End chat" }));

    await userEvent.click(score(3));

    expect(await screen.findByRole("alert")).toHaveTextContent(FAILED);
    await userEvent.click(screen.getByRole("button", { name: "End without rating" }));
    expect(await screen.findByRole("status")).toHaveTextContent("You ended the chat.");
    expect(seen.map((s) => s.route)).toEqual(["rate", "dismiss", "end"]);
  });

  test("an expired chat ends anyway when the Visitor rates it", async () => {
    fakeWidgetApi({ refuseRating: 401 });
    render(<Widget boot={{ ...boot, rating_prompt_after: 0 }} />);
    await ask("How much leave?");
    await userEvent.click(screen.getByRole("button", { name: "End chat" }));

    await userEvent.click(score(3));

    expect(await screen.findByRole("status")).toHaveTextContent("You ended the chat.");
  });

  test("a chat with no reply yet ends straight away", async () => {
    const seen = fakeWidgetApi();
    render(<Widget boot={boot} />);

    await userEvent.click(await screen.findByRole("button", { name: "End chat" }));

    expect(await screen.findByRole("status")).toHaveTextContent("You ended the chat.");
    expect(seen).toEqual([]);
  });
});

test.each([
  [500, FAILED],
  [401, EXPIRED],
])("a rating the API refuses with %s is announced and the prompt stays", async (status, message) => {
  fakeWidgetApi({ refuseRating: status });
  render(<Widget boot={{ ...boot, rating_prompt_after: 1 }} />);
  await ask("How much leave?");

  await userEvent.click(score(4));

  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  expect(prompt()).toBeInTheDocument();
  expect(score(4)).toHaveAttribute("aria-pressed", "false");
});

test("once the chat's token is gone, rating says it couldn't be saved and Not now only hides the prompt", async () => {
  const seen = fakeWidgetApi({ refuseAsk: 401 });
  render(<Widget boot={{ ...boot, rating_prompt_after: 1 }} />);
  await ask("How much leave?");
  // The second question finds the chat expired: the widget forgets its token.
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Message"), "Still there?");
  await user.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(EXPIRED);

  await user.click(score(4));
  expect(screen.getByText(FAILED)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Not now" }));
  expect(prompt()).not.toBeInTheDocument();
  // Nothing to end on the API either.
  await user.click(screen.getByRole("button", { name: "End chat" }));
  expect(await screen.findByRole("status")).toHaveTextContent("You ended the chat.");
  expect(seen).toEqual([]);
});
