import type { Page } from "@playwright/test";

import { expect, test } from "../fixtures";

// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-t4g5";

function markdown(name: string, text: string) {
  return { name, mimeType: "text/markdown", buffer: Buffer.from(text) };
}

function row(page: Page, name: string) {
  return page.getByRole("table", { name: "Documents" }).getByRole("row", { name: new RegExp(name.replace(".", "\\.")) });
}

test.describe("Tag scoping", () => {
  test("an Agent limited to a Tag is given only that material, and deleting the Tag warns which Agents use it", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    // Two uploads through the real worker, a streamed answer and two axe scans.
    test.setTimeout(120_000);
    await page.goto("/");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const organisationId = me.organisations[0]?.id ?? "";
    const organisation = `/api/organisations/${organisationId}`;
    const credential = await page.request.post(`${organisation}/credentials`, {
      data: { name: "Support Claude", provider: "anthropic", api_key: CHAT_KEY },
    });
    expect(credential.status()).toBe(201);
    const { id } = (await credential.json()) as { id: string };
    const chosen = await page.request.put(`${organisation}/default-model`, { data: { credential_id: id, model: "claude-haiku-4-5" } });
    expect(chosen.status()).toBe(200);
    const project = await page.request.post(`${organisation}/projects`, { data: { name: "Shared handbook" } });
    const projectId = ((await project.json()) as { id: string }).id;
    const projectApi = `${organisation}/projects/${projectId}`;

    // One Project holds HR and Sales material.
    await page.goto(`/organisations/${organisationId}/projects/${projectId}`);
    await page
      .getByLabel("Choose files to upload")
      .setInputFiles([
        markdown("leave-policy.md", "# Leave\n\nEveryone gets 25 days of annual leave a year."),
        markdown("price-list.md", "# Prices\n\nModel SKU-4471 ships with a two-year warranty."),
      ]);
    for (const name of ["leave-policy.md", "price-list.md"]) {
      await expect(row(page, name).getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    }
    const documents = (await (await page.request.get(`${projectApi}/documents`)).json()) as { id: string; name: string }[];
    const tag = async (name: string, documentName: string) => {
      const created = await page.request.post(`${projectApi}/tags`, { data: { name } });
      const tagId = ((await created.json()) as { id: string }).id;
      const documentId = documents.find((d) => d.name === documentName)?.id ?? "";
      const applied = await page.request.put(`${projectApi}/documents/${documentId}/tags`, { data: { tag_ids: [tagId] } });
      expect(applied.status()).toBe(200);
      return tagId;
    };
    const hr = await tag("HR", "leave-policy.md");
    await tag("Sales", "price-list.md");
    const agent = await page.request.post(`${projectApi}/agents`, { data: { name: "HR helper" } });
    const agentId = ((await agent.json()) as { id: string }).id;

    // The Editor limits the Agent to HR in its Retrieval settings.
    await page.goto(`/organisations/${organisationId}/projects/${projectId}/agents/${agentId}`);
    const scoping = page.getByRole("group", { name: "Tag scoping" });
    const saved = page.waitForResponse((r) => r.url().endsWith("/draft") && r.request().method() === "PUT");
    await scoping.getByRole("checkbox", { name: "HR" }).check();
    expect((await saved).status()).toBe(200);
    await expect(page.getByRole("status", { name: "Draft status" })).toHaveText("All changes saved");

    // Asked about the product, it is given only the HR Document; the Trace shows the price list
    // was left out by the Tags.
    await page.getByLabel("Question", { exact: true }).fill("What warranty does SKU-4471 have?");
    await page.getByRole("button", { name: "Send" }).click();
    const answer = page.getByRole("list", { name: "Playground messages" }).getByRole("listitem", { name: "HR helper" });
    await expect(answer).toContainText("Fake reply from anthropic:claude-haiku-4-5.", { timeout: 15_000 });
    await expect(answer.getByRole("list", { name: "Sources" }).getByRole("link")).toHaveText(["C1 leave-policy.md"]);
    await answer.getByRole("button", { name: "Trace" }).click();
    const trace = page.getByRole("dialog", { name: "Trace" });
    const chunks = trace.getByRole("table", { name: "Retrieved Chunks" });
    await expect(chunks.getByRole("row").filter({ hasText: "price-list.md" })).toContainText("Excluded: outside the Agent's Tags", {
      timeout: 15_000,
    });
    await expect(chunks.getByRole("row").filter({ hasText: "leave-policy.md" })).toContainText("Cited");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await trace.getByRole("button", { name: "Close" }).click();

    // Deleting HR warns that the HR helper uses it; once deleted, the Draft has no Tags.
    await page.goto(`/organisations/${organisationId}/projects/${projectId}`);
    const tags = page.getByRole("region", { name: "Tags" });
    await tags.getByRole("button", { name: "Delete HR" }).click();
    await expect(tags.getByRole("alert")).toHaveText(
      "1 Agent is limited to HR: HR helper. Deleting it takes it out of their Drafts; an Agent left with no Tags searches every Document.",
    );
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await tags.getByRole("button", { name: "Delete Tag" }).click();
    await expect(tags.getByTestId("tag-name")).toHaveText(["Sales"]);
    const draft = (await (await page.request.get(`${projectApi}/agents/${agentId}`)).json()) as {
      draft: { retrieval: { tag_ids: string[] } };
    };
    expect(draft.draft.retrieval.tag_ids).not.toContain(hr);
    expect(draft.draft.retrieval.tag_ids).toEqual([]);
  });
});
