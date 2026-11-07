import type { APIRequestContext, FrameLocator, Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { HOST_URL } from "../fixtures/env";

// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-e603";

type Agent = { id: string; public_id: string; project_id: string };

/** An Organisation with a Default Model and a published Agent with a greeting, starter
 * questions and a UI text override, allowed on the demo host page, set up through the API. */
async function brandedAgent(request: APIRequestContext): Promise<{ organisation: string; agent: Agent }> {
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
  const agent = (await created.json()) as Agent;
  const agentPath = `${organisation}/projects/${project.id}/agents/${agent.id}`;
  const draft = await request.put(`${agentPath}/draft`, {
    data: {
      experience: {
        display_name: "Hana from HR",
        greeting: "Hi! Ask me about leave, pay or benefits.",
        starter_questions: ["How much leave do I get?", "When is payday?"],
        ui_text: { send_button: "Ask" },
      },
    },
  });
  expect(draft.status()).toBe(200);
  expect((await request.post(`${agentPath}/versions`, { data: { note: "Branded" } })).status()).toBe(201);
  const origins = await request.put(`${agentPath}/allowed-origins`, { data: { origins: [new URL(HOST_URL).origin] } });
  expect(origins.status()).toBe(200);
  return { organisation, agent };
}

/** A CSS custom property of the widget's Theme, as the browser resolves it inside the frame. */
async function themeValue(host: Page, property: string): Promise<string> {
  const frame = host.frames().find((candidate) => candidate.url().includes("/widget/a/"));
  if (!frame) throw new Error("The widget frame is not on the page");
  return frame.evaluate((name) => getComputedStyle(document.getElementById("root") as HTMLElement).getPropertyValue(name).trim(), property);
}

async function opened(host: Page): Promise<FrameLocator> {
  const widget = host.frameLocator('iframe[title="Chat"]');
  await widget.getByRole("button", { name: "Open chat" }).click({ timeout: 15_000 });
  await expect(widget.getByRole("region", { name: "Chat with Hana from HR" })).toBeVisible();
  return widget;
}

test.describe("Branded widget", () => {
  test("the widget wears the Theme with the Agent's own colour, as a bubble, full-screen on a phone, inline, light and dark", async ({
    signedInPage: page,
    browser,
  }) => {
    test.setTimeout(180_000);
    await page.goto("/");
    const { organisation, agent } = await brandedAgent(page.request);
    // The Theme follows the Visitor's light or dark preference.
    const theme = (await (await page.request.get(`${organisation}/theme`)).json()) as Record<string, unknown>;
    for (const key of ["updated_at", "logo", "avatar"]) Reflect.deleteProperty(theme, key);
    expect((await page.request.put(`${organisation}/theme`, { data: { ...theme, mode: "auto" } })).status()).toBe(200);

    // The Owner gives this Agent its own primary colour on the Agent page; no publishing.
    await page.goto(`/organisations/${organisation.split("/").at(-1) ?? ""}/projects/${agent.project_id}/agents/${agent.id}`);
    const branding = page.getByRole("region", { name: "Widget branding" });
    await branding.getByRole("checkbox", { name: "Override primary" }).check({ timeout: 15_000 });
    await branding.getByLabel("Primary, light").fill("#aa0000");
    await branding.getByLabel("Primary, dark").fill("#ff8888");
    await branding.getByRole("button", { name: "Save colours" }).click();
    await expect(branding.getByText("Saved. The widget uses these colours now.")).toBeVisible();

    // A Visitor on a phone in dark mode: the bubble opens to fill the screen.
    const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: "dark", hasTouch: true });
    const host = await phone.newPage();
    await host.goto(`${HOST_URL}/?agent=${agent.public_id}`);
    const frame = host.locator('iframe[title="Chat"]');
    await expect(frame).toHaveCSS("width", "88px", { timeout: 15_000 });
    const widget = await opened(host);
    await expect(frame).toHaveCSS("width", "390px");
    await expect(frame).toHaveCSS("height", "844px");
    expect(await themeValue(host, "--theme-primary")).toBe("#ff8888");
    expect(await themeValue(host, "--theme-surface")).toBe("#111827");
    const log = widget.getByRole("log", { name: "Conversation" });
    await expect(log.getByRole("listitem", { name: "Hana from HR's greeting" })).toHaveText("Hi! Ask me about leave, pay or benefits.");
    await expect(widget.getByRole("button", { name: "Ask" })).toBeVisible();
    // A starter question asks itself, and the reply streams in from the Live Version.
    await widget.getByRole("list", { name: "Suggested questions" }).getByRole("button", { name: "How much leave do I get?" }).click();
    await expect(log.getByRole("listitem", { name: "You" })).toHaveText("How much leave do I get?");
    await expect(log.getByRole("listitem", { name: "Hana from HR" })).not.toBeEmpty({ timeout: 15_000 });
    await widget.getByRole("button", { name: "Close chat" }).first().click();
    await expect(frame).toHaveCSS("width", "88px");
    await phone.close();

    // A Visitor on a desktop in light mode, with the snippet's inline launcher in the page's container.
    const desktop = await browser.newContext({ colorScheme: "light" });
    const inlineHost = await desktop.newPage();
    await inlineHost.goto(`${HOST_URL}/?agent=${agent.public_id}&launcher=inline`);
    const inline = inlineHost.getByRole("region", { name: "Help" }).locator('iframe[title="Chat"]');
    await expect(inline).toHaveCSS("height", "560px", { timeout: 15_000 });
    const inlineWidget = inlineHost.frameLocator('iframe[title="Chat"]');
    await expect(inlineWidget.getByRole("region", { name: "Chat with Hana from HR" })).toBeVisible();
    await expect(inlineWidget.getByRole("button", { name: "Open chat" })).toHaveCount(0);
    expect(await themeValue(inlineHost, "--theme-primary")).toBe("#aa0000");
    expect(await themeValue(inlineHost, "--theme-surface")).toBe("#ffffff");

    // A desktop bubble opens to a panel in the corner, not the whole screen.
    const bubbleHost = await desktop.newPage();
    await bubbleHost.goto(`${HOST_URL}/?agent=${agent.public_id}&launcher=bubble`);
    await opened(bubbleHost);
    await expect(bubbleHost.locator('iframe[title="Chat"]')).toHaveCSS("width", "420px");
    await desktop.close();
  });
});
