import AxeBuilder from "@axe-core/playwright";

import { AXE_TAGS, expect, test } from "../fixtures";
import { HOST_URL } from "../fixtures/env";

// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-e703";
const QUESTION = "How would you rate this chat?";

test.describe("Conversation Rating", () => {
  test("Visitors are asked to rate after the Nth reply and on End chat, can dismiss or change it; the Editor finds Conversations by rating", async ({
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
    const project = await page.request.post(`${organisation}/projects`, { data: { name: "Rating HR" } });
    const { id: projectId } = (await project.json()) as { id: string };
    const created = await page.request.post(`${organisation}/projects/${projectId}/agents`, { data: { name: "HR helper" } });
    const { id: agentId, public_id: publicId } = (await created.json()) as { id: string; public_id: string };
    const agentApi = `${organisation}/projects/${projectId}/agents/${agentId}`;
    expect(
      (await page.request.patch(`${agentApi}/operational-settings`, { data: { allowed_origins: [new URL(HOST_URL).origin] } })).status(),
    ).toBe(200);
    // The Live Version asks for a rating after the first reply.
    expect((await page.request.put(`${agentApi}/draft`, { data: { experience: { rating_prompt_after: 1 } } })).ok()).toBe(true);
    expect((await page.request.post(`${agentApi}/versions`, { data: { note: "First release" } })).status()).toBe(201);

    async function visit() {
      const context = await browser.newContext();
      const host = await context.newPage();
      await host.goto(`${HOST_URL}/?agent=${publicId}&launcher=inline`);
      const widget = host.frameLocator('iframe[title="Chat"]');
      const ask = async (question: string, replies: number) => {
        await widget.getByLabel("Message").fill(question);
        await widget.getByRole("button", { name: "Send" }).click();
        await expect(widget.getByRole("log", { name: "Conversation" }).getByRole("listitem", { name: "HR helper" })).toHaveCount(replies, {
          timeout: 15_000,
        });
        await expect(widget.getByRole("button", { name: "Send" })).toBeEnabled({ timeout: 15_000 });
      };
      return { context, host, widget, ask };
    }

    // The first Visitor is asked after the first reply, rates 2, then changes it to 4.
    const first = await visit();
    const prompt = first.widget.getByRole("group", { name: QUESTION });
    await expect(prompt).toHaveCount(0);
    await first.ask("How many days of annual leave do I get?", 1);
    await expect(prompt).toBeVisible();
    await prompt.getByRole("button", { name: "2 out of 5" }).click();
    await expect(first.widget.getByText("You rated this chat 2 out of 5.")).toBeVisible();
    await first.widget.getByRole("button", { name: "Change rating" }).click();
    await prompt.getByRole("button", { name: "4 out of 5" }).click();
    await expect(first.widget.getByText("You rated this chat 4 out of 5.")).toBeVisible();
    await first.widget.getByRole("button", { name: "Change rating" }).click();
    // The whole host page, the widget iframe and its rating prompt included.
    expect((await new AxeBuilder({ page: first.host }).withTags(AXE_TAGS).analyze()).violations).toEqual([]);
    await first.widget.getByRole("button", { name: "Cancel" }).click();
    // After a reload the rating is still there, and the prompt isn't shown again.
    await first.host.reload();
    await expect(first.widget.getByText("You rated this chat 4 out of 5.")).toBeVisible({ timeout: 15_000 });
    await expect(prompt).toHaveCount(0);
    await first.context.close();

    // The second Visitor dismisses the prompt; it stays away, even after a reload, until they end the chat.
    const second = await visit();
    await second.ask("Can I carry leave over?", 1);
    await second.widget.getByRole("button", { name: "Not now" }).click();
    await expect(second.widget.getByRole("group", { name: QUESTION })).toHaveCount(0);
    await second.host.reload();
    await expect(second.widget.getByRole("log", { name: "Conversation" }).getByRole("listitem", { name: "HR helper" })).toHaveCount(1, {
      timeout: 15_000,
    });
    await second.ask("And sick days?", 2);
    await expect(second.widget.getByRole("group", { name: QUESTION })).toHaveCount(0);
    await second.widget.getByRole("button", { name: "End chat" }).click();
    const onEnd = second.widget.getByRole("group", { name: `Before you go: ${QUESTION}` });
    await expect(onEnd.getByRole("button", { name: "1 out of 5" })).toBeFocused();
    expect((await new AxeBuilder({ page: second.host }).withTags(AXE_TAGS).analyze()).violations).toEqual([]);
    await onEnd.getByRole("button", { name: "1 out of 5" }).click();
    await expect(second.widget.getByRole("status")).toHaveText("You ended the chat.");
    await second.context.close();

    // The Editor sees each Conversation's rating, filters by it, and reads the change log.
    await page.goto(`/organisations/${organisationId}/projects/${projectId}/conversations`);
    const filters = page.getByRole("group", { name: "Filter Conversations" });
    const table = page.getByRole("table", { name: "Conversations" });
    const loved = table.getByRole("row", { name: /How many days of annual leave/ });
    const unhappy = table.getByRole("row", { name: /Can I carry leave over/ });
    await expect(loved.getByRole("cell").nth(6)).toHaveText("4 of 5", { timeout: 15_000 });
    await expect(unhappy.getByRole("cell").nth(6)).toHaveText("1 of 5");
    await filters.getByLabel("Rating").selectOption("1 of 5");
    await expect(page).toHaveURL(/rating=1/);
    await expect(loved).toHaveCount(0);
    await expect(unhappy).toHaveCount(1);
    await filters.getByLabel("Rating").selectOption("Not rated");
    await expect(page.getByText("No Conversations match these filters.")).toBeVisible();
    await filters.getByLabel("Rating").selectOption("4 of 5");
    await expect(loved).toHaveCount(1);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    await loved.getByRole("link", { name: "How many days of annual leave do I get?" }).click();
    const rating = page.getByRole("region", { name: "Conversation Rating" });
    await expect(rating).toContainText("Rated 4 of 5 · for Agent Version v1");
    const changes = rating.getByRole("list", { name: "Rating changes" }).getByRole("listitem");
    await expect(changes).toHaveCount(2);
    await expect(changes.nth(0)).toContainText("Rated 2 · for Agent Version v1");
    await expect(changes.nth(1)).toContainText("Changed from 2 to 4 · for Agent Version v1");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });
});
