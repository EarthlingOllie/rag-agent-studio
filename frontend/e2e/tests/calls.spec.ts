import { fileURLToPath } from "node:url";

import AxeBuilder from "@axe-core/playwright";

import { AXE_TAGS, expect, test } from "../fixtures";
import { liveVersion, openAgentView, publishAgent } from "../fixtures/agent";
import { HOST_URL } from "../fixtures/env";
import { openSection } from "../fixtures/navigation";

/** The seed staff handbook (synthetic content), so the Agent has something to cite. */
const HANDBOOK = fileURLToPath(new URL("../../../seed/documents/northwind-staff-handbook.md", import.meta.url));
// The compose stack checks keys with the fake verifier, answers with the fake gateway's chat model
// and holds Calls with the scripted fake voice layer. No real provider is called, no real key is
// used, and no audio is played.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-e2004";
const VOICE_KEY = "sk_e2e_test_only_not_a_real_elevenlabs_key_2004";
const QUESTION = "How many days of annual leave do I get?";

test.describe("Calls", () => {
  test("an Editor turns calling on, and a Visitor on the host page calls the Agent and is answered with a source", async ({
    signedInPage: page,
    browser,
  }) => {
    test.setTimeout(180_000);
    await page.goto("/");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const organisation = `/api/organisations/${me.organisations[0]?.id ?? ""}`;
    const chat = await page.request.post(`${organisation}/credentials`, {
      data: { name: "Support Claude", provider: "anthropic", api_key: CHAT_KEY },
    });
    expect(chat.status()).toBe(201);
    const { id: chatId } = (await chat.json()) as { id: string };
    expect((await page.request.put(`${organisation}/default-model`, { data: { credential_id: chatId, model: "claude-haiku-4-5" } })).status()).toBe(200);
    const voice = await page.request.post(`${organisation}/credentials`, {
      data: { name: "Front desk voice", provider: "elevenlabs", api_key: VOICE_KEY },
    });
    expect(voice.status()).toBe(201);

    // A Project holding the handbook, and an Agent whose first starter question the scripted Call asks.
    await openSection(page, "Organisation sections", "Projects");
    await page.getByRole("button", { name: "New Project" }).click();
    const newProject = page.getByRole("form", { name: "New Project" });
    await newProject.getByLabel("Name").fill("Northwind HR");
    await newProject.getByRole("button", { name: "Create Project" }).click();
    await page.getByLabel("Upload", { exact: true }).setInputFiles(HANDBOOK);
    const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /northwind-staff-handbook\.md/ });
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    await openSection(page, "Project sections", "Agents");
    await page.getByRole("button", { name: "New Agent" }).click();
    const newAgent = page.getByRole("form", { name: "New Agent" });
    await newAgent.getByLabel("Name").fill("HR helper");
    await newAgent.getByRole("button", { name: "Create Agent" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "HR helper" })).toBeVisible({ timeout: 15_000 });
    const agentApi = page.url().replace(/^https?:\/\/[^/]+/, "/api");
    const { public_id: publicId } = (await (await page.request.get(agentApi)).json()) as { public_id: string };
    expect((await page.request.put(`${agentApi}/draft`, { data: { experience: { starter_questions: [QUESTION] } } })).status()).toBe(200);
    await page.reload();
    await publishAgent(page, "First release");
    await expect(liveVersion(page, 1)).toBeVisible({ timeout: 15_000 });
    const origins = await page.request.patch(`${agentApi}/operational-settings`, { data: { allowed_origins: [new URL(HOST_URL).origin] } });
    expect(origins.status()).toBe(200);

    // The Editor turns calling on in the Agent's Call settings.
    await openAgentView(page, "Embed & limits");
    const calls = page.getByRole("region", { name: "Call settings" });
    await calls.getByLabel("Visitors can call the Agent").check();
    await calls.getByLabel("Credential").selectOption({ label: "Front desk voice" });
    await calls.getByLabel("Voice", { exact: true }).selectOption({ label: "Ada" });
    await calls.getByLabel("Spoken greeting").fill("Hello, you're through to HR.");
    await calls.getByRole("button", { name: "Save Call settings" }).click();
    await expect(calls.getByText("Saved. Calls use these settings from now on.")).toBeVisible({ timeout: 15_000 });

    // A Visitor on the host page (another browser, no Studio session) chooses Call.
    const visitor = await browser.newContext();
    const host = await visitor.newPage();
    await host.goto(`${HOST_URL}/?agent=${publicId}`);
    const widget = host.frameLocator('iframe[title="Chat"]');
    await widget.getByRole("button", { name: "Open chat" }).click({ timeout: 15_000 });
    const choice = widget.getByRole("group", { name: "How would you like to ask?" });
    await expect(choice).toBeVisible({ timeout: 15_000 });
    await expect(widget.getByLabel("Message")).toHaveCount(0);
    expect((await new AxeBuilder({ page: host }).withTags(AXE_TAGS).analyze()).violations).toEqual([]);
    await choice.getByRole("button", { name: "Call" }).click();

    // The scripted exchange fills the Conversation log: the Visitor's words, then the Agent's
    // reply with its source, while the Call view says whether the Agent speaks or listens.
    const call = widget.getByRole("group", { name: "Call" });
    await expect(call).toBeVisible();
    await expect(widget.getByLabel("Message")).toHaveCount(0);
    const log = widget.getByRole("log", { name: "Conversation" });
    await expect(log.getByRole("listitem", { name: "You" })).toHaveText(QUESTION, { timeout: 15_000 });
    const reply = log.getByRole("listitem", { name: "HR helper" }).first();
    await expect(reply).toContainText("Fake reply from anthropic:claude-haiku-4-5.", { timeout: 15_000 });
    await expect(reply).toContainText("Sources: northwind-staff-handbook.md");
    await expect(reply.getByRole("button", { name: "Helpful", exact: true })).toBeVisible();
    await expect(call.getByRole("status")).toHaveText("Listening…", { timeout: 15_000 });
    await expect(call.getByRole("button", { name: "Mute" })).toHaveAttribute("aria-pressed", "false");
    expect((await new AxeBuilder({ page: host }).withTags(AXE_TAGS).analyze()).violations).toEqual([]);

    // End call returns to the chat, with the Spoken Messages in the log.
    await call.getByRole("button", { name: "End call" }).click();
    await expect(widget.getByLabel("Message")).toBeVisible();
    await expect(call).toHaveCount(0);
    await expect(log.getByRole("listitem", { name: "You" })).toHaveText(QUESTION);
    await expect(log.getByRole("listitem", { name: "HR helper" }).first()).toContainText("Sources: northwind-staff-handbook.md");

    // The chat header's Call button starts another Call in the same Conversation; it opens
    // listening, as the Conversation already has Messages.
    await widget.getByRole("button", { name: "Call", exact: true }).click();
    await expect(call.getByRole("status")).toHaveText("Listening…", { timeout: 15_000 });
    await expect(log.getByRole("listitem", { name: "You" })).toHaveCount(2, { timeout: 15_000 });
    await expect(log.getByRole("listitem", { name: "HR helper" })).toHaveCount(2, { timeout: 15_000 });

    // A reload ends the Call: the resumed Conversation shows what was said and offers
    // "Continue call", which starts a new Call only when tapped.
    await host.reload();
    await widget.getByRole("button", { name: "Open chat" }).click({ timeout: 15_000 });
    const continueCall = widget.getByRole("button", { name: "Continue call" });
    await expect(continueCall).toBeVisible({ timeout: 15_000 });
    await expect(log.getByRole("listitem", { name: "You" })).toHaveCount(2);
    await expect(call).toHaveCount(0);
    await expect(widget.getByLabel("Message")).toBeVisible();
    await continueCall.click();
    await expect(call.getByRole("status")).toHaveText("Listening…", { timeout: 15_000 });
    await expect(continueCall).toHaveCount(0);

    // New chat ends the Call and starts afresh.
    await widget.getByRole("button", { name: "New chat" }).click();
    await expect(call).toHaveCount(0);
    await expect(log.getByRole("listitem", { name: "You" })).toHaveCount(0);
    await visitor.close();
  });
});
