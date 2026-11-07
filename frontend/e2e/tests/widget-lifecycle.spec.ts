import type { APIRequestContext, Browser, BrowserContext } from "@playwright/test";

import { expect, test } from "../fixtures";
import { HOST_URL } from "../fixtures/env";

// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-e604";
const RETIRED = "This assistant is no longer available.";

type Agent = { project: string; id: string; publicId: string };

/** The Organisation's API path, with a Default Model set so live Agents can answer. */
async function organisationWithModel(request: APIRequestContext): Promise<string> {
  const me = (await (await request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
  const organisation = `/api/organisations/${me.organisations[0]?.id ?? ""}`;
  const credential = await request.post(`${organisation}/credentials`, {
    data: { name: "Support Claude", provider: "anthropic", api_key: CHAT_KEY },
  });
  expect(credential.status()).toBe(201);
  const { id } = (await credential.json()) as { id: string };
  const model = await request.put(`${organisation}/default-model`, { data: { credential_id: id, model: "claude-haiku-4-5" } });
  expect(model.status()).toBe(200);
  return organisation;
}

/** An Agent in a new Project, published (unless `publish` is false) and shown on the host page's origin. */
async function agent(request: APIRequestContext, organisation: string, name: string, publish = true): Promise<Agent> {
  const project = await request.post(`${organisation}/projects`, { data: { name: `${name} Project` } });
  expect(project.status()).toBe(201);
  const projectPath = `${organisation}/projects/${((await project.json()) as { id: string }).id}`;
  const created = await request.post(`${projectPath}/agents`, { data: { name } });
  expect(created.status()).toBe(201);
  const { id, public_id: publicId } = (await created.json()) as { id: string; public_id: string };
  const agentPath = `${projectPath}/agents/${id}`;
  const origins = await request.put(`${agentPath}/allowed-origins`, { data: { origins: [new URL(HOST_URL).origin] } });
  expect(origins.status()).toBe(200);
  if (publish) {
    const version = await request.post(`${agentPath}/versions`, { data: { note: "First release" } });
    expect(version.status()).toBe(201);
  }
  return { project: projectPath, id, publicId };
}

/** A Visitor's browser (no Studio session) on the demo host page showing the Agent. */
async function visit(browser: Browser, publicId: string, setUp?: (context: BrowserContext) => Promise<void>) {
  const context = await browser.newContext();
  if (setUp) await setUp(context);
  const host = await context.newPage();
  await host.goto(`${HOST_URL}/?agent=${publicId}`);
  await expect(host.getByRole("heading", { name: "Northwind Traders" })).toBeVisible();
  const widget = host.frameLocator('iframe[title="Chat"]');
  return { context, host, widget, log: widget.getByRole("log", { name: "Conversation" }) };
}

test.describe("Widget Conversation lifecycle", () => {
  test("a Visitor's Conversation comes back after a reload; New chat and End chat start afresh; a retired Agent says so", async ({
    signedInPage: page,
    browser,
  }) => {
    test.setTimeout(150_000);
    await page.goto("/");
    const organisation = await organisationWithModel(page.request);
    const helper = await agent(page.request, organisation, "HR helper");
    const { context, host, widget, log } = await visit(browser, helper.publicId);

    // Chat, then reload: the Conversation is still there and carries on.
    await widget.getByLabel("Message").fill("How many days of annual leave do I get?");
    await widget.getByRole("button", { name: "Send" }).click();
    const reply = log.getByRole("listitem", { name: "HR helper" });
    await expect(reply).toHaveCount(1, { timeout: 15_000 });
    await expect(widget.getByRole("button", { name: "Send" })).toBeEnabled({ timeout: 15_000 });
    const answer = (await reply.textContent()) ?? "";
    expect(answer).not.toBe("");
    await host.reload();
    await expect(log.getByRole("listitem", { name: "You" })).toHaveText("How many days of annual leave do I get?", { timeout: 15_000 });
    await expect(reply).toHaveText(answer);
    await widget.getByLabel("Message").fill("And sick days?");
    await widget.getByRole("button", { name: "Send" }).click();
    await expect(reply).toHaveCount(2, { timeout: 15_000 });
    await expect(widget.getByRole("button", { name: "Send" })).toBeEnabled({ timeout: 15_000 });
    await host.reload();
    await expect(log.getByRole("listitem", { name: "You" })).toHaveText(["How many days of annual leave do I get?", "And sick days?"], {
      timeout: 15_000,
    });

    // New chat clears it, and a reload no longer brings the old one back.
    await widget.getByRole("button", { name: "New chat" }).click();
    await expect(log.getByRole("listitem")).toHaveCount(0);
    await host.reload();
    await expect(widget.getByLabel("Message")).toBeVisible({ timeout: 15_000 });
    await expect(log.getByRole("listitem")).toHaveCount(0);

    // End chat: the chat closes; a reload shows a fresh one.
    await widget.getByLabel("Message").fill("Where is the handbook?");
    await widget.getByRole("button", { name: "Send" }).click();
    await expect(reply).toHaveCount(1, { timeout: 15_000 });
    await expect(widget.getByRole("button", { name: "Send" })).toBeEnabled({ timeout: 15_000 });
    await widget.getByRole("button", { name: "End chat" }).click();
    await expect(widget.getByRole("status")).toHaveText("You ended the chat.");
    await expect(widget.getByLabel("Message")).toHaveCount(0);
    await host.reload();
    await expect(widget.getByLabel("Message")).toBeVisible({ timeout: 15_000 });
    await expect(log.getByRole("listitem")).toHaveCount(0);

    // Chat again, then the Agent is archived: the next reload shows the retired shell.
    await widget.getByLabel("Message").fill("Hello?");
    await widget.getByRole("button", { name: "Send" }).click();
    await expect(reply).toHaveCount(1, { timeout: 15_000 });
    await expect(widget.getByRole("button", { name: "Send" })).toBeEnabled({ timeout: 15_000 });
    expect((await page.request.post(`${helper.project}/agents/${helper.id}/archive`)).status()).toBe(200);
    // Mid-Conversation, the next question gets the retired message instead of an answer.
    await widget.getByLabel("Message").fill("Still there?");
    await widget.getByRole("button", { name: "Send" }).click();
    await expect(widget.getByRole("status")).toHaveText(RETIRED, { timeout: 15_000 });
    await expect(widget.getByRole("log")).toHaveCount(0);
    await host.reload();
    await expect(widget.getByRole("status")).toHaveText(RETIRED, { timeout: 15_000 });
    await expect(widget.getByLabel("Message")).toHaveCount(0);
    await context.close();
  });

  test("an Agent that was never published shows the no longer available shell on the host page", async ({
    signedInPage: page,
    browser,
  }) => {
    await page.goto("/");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const draftOnly = await agent(page.request, `/api/organisations/${me.organisations[0]?.id ?? ""}`, "Draft helper", false);

    const { context, widget } = await visit(browser, draftOnly.publicId);

    await expect(widget.getByRole("status")).toHaveText(RETIRED, { timeout: 15_000 });
    await expect(widget.getByLabel("Message")).toHaveCount(0);
    await context.close();
  });

  test("when the browser blocks the iframe's storage, the Visitor still chats and a reload starts afresh", async ({
    signedInPage: page,
    browser,
  }) => {
    test.setTimeout(120_000);
    await page.goto("/");
    const organisation = await organisationWithModel(page.request);
    const helper = await agent(page.request, organisation, "Storage helper");
    const { context, host, widget, log } = await visit(browser, helper.publicId, (context) =>
      // As a browser that blocks third-party storage does: any access throws.
      context.addInitScript(() => {
        if (window.location.pathname.startsWith("/widget/a/")) {
          Object.defineProperty(window, "localStorage", {
            configurable: true,
            get() {
              throw new DOMException("The operation is insecure.", "SecurityError");
            },
          });
        }
      }),
    );

    await widget.getByLabel("Message").fill("Hello?");
    await widget.getByRole("button", { name: "Send" }).click();
    await expect(log.getByRole("listitem", { name: "Storage helper" })).toHaveCount(1, { timeout: 15_000 });
    await expect(widget.getByRole("button", { name: "Send" })).toBeEnabled({ timeout: 15_000 });
    await widget.getByLabel("Message").fill("Again?");
    await widget.getByRole("button", { name: "Send" }).click();
    await expect(log.getByRole("listitem", { name: "Storage helper" })).toHaveCount(2, { timeout: 15_000 });
    await expect(widget.getByRole("alert")).toHaveCount(0);

    await host.reload();

    await expect(widget.getByLabel("Message")).toBeVisible({ timeout: 15_000 });
    await expect(log.getByRole("listitem")).toHaveCount(0);
    await context.close();
  });
});
