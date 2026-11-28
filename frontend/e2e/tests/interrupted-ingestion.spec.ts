import { expect, test } from "../fixtures";
import { openSection } from "../fixtures/navigation";

/**
 * Test-only: with CONVERTER_TEST_INTERRUPTS on (`make e2e` sets it), the stack's converter
 * interrupts a file whose first line starts with this at its first conversion, as a worker that
 * died there would (`INTERRUPT_MARKER` in backend/app/documents/converter.py). `make e2e` also
 * shortens the dead-after time to 20 s, and Beat runs the sweeper every minute.
 */
const INTERRUPT_MARKER = "%INTERRUPT-ONCE ";
const DEAD_AFTER_MS = 20_000;

test.describe("Interrupted ingestion", () => {
  test("an ingestion interrupted mid-way goes back to Queued and becomes Ready without anyone doing anything", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    // Dead after 20 s, then the next minutely sweep puts it back to Queued and sends it again.
    test.setTimeout(240_000);
    await page.goto("/");
    await openSection(page, "Organisation sections", "Projects");
    await page.getByRole("button", { name: "New Project" }).click();
    const form = page.getByRole("form", { name: "New Project" });
    await form.getByLabel("Name").fill("Interrupted ingestion");
    await form.getByRole("button", { name: "Create Project" }).click();
    await expect(page.getByText(/No Documents yet/)).toBeVisible();

    // Each run's file is new (the switch interrupts a given file once).
    const body = `${INTERRUPT_MARKER}${String(Date.now())}\n# Handbook\n\nEveryone gets 25 days of annual leave.\n`;
    // Every status the list's polling reads for the Document, in order.
    const seen: string[] = [];
    page.on("response", async (response) => {
      if (!/\/documents\/statuses/.test(response.url()) || !response.ok()) return;
      const statuses = (await response.json().catch(() => [])) as { status: string }[];
      for (const { status } of statuses) if (seen.at(-1) !== status) seen.push(status);
    });
    const uploaded = Date.now();
    await page.getByLabel("Upload", { exact: true }).setInputFiles({ name: "interrupted.md", mimeType: "text/markdown", buffer: Buffer.from(body) });

    // The worker dies during conversion: the Document stays Processing, with no error.
    const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /interrupted\.md/ });
    await expect(row.getByRole("cell", { name: "Processing" })).toBeVisible({ timeout: 60_000 });
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // Once it counts as dead, the sweeper puts it back to Queued and it is ingested again.
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 180_000 });
    expect(Date.now() - uploaded).toBeGreaterThan(DEAD_AFTER_MS);
    await expect(row).not.toContainText("Interrupted");
    const chunks = Number(await row.getByRole("cell").nth(5).textContent());
    expect(chunks).toBeGreaterThan(0);
    expect(seen).toContain("processing");
    expect(seen.at(-1)).toBe("ready");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });
});
