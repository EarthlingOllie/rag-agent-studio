import { readFile } from "node:fs/promises";

import { expect, test } from "../fixtures";
import { HOST_URL } from "../fixtures/env";

// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-e705";

test.describe("Version comparison", () => {
  test("an Editor compares two Versions side by side with the config diff, and exports the comparison as CSV", async ({
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
    const project = await page.request.post(`${organisation}/projects`, { data: { name: "Comparison HR" } });
    const { id: projectId } = (await project.json()) as { id: string };
    const created = await page.request.post(`${organisation}/projects/${projectId}/agents`, { data: { name: "HR helper" } });
    const { id: agentId, public_id: publicId } = (await created.json()) as { id: string; public_id: string };
    const agentApi = `${organisation}/projects/${projectId}/agents/${agentId}`;
    expect(
      (await page.request.patch(`${agentApi}/operational-settings`, { data: { allowed_origins: [new URL(HOST_URL).origin] } })).status(),
    ).toBe(200);
    const publish = async (system_prompt: string, note: string) => {
      expect((await page.request.put(`${agentApi}/draft`, { data: { behaviour: { system_prompt } } })).ok()).toBe(true);
      expect((await page.request.post(`${agentApi}/versions`, { data: { note } })).status()).toBe(201);
    };

    // A Visitor chats with v1 and finds it helpful; then with v2 (a new system prompt), which they don't.
    const visitorChat = async (question: string, button: "Helpful" | "Not helpful") => {
      const visitor = await browser.newContext();
      const host = await visitor.newPage();
      await host.goto(`${HOST_URL}/?agent=${publicId}&launcher=inline`);
      const widget = host.frameLocator('iframe[title="Chat"]');
      const replies = widget.getByRole("log", { name: "Conversation" }).getByRole("listitem", { name: "HR helper" });
      await widget.getByLabel("Message").fill(question);
      await widget.getByRole("button", { name: "Send" }).click();
      await expect(replies).toHaveCount(1, { timeout: 15_000 });
      await expect(widget.getByRole("button", { name: "Send" })).toBeEnabled({ timeout: 15_000 });
      const thumbs = replies.nth(0).getByRole("group", { name: "Was this reply helpful?" });
      await thumbs.getByRole("button", { name: button, exact: true }).click();
      await expect(thumbs.getByRole("button", { name: button, exact: true })).toHaveAttribute("aria-pressed", "true");
      await visitor.close();
    };
    await publish("Answer from the handbook.", "First release");
    await visitorChat("How many days of annual leave do I get?", "Helpful");
    await publish("Answer in one sentence.", "Shorter answers");
    await visitorChat("Can I carry leave over?", "Not helpful");

    // The Editor compares the two Versions (today's partial day included).
    await page.goto(`/organisations/${organisationId}/projects/${projectId}/analytics`);
    await expect(page.getByLabel("First Version").locator("option:checked")).toHaveText("v1");
    await expect(page.getByLabel("Second Version").locator("option:checked")).toHaveText("v2 (Live)");
    const table = page.getByRole("table", { name: "v1 compared with v2" });
    const row = (metric: string) => table.getByRole("row").filter({ has: page.getByRole("rowheader", { name: metric }) });
    await expect(row("Thumbs-up rate (small sample)")).toContainText("100%", { timeout: 15_000 });
    await expect(row("Thumbs-up rate (small sample)").getByRole("cell")).toHaveText(["100%", "0%", "−100 pts", "v1"]);
    await expect(row("Conversations (small sample)").getByRole("cell")).toHaveText(["1", "1", "Same", ""]);
    await expect(row("Votes (small sample)").getByRole("cell")).toHaveText(["1", "1", "Same", ""]);
    const changes = page.getByRole("region", { name: "Configuration changes" });
    await expect(changes.getByText("Behaviour › System prompt")).toBeVisible();
    await expect(changes.getByRole("list", { name: "Behaviour › System prompt changes" })).toContainText("Answer in one sentence.");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // A date range with no Visitor use leaves nothing to compare.
    await page.getByLabel("From (UTC)").fill("2026-01-01");
    await page.getByLabel("To (UTC)").fill("2026-01-02");
    await expect(row("Conversations (small sample)").getByRole("cell")).toHaveText(["0", "0", "Same", ""]);
    await page.getByLabel("From (UTC)").fill("");
    await page.getByLabel("To (UTC)").fill("");
    await expect(row("Conversations (small sample)").getByRole("cell")).toHaveText(["1", "1", "Same", ""]);

    // The CSV export downloads the same comparison.
    const downloading = page.waitForEvent("download");
    await page.getByRole("link", { name: "Export as CSV" }).click();
    const download = await downloading;
    expect(download.suggestedFilename()).toMatch(/^comparison-v1-v2-\d{4}-\d{2}-\d{2}-to-\d{4}-\d{2}-\d{2}\.csv$/);
    const lines = (await readFile(await download.path(), "utf8")).trim().split("\n");
    expect(lines[0]).toBe("Metric,v1,v2,Difference (v2 - v1),Better");
    expect(lines).toContain("Thumbs-up rate,1.0000,0.0000,-1.0000,v1");
    expect(lines).toContain("Conversations,1,1,0,");
  });
});
