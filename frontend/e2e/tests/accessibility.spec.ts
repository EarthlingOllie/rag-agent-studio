import { fileURLToPath } from "node:url";

import { expect, test } from "../fixtures";
import { APPEARANCES, pagePath, SIGNED_IN_PAGES } from "../fixtures/pages";

/** The seed staff handbook (synthetic content), uploaded as an Editor would. */
const HANDBOOK = fileURLToPath(new URL("../../../seed/documents/northwind-staff-handbook.md", import.meta.url));
// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-a11y";

test.describe("Accessibility", () => {
  test("every signed-in page has no WCAG 2.2 AA violations, in the light and the dark Appearance", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    // Ingestion, then 23 pages scanned twice.
    test.setTimeout(300_000);
    await page.goto("/");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const organisationId = me.organisations[0]?.id ?? "";
    const organisation = `/api/organisations/${organisationId}`;
    const credential = await page.request.post(`${organisation}/credentials`, {
      data: { name: "Support Claude", provider: "anthropic", api_key: CHAT_KEY },
    });
    expect(credential.status()).toBe(201);
    const { id: credentialId } = (await credential.json()) as { id: string };
    expect(
      (await page.request.put(`${organisation}/default-model`, { data: { credential_id: credentialId, model: "claude-haiku-4-5" } })).status(),
    ).toBe(200);

    // A Project with a Document, an Agent with a Live Version, and a Playground Conversation, so
    // every page has something to show.
    const project = await page.request.post(`${organisation}/projects`, { data: { name: "Northwind HR" } });
    const { id: projectId } = (await project.json()) as { id: string };
    const agent = await page.request.post(`${organisation}/projects/${projectId}/agents`, { data: { name: "HR helper" } });
    const { id: agentId } = (await agent.json()) as { id: string };
    const agentApi = `${organisation}/projects/${projectId}/agents/${agentId}`;
    expect((await page.request.post(`${agentApi}/versions`, { data: { note: "First release" } })).status()).toBe(201);
    const playground = await page.request.post(`${agentApi}/playground/conversations`);
    const { id: conversationId } = (await playground.json()) as { id: string };
    expect(
      (await page.request.post(`${agentApi}/playground/conversations/${conversationId}/messages`, { data: { content: "Testing leave" } })).status(),
    ).toBe(200);

    await page.goto(`/organisations/${organisationId}/projects/${projectId}`);
    await page.getByLabel("Upload", { exact: true }).setInputFiles(HANDBOOK);
    const document = page.getByRole("table", { name: "Documents" }).getByRole("link", { name: "northwind-staff-handbook.md" });
    await expect(document).toBeVisible({ timeout: 15_000 });
    const documentId = /\/documents\/([0-9a-f-]+)/.exec((await document.getAttribute("href")) ?? "")?.[1] ?? "";
    const ids = { organisationId, projectId, documentId, agentId, conversationId };

    // Each page's violations, by Appearance and page; the expectation shows them all at once.
    const violations: Record<string, string[]> = {};
    for (const appearance of APPEARANCES) {
      await page.emulateMedia({ colorScheme: appearance });
      for (const target of SIGNED_IN_PAGES) {
        await page.goto(pagePath(target, ids));
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 15_000 });
        await page.waitForLoadState("networkidle");
        const found = (await makeAxeBuilder().analyze()).violations.map((violation) => violation.id);
        if (found.length > 0) violations[`${appearance} ${target.name}`] = found;
      }
    }
    expect(violations).toEqual({});
  });
});
