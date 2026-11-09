import { expect, test } from "../fixtures";
import { HOST_URL } from "../fixtures/env";

// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-e704";

test.describe("Version KPIs", () => {
  test("a Visitor's feedback and rating show in the Live Version's KPI cards, marked low confidence; the Playground doesn't count", async ({
    signedInPage: page,
    makeAxeBuilder,
    browser,
  }) => {
    test.setTimeout(180_000);
    await page.goto("/");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const organisationId = me.organisations[0]?.id ?? "";
    const organisation = `/api/organisations/${organisationId}`;
    const credential = await page.request.post(`${organisation}/credentials`, {
      data: { name: "Support Claude", provider: "anthropic", api_key: CHAT_KEY },
    });
    expect(credential.status()).toBe(201);
    const { id } = (await credential.json()) as { id: string };
    expect(
      (await page.request.put(`${organisation}/default-model`, { data: { credential_id: id, model: "claude-haiku-4-5" } })).status(),
    ).toBe(200);
    const project = await page.request.post(`${organisation}/projects`, { data: { name: "KPI HR" } });
    const { id: projectId } = (await project.json()) as { id: string };
    const created = await page.request.post(`${organisation}/projects/${projectId}/agents`, { data: { name: "HR helper" } });
    const { id: agentId, public_id: publicId } = (await created.json()) as { id: string; public_id: string };
    const agentApi = `${organisation}/projects/${projectId}/agents/${agentId}`;
    expect(
      (await page.request.patch(`${agentApi}/operational-settings`, { data: { allowed_origins: [new URL(HOST_URL).origin] } })).status(),
    ).toBe(200);
    expect((await page.request.post(`${agentApi}/versions`, { data: { note: "First release" } })).status()).toBe(201);
    // Playground use of the same Agent is left out of its KPIs.
    const playground = await page.request.post(`${agentApi}/playground/conversations`);
    expect(playground.status()).toBe(201);
    const { id: tryId } = (await playground.json()) as { id: string };
    const tried = await page.request.post(`${agentApi}/playground/conversations/${tryId}/messages`, {
      data: { content: "Testing the Draft before Visitors see it" },
    });
    expect(tried.status()).toBe(200);
    expect(await tried.text()).toContain("event: done");

    // A Visitor asks two questions, gives one reply a thumbs up and the other a thumbs down, and rates the chat 2.
    const visitor = await browser.newContext();
    const host = await visitor.newPage();
    await host.goto(`${HOST_URL}/?agent=${publicId}&launcher=inline`);
    const widget = host.frameLocator('iframe[title="Chat"]');
    const replies = widget.getByRole("log", { name: "Conversation" }).getByRole("listitem", { name: "HR helper" });
    for (const [count, question] of ["How many days of annual leave do I get?", "Can I carry leave over?"].entries()) {
      await widget.getByLabel("Message").fill(question);
      await widget.getByRole("button", { name: "Send" }).click();
      await expect(replies).toHaveCount(count + 1, { timeout: 15_000 });
      await expect(widget.getByRole("button", { name: "Send" })).toBeEnabled({ timeout: 15_000 });
    }
    const thumbs = (n: number) => replies.nth(n).getByRole("group", { name: "Was this reply helpful?" });
    await thumbs(0).getByRole("button", { name: "Helpful", exact: true }).click();
    await expect(thumbs(0).getByRole("button", { name: "Helpful", exact: true })).toHaveAttribute("aria-pressed", "true");
    await thumbs(1).getByRole("button", { name: "Not helpful" }).click();
    await expect(thumbs(1).getByRole("button", { name: "Not helpful" })).toHaveAttribute("aria-pressed", "true");
    await widget.getByRole("button", { name: "End chat" }).click();
    await widget.getByRole("group", { name: /Before you go/ }).getByRole("button", { name: "2 out of 5" }).click();
    // The thumbs leave their own "Thanks for your feedback." notices beside the end's.
    await expect(widget.getByRole("status").filter({ hasText: "You ended the chat." })).toHaveCount(1);
    await visitor.close();

    // The Editor reads the Live Version's KPIs, today's partial day included.
    await page.goto(`/organisations/${organisationId}/projects/${projectId}/analytics`);
    await expect(page.getByLabel("Agent")).toHaveValue(agentId);
    await expect(page.getByRole("combobox", { name: /^Version/ })).toHaveText("v1 (Live)");
    const card = (name: string) => page.getByRole("list", { name: "Key numbers for v1" }).getByRole("listitem", { name });
    await expect(card("Volume")).toContainText("1 Conversation", { timeout: 15_000 });
    await expect(card("Volume")).toContainText("2 replies");
    await expect(card("Volume").getByText("Low sample")).toHaveAttribute("title", "Fewer than 30 Conversations");
    await expect(card("Thumbs-up rate")).toContainText("50%");
    await expect(card("Thumbs-up rate")).toContainText("95% interval 9% to 91%");
    await expect(card("Thumbs-up rate")).toContainText("n = 2 votes (1 up, 1 down)");
    await expect(card("Thumbs-up rate").getByText("Low sample")).toHaveAttribute("title", "Fewer than 30 votes");
    await expect(card("Mean rating")).toContainText("2.0 of 5");
    await expect(card("Mean rating")).toContainText("n = 1 rating");
    // The Project has no Documents, so every reply is the fallback text and asks no model.
    await expect(card("Fallback rate")).toContainText("100%");
    await expect(card("Fallback rate")).toContainText("2 of 2 replies were the fallback text");
    await expect(card("Tokens per reply")).toContainText("n = 0 replies that asked a model");
    await expect(card("p95 latency")).toContainText("n = 2 replies");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });
});
