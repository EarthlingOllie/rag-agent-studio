import AxeBuilder from "@axe-core/playwright";

import { AXE_TAGS, expect, test } from "../fixtures";
import { HOST_URL } from "../fixtures/env";

// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-e702";

test.describe("Message Feedback", () => {
  test("a Visitor gives a reply a thumbs down with a comment and changes it; the Editor finds it by its feedback in the Conversations viewer", async ({
    signedInPage: page,
    makeAxeBuilder,
    browser,
  }) => {
    test.setTimeout(150_000);
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
    const project = await page.request.post(`${organisation}/projects`, { data: { name: "Feedback HR" } });
    const { id: projectId } = (await project.json()) as { id: string };
    const created = await page.request.post(`${organisation}/projects/${projectId}/agents`, { data: { name: "HR helper" } });
    const { id: agentId, public_id: publicId } = (await created.json()) as { id: string; public_id: string };
    const agentApi = `${organisation}/projects/${projectId}/agents/${agentId}`;
    expect(
      (await page.request.patch(`${agentApi}/operational-settings`, { data: { allowed_origins: [new URL(HOST_URL).origin] } })).status(),
    ).toBe(200);
    expect((await page.request.post(`${agentApi}/versions`, { data: { note: "First release" } })).status()).toBe(201);

    // A Visitor (another browser, no Studio session) chats on the demo host page.
    const visitor = await browser.newContext();
    const host = await visitor.newPage();
    await host.goto(`${HOST_URL}/?agent=${publicId}&launcher=inline`);
    const widget = host.frameLocator('iframe[title="Chat"]');
    await widget.getByLabel("Message").fill("How many days of annual leave do I get?");
    await widget.getByRole("button", { name: "Send" }).click();
    const reply = widget.getByRole("log", { name: "Conversation" }).getByRole("listitem", { name: "HR helper" });
    const thumbs = reply.getByRole("group", { name: "Was this reply helpful?" });
    await expect(thumbs).toBeVisible({ timeout: 15_000 });

    // Thumbs up, then changes their mind: thumbs down with a comment.
    await thumbs.getByRole("button", { name: "Helpful", exact: true }).click();
    await expect(thumbs.getByRole("button", { name: "Helpful", exact: true })).toHaveAttribute("aria-pressed", "true");
    await thumbs.getByRole("button", { name: "Not helpful" }).click();
    await expect(thumbs.getByRole("button", { name: "Not helpful" })).toHaveAttribute("aria-pressed", "true");
    await expect(thumbs.getByRole("button", { name: "Helpful", exact: true })).toHaveAttribute("aria-pressed", "false");
    await thumbs.getByRole("button", { name: "Add a comment" }).click();
    await reply.getByLabel("Comment (optional)").fill("Our contract says 30 days.");
    await reply.getByRole("button", { name: "Save comment" }).click();
    await expect(reply.getByText("“Our contract says 30 days.”")).toBeVisible();
    // `listitem` is left out: the widget's Message list (role="log" on its <ol>, from 06-01) predates
    // this ticket and is ticket 06-07's (WCAG 2.2 AA widget) to fix. Everything else, the feedback
    // controls included, must pass.
    const widgetAxe = new AxeBuilder({ page: host }).withTags(AXE_TAGS).disableRules(["listitem"]);
    expect((await widgetAxe.analyze()).violations).toEqual([]);

    // After a reload the feedback is still there.
    await host.reload();
    await expect(thumbs.getByRole("button", { name: "Not helpful" })).toHaveAttribute("aria-pressed", "true", { timeout: 15_000 });
    await expect(reply.getByText("“Our contract says 30 days.”")).toBeVisible();
    await visitor.close();

    // The Editor filters the Conversations by thumbs down and reads the feedback.
    await page.goto(`/organisations/${organisationId}/projects/${projectId}/conversations`);
    const filters = page.getByRole("group", { name: "Filter Conversations" });
    const table = page.getByRole("table", { name: "Conversations" });
    const row = table.getByRole("row", { name: /How many days of annual leave/ });
    await expect(row.getByRole("cell").nth(5)).toHaveText("1 down", { timeout: 15_000 });
    await filters.getByLabel("Feedback").selectOption("Thumbs up");
    await expect(page.getByText("No Conversations match these filters.")).toBeVisible();
    await filters.getByLabel("Feedback").selectOption("Thumbs down");
    await expect(row).toHaveCount(1);
    await expect(page).toHaveURL(/feedback=down/);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    await row.getByRole("link", { name: "How many days of annual leave do I get?" }).click();
    const feedback = page.getByRole("list", { name: "Messages" }).getByRole("group", { name: "Visitor feedback" });
    await expect(feedback).toContainText("Thumbs down · for Agent Version v1");
    await expect(feedback).toContainText("Our contract says 30 days.");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });
});
