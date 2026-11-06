import { expect, test } from "../fixtures";

// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-p9q3";

test.describe("Playground Instructions picker", () => {
  test("an Owner asks the Agent's Draft with the Instructions Draft, then with a Version, and each answer records which", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    test.setTimeout(120_000);
    // Set up through the API: a Default Model, a Project with Instructions v1 published and a
    // newer unpublished Draft, and an Agent.
    await page.goto("/");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const organisationId = me.organisations[0]?.id ?? "";
    const organisation = `/api/organisations/${organisationId}`;
    const credential = await page.request.post(`${organisation}/credentials`, {
      data: { name: "Picker Claude", provider: "anthropic", api_key: CHAT_KEY },
    });
    expect(credential.status()).toBe(201);
    const { id: credentialId } = (await credential.json()) as { id: string };
    expect(
      (await page.request.put(`${organisation}/default-model`, { data: { credential_id: credentialId, model: "claude-haiku-4-5" } })).status(),
    ).toBe(200);
    const project = await page.request.post(`${organisation}/projects`, { data: { name: "Picker HR" } });
    expect(project.status()).toBe(201);
    const { id: projectId } = (await project.json()) as { id: string };
    const instructions = `${organisation}/projects/${projectId}/instructions`;
    expect((await page.request.put(instructions, { data: { markdown: "Answer in English." } })).status()).toBe(200);
    const published = await page.request.post(`${instructions}/versions`, { data: { note: "First rules" } });
    expect(published.status()).toBe(201);
    const { id: v1Id } = (await published.json()) as { id: string };
    expect((await page.request.put(instructions, { data: { markdown: "Answer in Welsh." } })).status()).toBe(200);
    const agent = await page.request.post(`${organisation}/projects/${projectId}/agents`, { data: { name: "Picker helper" } });
    expect(agent.status()).toBe(201);
    const { id: agentId } = (await agent.json()) as { id: string };

    await page.goto(`/organisations/${organisationId}/projects/${projectId}/agents/${agentId}`);
    const picker = page.getByRole("combobox", { name: "Instructions", exact: true });
    await expect(picker).toBeVisible({ timeout: 15_000 });
    await expect(picker.getByRole("option")).toHaveText(["Instructions Draft", "v1 (Current) · First rules"]);
    await expect(picker).toHaveValue("");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    const messages = page.getByRole("list", { name: "Playground messages" });
    const answers = messages.getByRole("listitem", { name: "Picker helper" });
    // With the default, the Instructions Draft.
    const started = page.waitForResponse(
      (response) => response.url().endsWith("/playground/conversations") && response.request().method() === "POST",
    );
    await page.getByLabel("Question", { exact: true }).fill("How much leave?");
    await page.getByRole("button", { name: "Send" }).click();
    const { id: conversationId } = (await (await started).json()) as { id: string };
    await expect(answers.nth(0)).toContainText("Instructions: Draft", { timeout: 15_000 });
    // Then with v1.
    await picker.selectOption({ label: "v1 (Current) · First rules" });
    await page.getByLabel("Question", { exact: true }).fill("And with v1?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(answers.nth(1)).toContainText("Instructions: v1", { timeout: 15_000 });
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The Trace names the Instructions too.
    await answers.nth(1).getByRole("button", { name: "Trace" }).click();
    const trace = page.getByRole("dialog", { name: "Trace" });
    await expect(trace.getByText("Instructions", { exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(trace.locator("dt", { hasText: "Instructions" }).locator("+ dd")).toHaveText("v1");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await trace.getByRole("button", { name: "Close" }).click();

    // The API records each answer's Instructions: the Draft marker, then v1.
    const conversation = (await (
      await page.request.get(`${organisation}/projects/${projectId}/agents/${agentId}/playground/conversations/${conversationId}`)
    ).json()) as { messages: { role: string; instructions_source: string | null; instructions_version_id: string | null }[] };
    expect(
      conversation.messages
        .filter((message) => message.role === "assistant")
        .map((message) => [message.instructions_source, message.instructions_version_id]),
    ).toEqual([
      ["draft", null],
      ["version", v1Id],
    ]);
  });
});
