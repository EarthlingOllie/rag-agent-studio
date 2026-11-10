import type { Page } from "@playwright/test";

import { expect, test } from "../fixtures";
import { newMember } from "../fixtures/auth";
import { openSection } from "../fixtures/navigation";

// The compose stack checks keys with the fake verifier: every key passes except those
// starting `fake-fail-<reason>`. No real provider is called and no real key is used.
const KEY = "sk-proj-e2e-test-only-not-a-real-key-k7q2";
const ROTATED = "sk-proj-e2e-test-only-rotated-key-r9z4";

async function openCredentials(page: Page) {
  await page.goto("/");
  await openSection(page, "Organisation sections", "Settings");
  await openSection(page, "Organisation settings", "Credentials");
  await expect(page.getByRole("heading", { name: "Provider Credentials" })).toBeVisible();
}

test.describe("provider credentials", () => {
  test("an Owner adds, re-checks, rotates and deletes a credential; a failed check says why; the key is never shown", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await openCredentials(page);
    await expect(page.getByText("No credentials yet.")).toBeVisible();
    const form = page.getByRole("region", { name: "Add a credential" });

    // A key the provider rejects is not saved, and the reason is shown.
    await form.getByLabel("Provider").selectOption("OpenAI");
    await form.getByLabel("Name").fill("Marketing OpenAI");
    await form.getByLabel("API key").fill("fake-fail-invalid_key-e2e-0000");
    await form.getByRole("button", { name: "Check and save" }).click();
    await expect(page.getByRole("alert")).toHaveText(
      "The check failed. The provider rejected this API key. Check it was copied in full.",
    );
    await expect(page.getByText("No credentials yet.")).toBeVisible();

    // A good key is checked, saved and shown only by its last four characters.
    await form.getByLabel("API key").fill(KEY);
    await form.getByRole("button", { name: "Check and save" }).click();
    await expect(page.getByText("Marketing OpenAI was checked and saved.")).toBeVisible();
    const table = page.getByRole("table", { name: "Provider Credentials" });
    const row = table.getByRole("row", { name: /Marketing OpenAI/ });
    await expect(row).toContainText("OpenAI");
    await expect(row).toContainText("Chat, Embeddings");
    await expect(row).toContainText("••••k7q2");
    await expect(row).toContainText("Working");
    await expect(page.locator("body")).not.toContainText(KEY.slice(0, -4));
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    await page.getByRole("button", { name: "Check now: Marketing OpenAI" }).click();
    await expect(page.getByText("Marketing OpenAI passed its check.")).toBeVisible();

    // Rotating keeps the credential and replaces the key.
    const before = await row.getByRole("cell").first().textContent();
    await page.getByRole("button", { name: "Rotate key: Marketing OpenAI" }).click();
    await page.getByLabel("New API key for Marketing OpenAI").fill(ROTATED);
    await page.getByRole("button", { name: "Check and rotate" }).click();
    await expect(page.getByText("The key of Marketing OpenAI was checked and replaced.")).toBeVisible();
    await expect(row).toContainText("••••r9z4");
    expect(await row.getByRole("cell").first().textContent()).toBe(before);

    // No API answer carries the key.
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const id = me.organisations[0]?.id ?? "";
    const listed = await (await page.request.get(`/api/organisations/${id}/credentials`)).text();
    const audit = await (await page.request.get(`/api/organisations/${id}/audit-events?size=100`)).text();
    for (const body of [listed, audit]) {
      expect(body).not.toContain(KEY.slice(0, -4));
      expect(body).not.toContain(ROTATED.slice(0, -4));
    }
    expect(audit).toContain("credential.created");
    expect(audit).toContain("credential.rotated");
    expect(audit).toContain("credential.check_failed");

    await page.getByRole("button", { name: "Delete: Marketing OpenAI" }).click();
    await page.getByRole("button", { name: "Yes, delete Marketing OpenAI" }).click();
    await expect(page.getByText("Marketing OpenAI was deleted.")).toBeVisible();
    await expect(page.getByText("No credentials yet.")).toBeVisible();
  });

  test("an Editor sees the Organisation's credentials but can't manage them", async ({ signedInPage: owner, browser }) => {
    await openCredentials(owner);
    const form = owner.getByRole("region", { name: "Add a credential" });
    await form.getByLabel("Provider").selectOption("Voyage AI");
    await form.getByLabel("Name").fill("Search embeddings");
    await form.getByLabel("API key").fill("pa-e2e-test-only-not-a-real-key-m3v8");
    await form.getByRole("button", { name: "Check and save" }).click();
    await expect(owner.getByText("Search embeddings was checked and saved.")).toBeVisible();

    // Invite an Editor with a copied link; they join in their own browser.
    const editor = newMember({ name: "Grace Editor" });
    await openSection(owner, "Organisation settings", "Members");
    await expect(owner.getByRole("table", { name: "Members" })).toBeVisible();
    await owner.getByRole("button", { name: "Invite someone" }).click();
    const invite = owner.getByRole("form", { name: "Invite someone" });
    await invite.getByLabel("Email", { exact: true }).fill(editor.email);
    await invite.getByLabel("Role").selectOption("Editor");
    await invite.getByLabel("Email the invite link").uncheck();
    await invite.getByRole("button", { name: "Invite" }).click();
    const link = new URL(await owner.getByLabel(`Invite link for ${editor.email}`).inputValue());
    const page = await (await browser.newContext()).newPage();
    await page.goto(link.pathname + link.search);
    await page.getByLabel("Your name").fill(editor.name);
    await page.getByLabel("Password").fill(editor.password);
    await page.getByRole("button", { name: "Create account and join" }).click();
    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();

    await openCredentials(page);
    const row = page.getByRole("table", { name: "Provider Credentials" }).getByRole("row", { name: /Search embeddings/ });
    await expect(row).toContainText("Embeddings, Reranking");
    await expect(row).toContainText("••••m3v8");
    await expect(page.getByText("Only Owners can add, check, rotate or delete credentials.")).toBeVisible();
    await expect(page.getByRole("region", { name: "Add a credential" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Delete: Search embeddings" })).toHaveCount(0);
  });
});
