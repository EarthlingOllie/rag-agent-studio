import type { Page } from "@playwright/test";

import { expect, test } from "../fixtures";

// The compose stack checks keys with the fake verifier, answers with the fake gateway's chat
// model and reranks with its fake reranker (a passage scores the share of the question's words
// it has). No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-r5k3";
const RERANK_KEY = "pa-e2e-test-only-not-a-real-key-r2n6";

const PRODUCT = "Model SKU-4471 ships with a two-year warranty.";
const LEAVE = "Everyone gets 25 days of annual leave a year.";
// Its words are what, warranty, does, sku and have: PRODUCT has two of the five.
const QUESTION = "What warranty does SKU-4471 have?";

/** Waits for the next Draft save and checks the API accepted it. */
async function nextSave(page: Page) {
  const response = await page.waitForResponse((r) => r.url().endsWith("/draft") && r.request().method() === "PUT");
  expect(response.status()).toBe(200);
}

test.describe("Reranker", () => {
  test("an Editor turns on a reranker and the best Chunk rises to the top", async ({ signedInPage: page, makeAxeBuilder }) => {
    test.setTimeout(120_000);
    // A Default Model, a Voyage credential that can rerank, a Project and an Agent, through the API.
    await page.goto("/");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const organisationId = me.organisations[0]?.id ?? "";
    const organisation = `/api/organisations/${organisationId}`;
    const add = async (data: object) => {
      const response = await page.request.post(`${organisation}/credentials`, { data });
      expect(response.status()).toBe(201);
      return ((await response.json()) as { id: string }).id;
    };
    const claude = await add({ name: "Support Claude", provider: "anthropic", api_key: CHAT_KEY });
    const voyage = await add({ name: "Search Voyage", provider: "voyage", api_key: RERANK_KEY });
    const chosen = await page.request.put(`${organisation}/default-model`, { data: { credential_id: claude, model: "claude-haiku-4-5" } });
    expect(chosen.status()).toBe(200);
    const project = await page.request.post(`${organisation}/projects`, { data: { name: "Northwind support" } });
    const projectId = ((await project.json()) as { id: string }).id;
    const agent = await page.request.post(`${organisation}/projects/${projectId}/agents`, { data: { name: "Support helper" } });
    const agentId = ((await agent.json()) as { id: string }).id;

    // Two one-Chunk Documents, uploaded as an Editor would.
    await page.goto(`/organisations/${organisationId}/projects/${projectId}`);
    await page.getByLabel("Choose files to upload").setInputFiles([
      { name: "product.txt", mimeType: "text/plain", buffer: Buffer.from(PRODUCT) },
      { name: "leave.txt", mimeType: "text/plain", buffer: Buffer.from(LEAVE) },
    ]);
    const documents = page.getByRole("table", { name: "Documents" });
    for (const name of [/product\.txt/, /leave\.txt/]) {
      await expect(documents.getByRole("row", { name }).getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    }

    // Retrieval: one Chunk per answer (the minimum relevance stays at its default, 0), and the
    // Voyage reranker.
    await page.goto(`/organisations/${organisationId}/projects/${projectId}/agents/${agentId}`);
    const status = page.getByRole("status", { name: "Draft status" });
    await expect(status).toHaveText("All changes saved", { timeout: 15_000 });
    const retrieval = page.getByRole("group", { name: "Retrieval" });
    let save = nextSave(page);
    await retrieval.getByLabel("Chunks per answer (top-k)").fill("1");
    await save;
    await expect(retrieval.getByLabel("Minimum relevance (0 to 1)")).toHaveValue("0");
    const reranker = retrieval.getByRole("group", { name: "Reranker" });
    await reranker.getByLabel("Credential").selectOption({ label: "Search Voyage (Voyage AI)" });
    save = nextSave(page);
    await reranker.getByLabel("Model").selectOption("rerank-2.5");
    await save;
    await expect(status).toHaveText("All changes saved");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The reranker's credential is a Credential reference now, so it can't be deleted.
    const deleted = await page.request.delete(`${organisation}/credentials/${voyage}`);
    expect(deleted.status()).toBe(409);
    expect(((await deleted.json()) as { references: unknown[] }).references).toEqual([
      { kind: "agent", id: agentId, name: "Support helper (reranker)" },
    ]);

    // Ask; the Trace shows the reranked product Chunk given to the model, with the reranker's
    // relevance, and the leave Chunk left out by top-k.
    await page.getByLabel("Question", { exact: true }).fill(QUESTION);
    await page.getByRole("button", { name: "Send" }).click();
    const answer = page.getByRole("list", { name: "Playground messages" }).getByRole("listitem", { name: "Support helper" });
    await expect(answer).toContainText("Fake reply from anthropic:claude-haiku-4-5.", { timeout: 15_000 });
    await answer.getByRole("button", { name: "Trace" }).click();
    const trace = page.getByRole("dialog", { name: "Trace" });
    const rows = trace.getByRole("table", { name: "Retrieved Chunks" }).getByRole("row");
    await expect(rows).toHaveCount(3, { timeout: 15_000 });
    const given = rows.nth(1).getByRole("cell");
    await expect(given.nth(0)).toHaveText("C1");
    await expect(given.nth(1)).toHaveText("product.txt");
    await expect(given.nth(4)).toHaveText("0.400");
    const leftOut = rows.nth(2).getByRole("cell");
    await expect(leftOut.nth(1)).toHaveText("leave.txt");
    await expect(leftOut.nth(4)).toHaveText("0.000");
  });
});
