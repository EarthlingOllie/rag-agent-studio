import AxeBuilder from "@axe-core/playwright";
import type { APIRequestContext, Browser, FrameLocator, Page } from "@playwright/test";

import { AXE_TAGS, expect, test } from "../fixtures";
import { HOST_URL } from "../fixtures/env";

// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-e607";

/** A published Agentic Agent (it searches before it answers) with a greeting and starter
 * questions, allowed on the demo host page, in an Organisation whose Theme (the default colours)
 * follows the Visitor's light or dark mode. */
async function publishedAgent(request: APIRequestContext): Promise<string> {
  const me = (await (await request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
  const organisation = `/api/organisations/${me.organisations[0]?.id ?? ""}`;
  const credential = await request.post(`${organisation}/credentials`, {
    data: { name: "Support Claude", provider: "anthropic", api_key: CHAT_KEY },
  });
  expect(credential.status()).toBe(201);
  const { id: credentialId } = (await credential.json()) as { id: string };
  expect((await request.put(`${organisation}/default-model`, { data: { credential_id: credentialId, model: "claude-haiku-4-5" } })).status()).toBe(200);
  const project = (await (await request.post(`${organisation}/projects`, { data: { name: "Northwind HR", description: "" } })).json()) as {
    id: string;
  };
  const created = await request.post(`${organisation}/projects/${project.id}/agents`, { data: { name: "HR helper" } });
  expect(created.status()).toBe(201);
  const agent = (await created.json()) as { id: string; public_id: string };
  const agentPath = `${organisation}/projects/${project.id}/agents/${agent.id}`;
  const draft = await request.put(`${agentPath}/draft`, {
    data: {
      experience: {
        display_name: "Hana from HR",
        greeting: "Hi! Ask me about leave, pay or benefits.",
        starter_questions: ["How much leave do I get?", "When is payday?"],
      },
      retrieval: { mode: "agentic" },
    },
  });
  expect(draft.status()).toBe(200);
  expect((await request.post(`${agentPath}/versions`, { data: { note: "Accessible" } })).status()).toBe(201);
  const origins = await request.patch(`${agentPath}/operational-settings`, {
    data: { allowed_origins: [new URL(HOST_URL).origin] },
  });
  expect(origins.status()).toBe(200);
  const theme = (await (await request.get(`${organisation}/theme`)).json()) as Record<string, unknown>;
  for (const key of ["updated_at", "logo", "avatar"]) Reflect.deleteProperty(theme, key);
  expect((await request.put(`${organisation}/theme`, { data: { ...theme, mode: "auto" } })).status()).toBe(200);
  return agent.public_id;
}

/** Every WCAG 2.2 AA violation axe finds on the host page, the widget's frame included. */
async function violations(host: Page) {
  const results = await new AxeBuilder({ page: host }).withTags(AXE_TAGS).analyze();
  return results.violations.map(({ id, nodes }) => ({ id, targets: nodes.map((node) => node.target) }));
}

/** The class of the panel's opening animation, as the browser resolves it inside the frame. */
async function panelAnimation(host: Page): Promise<string> {
  const frame = host.frames().find((candidate) => candidate.url().includes("/widget/a/"));
  if (!frame) throw new Error("The widget frame is not on the page");
  return frame.evaluate(() => getComputedStyle(document.querySelector(".panel") as HTMLElement).animationName);
}

/**
 * Holds each widget reply after its first `search` event until `releaseAnswer()` is called in the
 * widget's frame, so the searching status stays on screen long enough to check. The stream is
 * the API's own, except that the first `search` is preceded by text and its `retract` event, as
 * when a model writes before it searches (the compose stack's fake model never does): the
 * retracted text must give way to the searching status and never be announced (ticket 13-10).
 */
function holdAfterSearch() {
  if (!location.pathname.startsWith("/widget/a/")) return;
  const held: (() => void)[] = [];
  Object.assign(window, {
    releaseAnswer: () => {
      for (const release of held.splice(0)) release();
    },
  });
  const realFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await realFetch(input, init);
    const url = input instanceof Request ? input.url : String(input);
    if (!url.endsWith("/messages") || init?.method !== "POST" || !response.body) return response;
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const encoder = new TextEncoder();
    let holding = true;
    const body = new ReadableStream<Uint8Array>({
      async pull(controller) {
        const { value, done } = await reader.read();
        if (done) {
          controller.close();
          return;
        }
        const text = decoder.decode(value, { stream: true });
        const at = holding ? text.indexOf("event: search") : -1;
        if (at === -1) {
          controller.enqueue(value);
          return;
        }
        // Up to the end of the first `search` event now, after the retracted text; the rest
        // once released.
        holding = false;
        const close = text.indexOf("\n\n", at);
        const end = close === -1 ? text.length : close + 2;
        const retracted = `event: token\ndata: ${JSON.stringify({ text: "Let me look that up for you first. " })}\n\nevent: retract\ndata: {}\n\n`;
        controller.enqueue(encoder.encode(text.slice(0, at) + retracted + text.slice(at, end)));
        await new Promise<void>((release) => held.push(release));
        if (end < text.length) controller.enqueue(encoder.encode(text.slice(end)));
      },
    });
    return new Response(body, { status: response.status, headers: response.headers });
  };
}

async function visitor(browser: Browser, colorScheme: "light" | "dark", reducedMotion: "reduce" | "no-preference") {
  const context = await browser.newContext({ colorScheme, reducedMotion });
  await context.addInitScript(holdAfterSearch);
  const host = await context.newPage();
  return { context, host };
}

for (const [colorScheme, reducedMotion, animation] of [
  ["light", "no-preference", "widget-open"],
  ["dark", "reduce", "none"],
] as const) {
  test(`a keyboard and screen-reader Visitor uses the bubble in ${colorScheme} mode (${reducedMotion} motion), and axe finds no AA violations`, async ({
    signedInPage: page,
    browser,
  }) => {
    test.setTimeout(180_000);
    await page.goto("/");
    const agent = await publishedAgent(page.request);
    const { context, host } = await visitor(browser, colorScheme, reducedMotion);
    await host.goto(`${HOST_URL}/?agent=${agent}&launcher=bubble`);
    const widget: FrameLocator = host.frameLocator('iframe[title="Chat"]');
    const launcher = widget.getByRole("button", { name: "Open chat" });
    await expect(launcher).toBeVisible({ timeout: 15_000 });

    // Closed: only the Launcher, and nothing for axe to object to.
    expect(await violations(host)).toEqual([]);

    // Tab from the host page reaches the Launcher; Enter opens the chat with focus in the message box.
    await host.keyboard.press("Tab");
    await expect(launcher).toBeFocused();
    await host.keyboard.press("Enter");
    const chat = widget.getByRole("region", { name: "Chat with Hana from HR" });
    await expect(chat).toBeVisible();
    expect(await panelAnimation(host)).toBe(animation);
    const message = chat.getByLabel("Message");
    await expect(message).toBeFocused();

    // Tab cycles through the chat's controls and never leaves it while it's open.
    await host.keyboard.press("Tab");
    await expect(chat.getByRole("button", { name: "Send" })).toBeFocused();
    await host.keyboard.press("Tab");
    await expect(chat.getByRole("button", { name: "New chat" })).toBeFocused();
    await host.keyboard.press("Shift+Tab");
    await expect(chat.getByRole("button", { name: "Send" })).toBeFocused();
    for (let step = 0; step < 12; step += 1) {
      await host.keyboard.press("Tab");
      await expect(chat.locator(":focus")).toHaveCount(1);
    }

    // Open with the greeting and starter questions on screen.
    expect(await violations(host)).toEqual([]);

    // A question typed and sent from the keyboard. Text streamed before the Search is retracted;
    // while the Agent searches the reply shows the searching status, announced once; the status
    // shows, axe finds nothing either.
    await message.focus();
    await host.keyboard.type("How much leave do I get?");
    await host.keyboard.press("Enter");
    const reply = chat.getByRole("log", { name: "Conversation" }).getByRole("listitem", { name: "Hana from HR", exact: true });
    const announcements = chat.getByRole("status", { name: "Announcements" });
    await expect(reply).toContainText("Searching the knowledge base…", { timeout: 15_000 });
    await expect(announcements).toHaveText("Searching the knowledge base…");
    await expect(reply).not.toContainText("look that up");
    expect(await violations(host)).toEqual([]);

    // The answer replaces the status, and is announced once it is complete.
    await host.frameLocator('iframe[title="Chat"]').locator("body").evaluate(() => {
      (window as unknown as { releaseAnswer: () => void }).releaseAnswer();
    });
    await expect(chat.getByRole("button", { name: "Send" })).toBeEnabled({ timeout: 15_000 });
    await expect(reply).not.toContainText("Searching the knowledge base…");
    // The reply's text only: the bubble also holds its Message Feedback thumbs (07-02).
    const answer = (await reply.locator("p").first().innerText()).trim();
    expect(answer).not.toBe("");
    await expect(announcements).toHaveText(`Hana from HR: ${answer}`);
    expect(answer).not.toContain("look that up");

    // Open with a Conversation in it.
    expect(await violations(host)).toEqual([]);

    // Escape closes it and focus is back on the Launcher.
    await host.keyboard.press("Escape");
    await expect(chat).toBeHidden();
    await expect(launcher).toBeFocused();
    await context.close();
  });
}

test("axe finds no AA violations on the inline widget in light and dark mode", async ({ signedInPage: page, browser }) => {
  test.setTimeout(120_000);
  await page.goto("/");
  const agent = await publishedAgent(page.request);
  for (const colorScheme of ["light", "dark"] as const) {
    const { context, host } = await visitor(browser, colorScheme, "no-preference");
    await host.goto(`${HOST_URL}/?agent=${agent}&launcher=inline`);
    const widget = host.frameLocator('iframe[title="Chat"]');
    await expect(widget.getByRole("region", { name: "Chat with Hana from HR" })).toBeVisible({ timeout: 15_000 });
    expect(await violations(host)).toEqual([]);
    await context.close();
  }
});
