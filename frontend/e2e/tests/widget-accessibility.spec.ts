import AxeBuilder from "@axe-core/playwright";
import type { APIRequestContext, Browser, FrameLocator, Page } from "@playwright/test";

import { AXE_TAGS, expect, test } from "../fixtures";
import { HOST_URL } from "../fixtures/env";

// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-e607";

/** A published Agent with a greeting and starter questions, allowed on the demo host page, in
 * an Organisation whose Theme (the default colours) follows the Visitor's light or dark mode. */
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
    },
  });
  expect(draft.status()).toBe(200);
  expect((await request.post(`${agentPath}/versions`, { data: { note: "Accessible" } })).status()).toBe(201);
  expect((await request.put(`${agentPath}/allowed-origins`, { data: { origins: [new URL(HOST_URL).origin] } })).status()).toBe(200);
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

async function visitor(browser: Browser, colorScheme: "light" | "dark", reducedMotion: "reduce" | "no-preference") {
  const context = await browser.newContext({ colorScheme, reducedMotion });
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

    // A question typed and sent from the keyboard; the reply is announced once it is complete.
    await message.focus();
    await host.keyboard.type("How much leave do I get?");
    await host.keyboard.press("Enter");
    const reply = chat.getByRole("log", { name: "Conversation" }).getByRole("listitem", { name: "Hana from HR", exact: true });
    await expect(chat.getByRole("button", { name: "Send" })).toBeEnabled({ timeout: 15_000 });
    const answer = (await reply.innerText()).trim();
    expect(answer).not.toBe("");
    await expect(chat.getByRole("status", { name: "Announcements" })).toHaveText(`Hana from HR: ${answer}`);

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
