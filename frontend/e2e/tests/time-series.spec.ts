import { fileURLToPath } from "node:url";

import { expect, test } from "../fixtures";
import { HOST_URL } from "../fixtures/env";

// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-e706";
/** The seed staff handbook (synthetic content), uploaded as an Editor would. */
const HANDBOOK = fileURLToPath(new URL("../../../seed/documents/northwind-staff-handbook.md", import.meta.url));

test.describe("Time series", () => {
  test("the Editor sees a Visitor's Conversation over time, markers where the Live Version changed, and a confounder note once a Document is added", async ({
    signedInPage: page,
    makeAxeBuilder,
    browser,
  }) => {
    test.setTimeout(240_000);
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
    const project = await page.request.post(`${organisation}/projects`, { data: { name: "Series HR" } });
    const { id: projectId } = (await project.json()) as { id: string };
    const created = await page.request.post(`${organisation}/projects/${projectId}/agents`, { data: { name: "HR helper" } });
    const { id: agentId, public_id: publicId } = (await created.json()) as { id: string; public_id: string };
    const agentApi = `${organisation}/projects/${projectId}/agents/${agentId}`;
    expect(
      (await page.request.patch(`${agentApi}/operational-settings`, { data: { allowed_origins: [new URL(HOST_URL).origin] } })).status(),
    ).toBe(200);
    // Publish v1, publish v2, revert to v1: three Live History entries, today.
    expect((await page.request.post(`${agentApi}/versions`, { data: { note: "First release" } })).status()).toBe(201);
    expect((await page.request.post(`${agentApi}/versions`, { data: { note: "Second release" } })).status()).toBe(201);
    expect((await page.request.post(`${agentApi}/revert`)).status()).toBe(200);

    // A Visitor asks a question on the host page.
    const visitor = await browser.newContext();
    const host = await visitor.newPage();
    await host.goto(`${HOST_URL}/?agent=${publicId}&launcher=inline`);
    const widget = host.frameLocator('iframe[title="Chat"]');
    await widget.getByLabel("Message").fill("How many days of annual leave do I get?");
    await widget.getByRole("button", { name: "Send" }).click();
    await expect(widget.getByRole("log", { name: "Conversation" }).getByRole("listitem", { name: "HR helper" })).toHaveCount(1, {
      timeout: 15_000,
    });
    // The reply is saved once it has finished streaming.
    await expect(widget.getByRole("button", { name: "Send" })).toBeEnabled({ timeout: 15_000 });
    await visitor.close();

    // The Editor reads the time series: today's Conversation, the three changes marked, no confounder yet.
    await page.goto(`/organisations/${organisationId}/projects/${projectId}/analytics`);
    const section = page.getByRole("region", { name: "Over time" });
    await expect(section.getByLabel("Metric")).toHaveValue("conversations");
    await expect(section.getByLabel("Granularity")).toHaveValue("day");
    const table = section.getByRole("table", { name: "Conversations, the numbers behind the chart" });
    // The last 30 days, one row each (and the header); today's has the Visitor's Conversation.
    await expect(table.getByRole("row")).toHaveCount(31, { timeout: 15_000 });
    const cells = (row: number) => table.getByRole("row").nth(row).getByRole("cell");
    await expect(cells(30)).toHaveText(["1", "1"]);
    await expect(cells(29)).toHaveText(["0", "0"]);
    const changes = section.getByRole("list", { name: "Live Version changes" }).getByRole("listitem");
    await expect(changes).toHaveCount(3);
    await expect(changes.nth(0)).toContainText("v1 published");
    await expect(changes.nth(1)).toContainText("v2 published (from v1)");
    await expect(changes.nth(2)).toContainText("v1 reverted to (from v2)");
    // All three changes were today: one dashed line on today's point, labelled with each Version made Live.
    await expect(section.locator(".recharts-reference-line")).toHaveCount(1);
    await expect(section.locator(".recharts-reference-line")).toContainText("v1, v2, v1");
    await expect(section.getByRole("note")).toHaveCount(0);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // By month: the range's months, the last holding the Conversation.
    await section.getByLabel("Granularity").selectOption("Month");
    await expect(section.getByText(/Conversations per month, from/)).toBeVisible({ timeout: 15_000 });
    await expect(table.getByRole("row")).not.toHaveCount(31);
    await expect(table.getByRole("row").last().getByRole("cell")).toHaveText(["1", "1"]);

    // An Editor adds a Document: the period now carries the confounder note.
    await page.goto(`/organisations/${organisationId}/projects/${projectId}`);
    await page.getByLabel("Choose files to upload").setInputFiles(HANDBOOK);
    await expect(page.getByRole("list", { name: "Uploads" }).getByText("Uploaded")).toBeVisible();
    await page.goto(`/organisations/${organisationId}/projects/${projectId}/analytics`);
    await expect(section.getByRole("note")).toContainText("Documents changed during this period: 1 added, replaced or processed again.", {
      timeout: 15_000,
    });
    await expect(section.getByRole("note")).toContainText("may confound the comparison");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });
});
