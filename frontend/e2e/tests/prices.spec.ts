import type { Page } from "@playwright/test";

import { expect, test } from "../fixtures";

// The compose stack checks keys with the fake verifier; no real provider is called and no
// real key is used. Prices come from the repo's price table, loaded when the API migrates.
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-p7q2";

async function settingsTab(page: Page, tab: string) {
  await page.getByRole("navigation", { name: "Organisation settings" }).getByRole("link", { name: tab }).click();
}

test.describe("prices", () => {
  test("an Owner sees the platform price table and overrides a price for one credential", async ({ signedInPage: page, makeAxeBuilder }) => {
    await page.goto("/");
    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Organisation settings" }).click();
    await settingsTab(page, "Credentials");
    const add = page.getByRole("region", { name: "Add a credential" });
    await add.getByLabel("Provider").selectOption("Anthropic");
    await add.getByLabel("Name").fill("Negotiated Claude");
    await add.getByLabel("API key").fill(CHAT_KEY);
    await add.getByRole("button", { name: "Check and save" }).click();
    await expect(page.getByText("Negotiated Claude was checked and saved.")).toBeVisible();

    // The platform price table, as loaded from the repo on migrate.
    await settingsTab(page, "Models");
    const table = page.getByRole("table", { name: "Prices for Negotiated Claude" });
    const sonnet = table.getByRole("row", { name: /Claude Sonnet 4\.5/ });
    await expect(sonnet.getByRole("cell")).toHaveText(["$3.00", "$15.00", "$0.30", "Override"]);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // A negotiated input price; the other two keep the platform price.
    await page.getByRole("button", { name: "Override prices: Claude Sonnet 4.5" }).click();
    const form = page.getByRole("form", { name: "Override prices for Claude Sonnet 4.5" });
    await form.getByLabel("Input", { exact: true }).fill("2.25");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await form.getByRole("button", { name: "Save prices" }).click();
    await expect(page.getByRole("status")).toHaveText("Prices for Claude Sonnet 4.5 saved.");
    await expect(sonnet.getByRole("cell")).toHaveText(["$2.25Override (platform $3.00)", "$15.00", "$0.30", "Override"]);

    // The override survives a reload, and is audited.
    await page.reload();
    await expect(sonnet.getByRole("cell").first()).toHaveText("$2.25Override (platform $3.00)");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const id = me.organisations[0]?.id ?? "";
    const audit = (await (await page.request.get(`/api/organisations/${id}/audit-events?action=credential.price_overridden`)).json()) as {
      items: { after: Record<string, string | null> }[];
    };
    expect(audit.items.map((event) => event.after)).toEqual([{ model: "claude-sonnet-4-5", input: "2.25", output: null, cached_input: null }]);

    // Back to the platform prices.
    await page.getByRole("button", { name: "Override prices: Claude Sonnet 4.5" }).click();
    await page.getByRole("button", { name: "Use platform prices" }).click();
    await expect(page.getByRole("status")).toHaveText("Claude Sonnet 4.5 uses the platform prices again.");
    await expect(sonnet.getByRole("cell")).toHaveText(["$3.00", "$15.00", "$0.30", "Override"]);
  });
});
