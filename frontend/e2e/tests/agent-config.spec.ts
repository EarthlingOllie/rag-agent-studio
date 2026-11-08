import { fileURLToPath } from "node:url";

import type { Page } from "@playwright/test";

import { expect, test } from "../fixtures";

/** The seed staff handbook (synthetic content), uploaded as an Editor would. */
const HANDBOOK = fileURLToPath(new URL("../../../seed/documents/northwind-staff-handbook.md", import.meta.url));
// The compose stack checks keys with the fake verifier and answers with the fake gateway's
// chat model. No real provider is called and no real key is used.
const CLAUDE_KEY = "sk-ant-e2e-test-only-not-a-real-key-c4n8";
const OPENAI_KEY = "sk-proj-e2e-test-only-not-a-real-key-0000000000-r7t1";

/** Waits for the next Draft save and checks the API accepted it. */
async function nextSave(page: Page, status = 200) {
  const response = await page.waitForResponse((r) => new URL(r.url()).pathname.endsWith("/draft") && r.request().method() === "PUT");
  expect(response.status()).toBe(status);
}

test.describe("Full AgentConfig editor", () => {
  test("an Owner configures every group, the Draft autosaves and the Playground uses the Model override", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    test.setTimeout(120_000);
    // Two credentials and a Default Model, a Project and an Agent, set up through the API.
    await page.goto("/");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const organisationId = me.organisations[0]?.id ?? "";
    const organisation = `/api/organisations/${organisationId}`;
    const add = async (data: object) => {
      const response = await page.request.post(`${organisation}/credentials`, { data });
      expect(response.status()).toBe(201);
      return ((await response.json()) as { id: string }).id;
    };
    const claude = await add({ name: "Support Claude", provider: "anthropic", api_key: CLAUDE_KEY });
    const openAi = await add({ name: "Team OpenAI", provider: "openai", api_key: OPENAI_KEY });
    const chosen = await page.request.put(`${organisation}/default-model`, { data: { credential_id: claude, model: "claude-haiku-4-5" } });
    expect(chosen.status()).toBe(200);
    const project = await page.request.post(`${organisation}/projects`, { data: { name: "Northwind HR" } });
    const projectId = ((await project.json()) as { id: string }).id;
    const agent = await page.request.post(`${organisation}/projects/${projectId}/agents`, { data: { name: "HR helper" } });
    const agentId = ((await agent.json()) as { id: string }).id;
    // The Knowledge Base holds the seed handbook, so the Playground has Chunks to answer from.
    await page.goto(`/organisations/${organisationId}/projects/${projectId}`);
    await page.getByLabel("Choose files to upload").setInputFiles(HANDBOOK);
    const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /northwind-staff-handbook\.md/ });
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    await page.goto(`/organisations/${organisationId}/projects/${projectId}/agents/${agentId}`);

    const status = page.getByRole("status", { name: "Draft status" });
    await expect(status).toHaveText("All changes saved", { timeout: 15_000 });
    const behaviour = page.getByRole("group", { name: "Behaviour" });
    const model = behaviour.getByRole("group", { name: "Model override" });

    // Behaviour: the Model override and a temperature.
    await model.getByLabel("Credential").selectOption({ label: "Team OpenAI (OpenAI)" });
    let save = nextSave(page);
    await model.getByLabel("Model").selectOption({ label: "GPT-4.1 mini" });
    await save;
    save = nextSave(page);
    await behaviour.getByLabel("Temperature").fill("0.2");
    await save;

    // Experience and Guardrails.
    const experience = page.getByRole("group", { name: "Experience" });
    save = nextSave(page);
    await experience.getByLabel("Greeting").fill("Hi! Ask me about leave.");
    await save;
    save = nextSave(page);
    await page.getByRole("group", { name: "Guardrails" }).getByLabel("Input Guardrail mode").selectOption("warn");
    await save;
    await expect(status).toHaveText("All changes saved");

    // An out-of-range setting is refused, with the reason beside it.
    save = nextSave(page, 422);
    await behaviour.getByLabel("Temperature").fill("5");
    await save;
    await expect(status).toHaveText("Not saved: fix the settings marked below.");
    await expect(behaviour.getByLabel("Temperature")).toHaveAttribute("aria-invalid", "true");
    await expect(behaviour.getByText("Input should be less than or equal to 1")).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    save = nextSave(page);
    await behaviour.getByLabel("Temperature").fill("0.3");
    await save;
    await expect(status).toHaveText("All changes saved");

    // The Playground answers with the Model override, not the Default Model.
    await page.getByLabel("Question", { exact: true }).fill("How many days of annual leave do I get?");
    await page.getByRole("button", { name: "Send" }).click();
    const answer = page.getByRole("list", { name: "Playground messages" }).getByRole("listitem", { name: "HR helper" });
    await expect(answer).toContainText("Fake reply from openai:gpt-4.1-mini.", { timeout: 15_000 });

    // The OpenAI credential is a Credential reference now, so it can't be deleted.
    const deleted = await page.request.delete(`${organisation}/credentials/${openAi}`);
    expect(deleted.status()).toBe(409);
    expect(((await deleted.json()) as { references: unknown[] }).references).toEqual([
      { kind: "agent", id: agentId, name: "HR helper (model)" },
    ]);

    // A reload shows the saved Draft.
    await page.reload();
    await expect(page.getByRole("group", { name: "Behaviour" }).getByLabel("Temperature")).toHaveValue("0.3", { timeout: 15_000 });
    await expect(page.getByRole("group", { name: "Model override" }).getByLabel("Model")).toHaveValue("gpt-4.1-mini");
    await expect(page.getByRole("group", { name: "Experience" }).getByLabel("Greeting")).toHaveValue("Hi! Ask me about leave.");
    await expect(page.getByLabel("Input Guardrail mode")).toHaveValue("warn");
  });
});
