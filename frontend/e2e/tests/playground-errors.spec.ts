import { fileURLToPath } from "node:url";

import { expect, test } from "../fixtures";

/** The seed staff handbook (synthetic content), uploaded as an Editor would. */
const HANDBOOK = fileURLToPath(new URL("../../../seed/documents/northwind-staff-handbook.md", import.meta.url));
// The compose stack checks keys with the fake verifier and answers with the fake gateway's chat
// model, which fails as a provider would when the question asks it to ("simulate a rate limit").
// No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-x5e8";

test.describe("Playground errors and reset", () => {
  test("a provider failure is explained, and a reset starts a new Conversation", async ({ signedInPage: page, makeAxeBuilder }) => {
    // Ingestion, axe scans and several streamed answers: more than the default 30 seconds.
    test.setTimeout(120_000);
    // A Default Model, a Project and an Agent, set up through the API.
    await page.goto("/");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const organisationId = me.organisations[0]?.id ?? "";
    const organisation = `/api/organisations/${organisationId}`;
    const credential = await page.request.post(`${organisation}/credentials`, {
      data: { name: "Support Claude", provider: "anthropic", api_key: CHAT_KEY },
    });
    expect(credential.status()).toBe(201);
    const { id } = (await credential.json()) as { id: string };
    const chosen = await page.request.put(`${organisation}/default-model`, { data: { credential_id: id, model: "claude-haiku-4-5" } });
    expect(chosen.status()).toBe(200);
    const project = await page.request.post(`${organisation}/projects`, { data: { name: "Northwind HR" } });
    const projectId = ((await project.json()) as { id: string }).id;
    const agent = await page.request.post(`${organisation}/projects/${projectId}/agents`, { data: { name: "HR helper" } });
    const agentId = ((await agent.json()) as { id: string }).id;
    // The Knowledge Base holds the handbook, so retrieval finds Chunks and the model is asked.
    await page.goto(`/organisations/${organisationId}/projects/${projectId}`);
    await page.getByLabel("Upload", { exact: true }).setInputFiles(HANDBOOK);
    const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /northwind-staff-handbook\.md/ });
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    await page.goto(`/organisations/${organisationId}/projects/${projectId}/agents/${agentId}`);

    const question = page.getByLabel("Question", { exact: true });
    const send = page.getByRole("button", { name: "Send" });
    const messages = page.getByRole("list", { name: "Playground messages" });
    const answers = messages.getByRole("listitem", { name: "HR helper" });

    // A first answer, so the Conversation has a turn to remember.
    await question.fill("How many days of annual leave do I get?");
    await send.click();
    await expect(answers.first()).toContainText("Fake reply from anthropic:claude-haiku-4-5.", { timeout: 15_000 });

    // Each provider failure ends the stream with its own readable message, and no answer. (The
    // questions pass the input Guardrail's local classifier, which scores "Please simulate an
    // invalid key." as an attack.)
    const failures: [string, RegExp][] = [
      ["Please simulate a rate limit.", /over its rate limit or quota\. Wait a moment and try again/],
      ["Could you simulate an invalid key error?", /The provider rejected the API key\. An Owner can check or rotate the Provider Credential/],
      ["Please simulate an unavailable model.", /The model claude-haiku-4-5 isn't available from the provider right now/],
    ];
    for (const [asked, explained] of failures) {
      await question.fill(asked);
      await send.click();
      await expect(page.getByRole("alert")).toHaveText(explained, { timeout: 15_000 });
      await expect(answers).toHaveCount(1);
    }
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // Reset: a new Playground Conversation, empty.
    const started = page.waitForResponse(
      (response) => response.url().endsWith("/playground/conversations") && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Reset conversation" }).click();
    const reset = await started;
    expect(reset.status()).toBe(201);
    const fresh = (await reset.json()) as { id: string; messages: unknown[] };
    expect(fresh.messages).toEqual([]);
    await expect(page.getByText("Started a new conversation.")).toBeVisible();
    await expect(messages.getByRole("listitem")).toHaveCount(0);
    await expect(page.getByRole("alert")).toHaveCount(0);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The next question is asked in the new Conversation.
    const asked = page.waitForResponse((response) => response.url().includes(`/conversations/${fresh.id}/messages`));
    await question.fill("And how much sick leave?");
    await send.click();
    expect((await asked).status()).toBe(200);
    await expect(answers.first()).toContainText("Fake reply from anthropic:claude-haiku-4-5.", { timeout: 15_000 });
    const saved = await page.request.get(`${organisation}/projects/${projectId}/agents/${agentId}/playground/conversations/${fresh.id}`);
    const conversation = (await saved.json()) as { is_playground: boolean; messages: { role: string; content: string }[] };
    expect(conversation.is_playground).toBe(true);
    expect(conversation.messages.map((message) => message.role)).toEqual(["user", "assistant"]);
    expect(conversation.messages[0]?.content).toBe("And how much sick leave?");
  });
});
