import { fileURLToPath } from "node:url";

import { expect, test } from "../fixtures";
import { openSection } from "../fixtures/navigation";

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
    await openSection(page, "Organisation sections", "Settings");
    await openSection(page, "Organisation settings", "Credentials");
    const add = page.getByRole("region", { name: "Add a credential" });
    await add.getByLabel("Provider").selectOption("Voyage AI");
    await add.getByLabel("Name").fill("Search embeddings");
    await add.getByLabel("API key").fill(EMBEDDINGS_KEY);
    await add.getByRole("button", { name: "Check and save" }).click();
    await expect(page.getByText("Search embeddings was checked and saved.")).toBeVisible();

    await openSection(page, "Organisation sections", "Projects");
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

    // The worker embeds the upload with the chosen model; changing it now would re-embed.
    await page.getByLabel("Choose files to upload").setInputFiles(HANDBOOK);
    const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /northwind-staff-handbook\.md/ });
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    await page.reload();
    await expect(setting).toContainText("Changing it re-embeds every Document in the background");

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
    await openSection(page, "Organisation sections", "Settings");
    await openSection(page, "Organisation settings", "Credentials");
    await page.getByRole("button", { name: "Delete: Search embeddings" }).click();
    await page.getByRole("button", { name: "Yes, delete Search embeddings" }).click();
    await expect(page.getByText("Voyage handbook (Embedding Model voyage-3.5)")).toBeVisible();
  });

  test("changing the model of a Project with Documents re-embeds it in the background and switches over", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    await openSection(page, "Organisation sections", "Settings");
    await openSection(page, "Organisation settings", "Credentials");
    const add = page.getByRole("region", { name: "Add a credential" });
    await add.getByLabel("Provider").selectOption("Voyage AI");
    await add.getByLabel("Name").fill("Re-embed target");
    await add.getByLabel("API key").fill(EMBEDDINGS_KEY);
    await add.getByRole("button", { name: "Check and save" }).click();
    await expect(page.getByText("Re-embed target was checked and saved.")).toBeVisible();

    // A Project on the built-in model, with the handbook Ready.
    await openSection(page, "Organisation sections", "Projects");
    const form = page.getByRole("form", { name: "New Project" });
    await form.getByLabel("Name").fill("Re-embedded handbook");
    await form.getByRole("button", { name: "Create Project" }).click();
    await page.getByLabel("Choose files to upload").setInputFiles(HANDBOOK);
    const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /northwind-staff-handbook\.md/ });
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    const [, organisationId, projectId] = /organisations\/([^/]+)\/projects\/([^/]+)/.exec(page.url()) ?? [];
    const project = `/api/organisations/${organisationId ?? ""}/projects/${projectId ?? ""}`;
    const probe = async () => {
      const response = await page.request.post(`${project}/retrieval-probe`, { data: { query: "annual leave", top_k: 3 } });
      expect(response.status()).toBe(200);
      return (await response.json()) as Probe;
    };
    expect((await probe()).embedding_model_id).toBe("multilingual-e5-small");

    await page.reload();
    const setting = page.getByRole("region", { name: "Embedding Model" });
    await expect(setting).toContainText("Changing it re-embeds every Document in the background");
    await setting.getByRole("button", { name: "Change Embedding Model" }).click();
    const choose = setting.getByRole("form", { name: "Choose the Embedding Model" });
    await choose.getByLabel("Embedding Model").selectOption("voyage-3.5 (Re-embed target)");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await choose.getByRole("button", { name: "Use this model" }).click();

    // The worker re-embeds every Chunk, then switches; the Studio polls until it has.
    await expect(setting).toContainText("Documents are embedded with voyage-3.5.", { timeout: 60_000 });
    await expect(setting.getByRole("status")).toHaveCount(0);
    const state = await page.request.get(`${project}/embedding-model`);
    const reEmbed = ((await state.json()) as { re_embed: { status: string; embedded_chunks: number; total_chunks: number } }).re_embed;
    expect(reEmbed.status).toBe("completed");
    expect(reEmbed.embedded_chunks).toBe(reEmbed.total_chunks);
    expect(reEmbed.total_chunks).toBeGreaterThan(1);
    const answer = await probe();
    expect([answer.embedding_model_id, answer.dimension]).toEqual(["voyage-3.5", 1024]);
    expect(answer.chunks.map((chunk) => chunk.document_name)).toEqual(Array(3).fill("northwind-staff-handbook.md"));
    // The Documents table counts each Chunk once.
    await expect(row).toBeVisible();

    // The change is in the Audit log.
    const events = await page.request.get(`/api/organisations/${organisationId ?? ""}/audit-events`, {
      params: { action: "project.re_embed_started" },
    });
    expect(((await events.json()) as { total: number }).total).toBe(1);
  });
});
