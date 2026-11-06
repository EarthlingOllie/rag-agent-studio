import { fileURLToPath } from "node:url";

import { expect, test } from "../fixtures";

// The compose stack checks keys with the fake verifier and calls provider models through the
// gateway's offline fakes, in the API and the worker. No real provider is called.
const EMBEDDINGS_KEY = "pa-e2e-test-only-not-a-real-key-e9d2";
const HANDBOOK = fileURLToPath(new URL("../../../seed/documents/northwind-staff-handbook.md", import.meta.url));

interface Probe {
  embedding_model_id: string;
  dimension: number;
  chunks: { document_name: string; score: number }[];
}

test.describe("Embedding Models", () => {
  test("an Owner chooses a Voyage Embedding Model; the handbook embeds with it and its credential can't be deleted", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Organisation settings" }).click();
    await page.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: "Credentials" }).click();
    const add = page.getByRole("region", { name: "Add a credential" });
    await add.getByLabel("Provider").selectOption("Voyage AI");
    await add.getByLabel("Name").fill("Search embeddings");
    await add.getByLabel("API key").fill(EMBEDDINGS_KEY);
    await add.getByRole("button", { name: "Check and save" }).click();
    await expect(page.getByText("Search embeddings was checked and saved.")).toBeVisible();

    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Projects" }).click();
    const form = page.getByRole("form", { name: "New Project" });
    await form.getByLabel("Name").fill("Voyage handbook");
    await form.getByRole("button", { name: "Create Project" }).click();
    const setting = page.getByRole("region", { name: "Embedding Model" });
    await expect(setting).toContainText("Documents are embedded with multilingual-e5-small.");

    await setting.getByRole("button", { name: "Change Embedding Model" }).click();
    const choose = setting.getByRole("form", { name: "Choose the Embedding Model" });
    await expect(choose.getByLabel("Embedding Model").getByRole("option")).toHaveText([
      "multilingual-e5-small (built in)",
      "voyage-3.5 (Search embeddings)",
      "voyage-3.5-lite (Search embeddings)",
      "voyage-multilingual-2 (Search embeddings)",
    ]);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await choose.getByLabel("Embedding Model").selectOption("voyage-3.5 (Search embeddings)");
    await choose.getByRole("button", { name: "Use this model" }).click();
    await expect(setting).toContainText("Documents are embedded with voyage-3.5.");

    // The worker embeds the upload with the chosen model; then the model is fixed.
    await page.getByLabel("Choose files to upload").setInputFiles(HANDBOOK);
    const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /northwind-staff-handbook\.md/ });
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    await page.reload();
    await expect(setting).toContainText("It can't be changed while the Project has Documents.");
    await expect(setting.getByRole("button")).toHaveCount(0);

    // The retrieval probe finds the handbook's Chunks by their Voyage vectors.
    const [, organisationId, projectId] = /organisations\/([^/]+)\/projects\/([^/]+)/.exec(page.url()) ?? [];
    const probe = await page.request.post(`/api/organisations/${organisationId ?? ""}/projects/${projectId ?? ""}/retrieval-probe`, {
      data: { query: "annual leave", top_k: 3 },
    });
    expect(probe.status()).toBe(200);
    const answer = (await probe.json()) as Probe;
    expect([answer.embedding_model_id, answer.dimension]).toEqual(["voyage-3.5", 1024]);
    expect(answer.chunks).toHaveLength(3);
    expect(answer.chunks.map((chunk) => chunk.document_name)).toEqual(Array(3).fill("northwind-staff-handbook.md"));

    // The Project's credential is a reference: deleting it is refused and says why.
    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Organisation settings" }).click();
    await page.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: "Credentials" }).click();
    await page.getByRole("button", { name: "Delete: Search embeddings" }).click();
    await page.getByRole("button", { name: "Yes, delete Search embeddings" }).click();
    await expect(page.getByText("Voyage handbook (Embedding Model voyage-3.5)")).toBeVisible();
  });
});
