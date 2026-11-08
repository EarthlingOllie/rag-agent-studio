import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { expect, test } from "../fixtures";

/** The seed staff handbook (synthetic content), uploaded as an Editor would. */
const HANDBOOK = fileURLToPath(new URL("../../../seed/documents/northwind-staff-handbook.md", import.meta.url));

test.describe("Documents", () => {
  test("an Owner uploads the seed handbook and it goes from Queued to Ready", async ({ signedInPage: page, makeAxeBuilder }) => {
    await page.goto("/");
    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Projects" }).click();
    const form = page.getByRole("form", { name: "New Project" });
    await form.getByLabel("Name").fill("Northwind handbook");
    await form.getByRole("button", { name: "Create Project" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "Documents" })).toBeVisible();
    await expect(page.getByText(/No Documents yet/)).toBeVisible();

    // Presign, PUT straight to the object store (RustFS through the Studio's proxy), confirm.
    await page.getByLabel("Choose files to upload").setInputFiles(HANDBOOK);
    await expect(page.getByRole("list", { name: "Uploads" }).getByText("Uploaded")).toBeVisible();

    // The list polls the status endpoint until the Document is Ready, without a reload.
    const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /northwind-staff-handbook\.md/ });
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    // Columns: select, Name, Status, Tags, Chunks, Size.
    const chunks = Number(await row.getByRole("cell").nth(4).textContent());
    expect(chunks).toBeGreaterThan(0);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The Project's Document count, and its Chunks through the API.
    await page.getByRole("link", { name: "All Projects" }).click();
    const projectRow = page.getByRole("row", { name: /Northwind handbook/ });
    await expect(projectRow.getByRole("cell", { name: "1", exact: true }).first()).toBeVisible();
  });

  test("an Owner opens the handbook in the Document viewer and downloads the original", async ({ signedInPage: page, makeAxeBuilder }) => {
    await page.goto("/");
    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Projects" }).click();
    const form = page.getByRole("form", { name: "New Project" });
    await form.getByLabel("Name").fill("Handbook viewer");
    await form.getByRole("button", { name: "Create Project" }).click();
    await page.getByLabel("Choose files to upload").setInputFiles(HANDBOOK);
    const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /northwind-staff-handbook\.md/ });
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });

    await row.getByRole("link", { name: "northwind-staff-handbook.md" }).click();

    // Docling's markdown, rendered, beside the Chunks with their heading paths.
    await expect(page.getByRole("heading", { level: 2, name: "northwind-staff-handbook.md" })).toBeVisible();
    const markdown = page.getByRole("region", { name: "Converted markdown" });
    await expect(markdown.getByRole("heading", { name: "Annual leave" })).toBeVisible();
    const chunks = page.getByRole("region", { name: "Chunks" });
    await expect(chunks.getByText(/^Chunks 1–\d+ of \d+$/)).toBeVisible();
    const leave = chunks.getByRole("listitem").filter({ hasText: "25 days of annual leave" });
    await expect(leave.getByText("Northwind Traders staff handbook › Annual leave")).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The original downloads through the API's redirect to a presigned GET on RustFS.
    const downloading = page.waitForEvent("download");
    await page.getByRole("link", { name: "Download original" }).click();
    const download = await downloading;
    expect(download.suggestedFilename()).toBe("northwind-staff-handbook.md");
    expect(readFileSync(await download.path(), "utf8")).toBe(readFileSync(HANDBOOK, "utf8"));
  });

  test("the ingestion scan flags the injection planted in the seed handbook, and an Editor can exclude or clear it", async ({ signedInPage: page, makeAxeBuilder }) => {
    await page.goto("/");
    await page.getByRole("navigation", { name: "Organisation" }).getByRole("link", { name: "Projects" }).click();
    const form = page.getByRole("form", { name: "New Project" });
    await form.getByLabel("Name").fill("Handbook scan");
    await form.getByRole("button", { name: "Create Project" }).click();
    // The Project quarantines flagged Chunks.
    await page.getByRole("navigation", { name: "Project" }).getByRole("link", { name: "Settings" }).click();
    const flaggedSetting = page.getByRole("radiogroup", { name: "Flagged Chunks" });
    await expect(flaggedSetting.getByRole("radio", { name: "Mark them, and keep retrieving them" })).toBeChecked();
    await flaggedSetting.getByRole("radio", { name: "Exclude them from retrieval" }).check();
    await expect(flaggedSetting.getByText(/Flagged Chunks are never given to an Agent/)).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
    await page.getByRole("navigation", { name: "Project" }).getByRole("link", { name: "Documents" }).click();
    await page.getByLabel("Choose files to upload").setInputFiles(HANDBOOK);
    const row = page.getByRole("table", { name: "Documents" }).getByRole("row", { name: /northwind-staff-handbook\.md/ });
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });

    // Columns: select, Name, Status, Tags, Chunks, Flagged, Size. One Chunk is flagged, by the local ONNX classifier.
    await expect(row.getByRole("cell").nth(5)).toHaveText("1");
    await row.getByRole("link", { name: "northwind-staff-handbook.md" }).click();

    await expect(page.getByText("1 Chunk flagged as possible instructions to an AI.")).toBeVisible();
    const chunks = page.getByRole("region", { name: "Chunks" });
    const planted = chunks.getByRole("listitem").filter({ has: page.getByRole("note", { name: "Guardrail flag" }) });
    await expect(planted).toHaveCount(1);
    await expect(planted.getByText("Northwind Traders staff handbook › A note for AI assistants")).toBeVisible();
    await expect(planted.getByRole("note", { name: "Guardrail flag" })).toContainText(
      /^Flagged: Prompt injection, score \d\.\d\d\. The local classifier scored the Chunk \d\.\d\d as a prompt injection\.$/,
    );
    // The handbook's ordinary policy text isn't flagged.
    const leave = chunks.getByRole("listitem").filter({ hasText: "25 days of annual leave" });
    await expect(leave.getByRole("note")).toHaveCount(0);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // An Editor judges it a false positive and clears the flag.
    const note = chunks.getByRole("listitem").filter({ hasText: "A note for AI assistants" });
    await note.getByRole("button", { name: /^Clear flag on Chunk \d+$/ }).click();
    await expect(note.getByRole("note", { name: "Guardrail flag" })).toHaveCount(0);
    await expect(page.getByText(/flagged as possible instructions to an AI/)).toHaveCount(0);
  });
});
