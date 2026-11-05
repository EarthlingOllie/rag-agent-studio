import type { Page } from "@playwright/test";

import { expect, test } from "../fixtures";

// The compose stack checks keys with the fake verifier and builds models with the fake
// gateway adapters. No real provider is called and no real key is used.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-h4n1";
const EMBEDDINGS_KEY = "pa-e2e-test-only-not-a-real-key-v8c3";

async function settingsTab(page: Page, tab: string) {
  await page.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: tab }).click();
}

async function addCredential(page: Page, provider: string, name: string, apiKey: string) {
  const form = page.getByRole("region", { name: "Add a credential" });
  await form.getByLabel("Provider").selectOption(provider);
  await form.getByLabel("Name").fill(name);
  await form.getByLabel("API key").fill(apiKey);
  await form.getByRole("button", { name: "Check and save" }).click();
  await expect(page.getByText(`${name} was checked and saved.`)).toBeVisible();
}

test.describe("models", () => {
  test("an Owner sets the Default Model from a chat-capable credential, and that credential can't then be deleted", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await page.goto("/");
    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Organisation settings" }).click();
    await settingsTab(page, "Models");
    await expect(page.getByRole("heading", { name: "Default Model" })).toBeVisible();
    await expect(page.getByText("No Default Model yet. New Agents need one to answer.")).toBeVisible();
    await expect(page.getByText(/No credential can be used for chat yet/)).toBeVisible();

    await page.getByRole("link", { name: "Add one on the Credentials tab" }).click();
    await addCredential(page, "Voyage AI", "Search embeddings", EMBEDDINGS_KEY);
    await addCredential(page, "Anthropic", "Support Claude", CHAT_KEY);

    // Only the chat-capable credential is offered, with its chat models.
    await settingsTab(page, "Models");
    const form = page.getByRole("form", { name: "Choose the Default Model" });
    const credential = form.getByLabel("Credential");
    await expect(credential.getByRole("option")).toHaveText(["Support Claude (Anthropic)"]);
    await expect(form.getByLabel("Model").getByRole("option")).toHaveText(["Claude Opus 4.1", "Claude Sonnet 4.5", "Claude Haiku 4.5"]);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    await form.getByLabel("Model").selectOption("Claude Haiku 4.5");
    await form.getByRole("button", { name: "Save Default Model" }).click();
    await expect(page.getByRole("status")).toHaveText("The Default Model is now Claude Haiku 4.5.");
    await expect(page.getByText("Claude Haiku 4.5, using Support Claude (Anthropic)")).toBeVisible();

    // The choice survives a reload, and is audited.
    await page.reload();
    await expect(page.getByText("Claude Haiku 4.5, using Support Claude (Anthropic)")).toBeVisible();
    await expect(page.getByRole("form", { name: "Choose the Default Model" }).getByLabel("Model")).toHaveValue("claude-haiku-4-5");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const id = me.organisations[0]?.id ?? "";
    const audit = await (await page.request.get(`/api/organisations/${id}/audit-events?action=default_model.changed`)).text();
    expect(audit).toContain("claude-haiku-4-5");

    // The Default Model's credential is a reference: deleting it is refused and says why.
    await settingsTab(page, "Credentials");
    await page.getByRole("button", { name: "Delete: Support Claude" }).click();
    await page.getByRole("button", { name: "Yes, delete Support Claude" }).click();
    await expect(page.getByText("Default Model (Claude Haiku 4.5)")).toBeVisible();
    await expect(page.getByRole("table", { name: "Provider Credentials" }).getByRole("row", { name: /Support Claude/ })).toBeVisible();
  });
});
