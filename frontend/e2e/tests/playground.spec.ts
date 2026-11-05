import { fileURLToPath } from "node:url";

import { expect, test } from "../fixtures";

/** The seed staff handbook (synthetic content), uploaded as an Editor would. */
const HANDBOOK = fileURLToPath(new URL("../../../seed/documents/northwind-staff-handbook.md", import.meta.url));
// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-p9q2";

test.describe("Agent and Playground", () => {
  test("an Owner creates an Agent, asks its Draft a question and the answer streams in", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    // Ingestion, two axe scans and a streamed answer: more than the default 30 seconds.
    test.setTimeout(120_000);
    // The Organisation's Default Model, set through the API (the Models page has its own test).
    await page.goto("/");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const organisation = `/api/organisations/${me.organisations[0]?.id ?? ""}`;
    const credential = await page.request.post(`${organisation}/credentials`, {
      data: { name: "Support Claude", provider: "anthropic", api_key: CHAT_KEY },
    });
    expect(credential.status()).toBe(201);
    const { id } = (await credential.json()) as { id: string };
    const chosen = await page.request.put(`${organisation}/default-model`, {
      data: { credential_id: id, model: "claude-haiku-4-5" },
    });
    expect(chosen.status()).toBe(200);

    // A Project whose Knowledge Base holds the seed handbook.
    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Projects" }).click();
    const newProject = page.getByRole("form", { name: "New Project" });
    await newProject.getByLabel("Name").fill("Northwind HR");
    await newProject.getByRole("button", { name: "Create Project" }).click();
    await page.getByLabel("Choose files to upload").setInputFiles(HANDBOOK);
    const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /northwind-staff-handbook\.md/ });
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });

    // Create the Agent and write its system prompt.
    await page.getByRole("navigation", { name: "Project" }).getByRole("link", { name: "Agents" }).click();
    await expect(page.getByText(/No Agents yet/)).toBeVisible({ timeout: 15_000 });
    const newAgent = page.getByRole("form", { name: "New Agent" });
    await newAgent.getByLabel("Name").fill("HR helper");
    await newAgent.getByRole("button", { name: "Create Agent" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "HR helper" })).toBeVisible({ timeout: 15_000 });
    await page.getByLabel("System prompt").fill("You answer Northwind staff questions about HR policy.");
    await page.getByRole("button", { name: "Save Draft" }).click();
    await expect(page.getByText("Draft saved")).toBeVisible({ timeout: 15_000 });
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // Ask the Draft; the fake model's answer streams back and is saved with its usage.
    await page.getByLabel("Question").fill("How many days of annual leave do I get?");
    await page.getByRole("button", { name: "Send" }).click();
    const messages = page.getByRole("list", { name: "Playground messages" });
    await expect(messages.getByRole("listitem", { name: "You" })).toHaveText("How many days of annual leave do I get?");
    const answer = messages.getByRole("listitem", { name: "HR helper" });
    await expect(answer).toContainText("Fake reply from anthropic:claude-haiku-4-5.", { timeout: 15_000 });
    await expect(answer).toContainText(/\d+ input and \d+ output tokens · \d+ ms/);
    // The fake model cites the first Chunk it is given: a chip links to it in the Document viewer.
    const chip = answer.getByRole("list", { name: "Sources" }).getByRole("link", { name: /^C1 northwind-staff-handbook\.md$/ });
    await expect(chip).toHaveAttribute("href", /\/projects\/[0-9a-f-]+\/documents\/[0-9a-f-]+#chunk-[0-9a-f-]+$/);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The Trace shows the model, usage, cost, latency and the Chunks retrieved, the cited one first.
    await answer.getByRole("button", { name: "Trace" }).click();
    const trace = page.getByRole("dialog", { name: "Trace" });
    await expect(trace.getByText("anthropic · claude-haiku-4-5")).toBeVisible({ timeout: 15_000 });
    await expect(trace.getByText(/^\d+ input · \d+ output$/)).toBeVisible();
    await expect(trace.getByText(/^\$\d/)).toBeVisible();
    await expect(trace.getByText(/ms to the first token · \d+ ms in all/)).toBeVisible();
    const firstChunk = trace.getByRole("table", { name: "Retrieved Chunks" }).getByRole("row").nth(1);
    await expect(firstChunk.getByRole("cell").first()).toHaveText("C1");
    await expect(firstChunk.getByRole("cell").last()).toHaveText("Cited");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await trace.getByRole("button", { name: "Close" }).click();
    await expect(trace).toBeHidden();

    // The reload keeps the Draft.
    await page.reload();
    await expect(page.getByLabel("System prompt")).toHaveValue("You answer Northwind staff questions about HR policy.", { timeout: 15_000 });
  });
});
