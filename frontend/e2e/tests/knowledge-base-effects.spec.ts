import { fileURLToPath } from "node:url";

import type { Page, Request, Route } from "@playwright/test";

import { expect, test } from "../fixtures";
import { openSettings } from "../fixtures/agent";
import { rowAction } from "../fixtures/documents";
import { scannedPdf, slideDeck } from "../fixtures/knowledge-base-effects";
import { openSection } from "../fixtures/navigation";

/**
 * What the Knowledge Base's settings and actions do to what Agents retrieve: uploads (drop zone,
 * progress, size limit, quota), editions, deletes, page numbers, OCR, re-embedding, flagged Chunks
 * and the Project Settings page. Retrieval is checked through the API's retrieval probe (the
 * Chunks nearest a query, by vector, of each Document's current edition and the Project's current
 * Embedding Model) and, for flagged Chunks, through the Playground's Trace.
 */

/** The seed staff handbook (synthetic content), with an injection planted for the ingestion scan. */
const HANDBOOK = fileURLToPath(new URL("../../../seed/documents/northwind-staff-handbook.md", import.meta.url));
// The compose stack checks keys with the fake verifier and calls provider models through the
// gateway's offline fakes. No real provider is called and no real key is used.
const EMBEDDINGS_KEY = "pa-e2e-test-only-not-a-real-key-p2kb";
const CHAT_KEY = "sk-ant-e2e-test-only-not-a-real-key-p2kb";
/** What a Document says when the worker can't convert it at all, as every PDF on a stack built without PDF support. */
const NO_PDF_PARSER = "This file couldn't be converted. Retry it, or upload a fixed copy.";

interface Probe {
  embedding_model_id: string;
  dimension: number;
  chunks: { document_name: string; text: string; score: number }[];
}

interface ProjectDocument {
  id: string;
  name: string;
  status: string;
  edition: number;
  chunk_count: number;
  error_message: string | null;
  replacement: { edition: number; status: string } | null;
}

function markdown(name: string, text: string) {
  return { name, mimeType: "text/markdown", buffer: Buffer.from(text) };
}

/** A Markdown Document with one short section per heading: `sections` Chunks, quick to scan. */
function manySections(name: string, sections: number, line: (index: number) => string) {
  const body = Array.from({ length: sections }, (_, index) => `## Section ${String(index + 1)}\n\n${line(index + 1)}\n`).join("\n");
  return markdown(name, `# ${name}\n\n${body}`);
}

/** Creates a Project from the Projects page, as a Member does; it opens on its Documents. */
async function createProject(page: Page, name: string) {
  await page.goto("/");
  await openSection(page, "Organisation sections", "Projects");
  await page.getByRole("button", { name: "New Project" }).click();
  const form = page.getByRole("form", { name: "New Project" });
  await form.getByLabel("Name").fill(name);
  await form.getByRole("button", { name: "Create Project" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Documents", exact: true })).toBeVisible();
}

/** The API paths of the Organisation and the Project the page shows. */
function apiPaths(page: Page) {
  const [, organisationId, projectId] = /organisations\/([^/]+)\/projects\/([^/]+)/.exec(page.url()) ?? [];
  const organisation = `/api/organisations/${organisationId ?? ""}`;
  return { organisation, project: `${organisation}/projects/${projectId ?? ""}` };
}

async function probe(page: Page, project: string, query: string, topK = 5): Promise<Probe> {
  const response = await page.request.post(`${project}/retrieval-probe`, { data: { query, top_k: topK } });
  expect(response.status()).toBe(200);
  return (await response.json()) as Probe;
}

async function documentsOf(page: Page, project: string): Promise<ProjectDocument[]> {
  const response = await page.request.get(`${project}/documents`);
  expect(response.status()).toBe(200);
  return (await response.json()) as ProjectDocument[];
}

async function auditCount(page: Page, organisation: string, action: string): Promise<number> {
  const response = await page.request.get(`${organisation}/audit-events`, { params: { action } });
  expect(response.status()).toBe(200);
  return ((await response.json()) as { total: number }).total;
}

/** Saves a Voyage AI credential through the API and returns its ID. */
async function voyageCredential(page: Page, organisation: string, name: string): Promise<string> {
  const response = await page.request.post(`${organisation}/credentials`, { data: { name, provider: "voyage", api_key: EMBEDDINGS_KEY } });
  expect(response.status()).toBe(201);
  return ((await response.json()) as { id: string }).id;
}

function documentRow(page: Page, name: string) {
  return page.getByRole("table", { name: "Documents" }).getByRole("row", { name: new RegExp(name.replace(/\./g, "\\.")) });
}

/** A Knowledge Base stat card's figure ("1 / 500", "multilingual-e5-small"). */
function stat(page: Page, label: "Documents" | "Chunks" | "Flagged chunks" | "Embedding Model") {
  return page.getByRole("region", { name: "Knowledge Base" }).getByText(label, { exact: true }).locator("xpath=following-sibling::span[1]");
}

/**
 * Holds the requests `matches` picks until `release` is called, then lets them through to the
 * real stack unchanged: a slow network, so a Member's view of work in flight can be checked.
 */
async function holdRequests(page: Page, matches: (request: Request) => boolean) {
  let release!: () => void;
  const released = new Promise<void>((resolve) => {
    release = resolve;
  });
  const held: Request[] = [];
  await page.route("**/*", async (route: Route) => {
    if (!matches(route.request())) {
      await route.fallback();
      return;
    }
    held.push(route.request());
    await released;
    await route.continue();
  });
  return { held, release };
}

test.describe("Knowledge Base effects", () => {
  test("an Editor drops several files on the drop zone, and each shows its own progress bar until it is uploaded", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    test.slow();
    await createProject(page, "P2 dropped files");
    // The files' PUTs to the object store are held, as on a slow connection.
    const storage = await holdRequests(page, (request) => request.method() === "PUT" && !new URL(request.url()).pathname.startsWith("/api/"));

    const files = [
      { name: "p2-leave.md", text: "# Leave\n\nEveryone gets 25 days of annual leave." },
      { name: "p2-expenses.md", text: "# Expenses\n\nClaim expenses within 30 days." },
    ];
    const dropped = await page.evaluateHandle((list) => {
      const transfer = new DataTransfer();
      for (const { name, text } of list) transfer.items.add(new File([text], name, { type: "text/markdown" }));
      return transfer;
    }, files);
    const dropzone = page.getByText(/^Drop files here to upload\./);
    await dropzone.dispatchEvent("dragover", { dataTransfer: dropped });
    await dropzone.dispatchEvent("drop", { dataTransfer: dropped });

    // One progress bar a file, named after it, while its upload is in flight.
    const uploads = page.getByRole("list", { name: "Uploads" });
    for (const { name } of files) {
      await expect(uploads.getByRole("progressbar", { name: `Uploading ${name}` })).toBeVisible();
    }
    await expect.poll(() => storage.held.length).toBe(2);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    storage.release();
    await expect(uploads.getByRole("progressbar")).toHaveCount(0);
    await expect(uploads.getByRole("listitem").filter({ hasText: "Uploaded" })).toHaveCount(2);
    for (const { name } of files) {
      await expect(documentRow(page, name).getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    }
  });

  test("a file over the upload limit is refused in the browser before anything is uploaded", async ({ signedInPage: page }) => {
    await createProject(page, "P2 size limit");
    const { project } = apiPaths(page);
    const limits = (await (await page.request.get(`${project}/uploads/limits`)).json()) as { max_upload_bytes: number };
    expect(limits.max_upload_bytes).toBe(50 * 1024 * 1024);
    const uploadRequests: string[] = [];
    page.on("request", (request) => {
      if (request.method() !== "GET") uploadRequests.push(`${request.method()} ${new URL(request.url()).pathname}`);
    });

    // One byte over the limit, dropped on the drop zone.
    const dropped = await page.evaluateHandle((size) => {
      const transfer = new DataTransfer();
      transfer.items.add(new File([new Uint8Array(size)], "p2-huge-manual.md", { type: "text/markdown" }));
      return transfer;
    }, limits.max_upload_bytes + 1);
    const dropzone = page.getByText(/^Drop files here to upload\. PDF, DOCX, PPTX, HTML, Markdown and TXT, up to 50\.0 MB each\.$/);
    await dropzone.dispatchEvent("drop", { dataTransfer: dropped });

    const uploads = page.getByRole("list", { name: "Uploads" });
    await expect(uploads.getByRole("listitem").filter({ hasText: "p2-huge-manual.md" }).getByRole("alert")).toHaveText(
      "This file is larger than the 50 MB upload limit.",
    );
    await expect(uploads.getByRole("progressbar")).toHaveCount(0);
    await expect(page.getByText(/No Documents yet/)).toBeVisible();
    // Nothing was asked of the API or sent to storage.
    expect(uploadRequests).toEqual([]);
  });

  test("an Owner's Document quota refuses the next upload with a clear message", async ({ signedInPage: page }) => {
    await createProject(page, "P2 quota");
    const { project } = apiPaths(page);
    const quota = await page.request.put(`${project}/document-quota`, { data: { document_quota: 1 } });
    expect(quota.status()).toBe(200);
    await page.reload();
    await expect(stat(page, "Documents")).toHaveText("0 / 1");

    await page.getByLabel("Upload", { exact: true }).setInputFiles(markdown("p2-first.md", "# First\n\nThe only Document there is room for."));
    await expect(documentRow(page, "p2-first.md").getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    await expect(stat(page, "Documents")).toHaveText("1 / 1");
    const message = "This Project has reached its quota of 1 Document. Delete a Document, or ask an Owner to raise the quota.";
    await expect(page.getByText(message, { exact: true })).toBeVisible();

    // The next one is refused before upload, with the same message.
    await page.getByLabel("Upload", { exact: true }).setInputFiles(markdown("p2-second.md", "# Second\n\nOne too many."));
    await expect(page.getByRole("list", { name: "Uploads" }).getByRole("alert")).toHaveText(message);
    await expect(page.getByRole("table", { name: "Documents" }).getByRole("row")).toHaveCount(2);

    // The API refuses it too.
    const refused = await page.request.post(`${project}/uploads`, { data: { filename: "p2-second.md", size_bytes: 20 } });
    expect(refused.status()).toBe(409);
    expect(((await refused.json()) as { detail: string }).detail).toBe(message);
  });

  test("while a new edition is processed the old one keeps being retrieved, then the new one replaces it", async ({ signedInPage: page }) => {
    test.slow();
    await createProject(page, "P2 editions");
    const { project } = apiPaths(page);
    await page.getByLabel("Upload", { exact: true }).setInputFiles(markdown("p2-leave.md", "# Leave policy\n\nEveryone gets 25 days of annual leave a year."));
    await expect(documentRow(page, "p2-leave.md").getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    const texts = async () => (await probe(page, project, "How many days of annual leave a year?", 3)).chunks.map((chunk) => chunk.text).join("\n");
    expect(await texts()).toContain("25 days of annual leave");

    // Edition 2 has many sections, so processing it takes a while.
    const chooser = page.waitForEvent("filechooser");
    await rowAction(page, "p2-leave.md", "New edition");
    await (await chooser).setFiles(
      manySections("p2-leave-2027.md", 150, (index) =>
        index === 1 ? "Everyone gets 28 days of annual leave a year." : `Rota note ${String(index)}: cover is arranged with the team lead.`,
      ),
    );
    await expect(page.getByText(/New edition 2 \(p2-leave-2027\.md\): (Queued|Processing)/)).toBeVisible();

    // Until edition 2 is Ready, every probe still finds edition 1.
    let duringProcessing = 0;
    for (;;) {
      const found = await texts();
      const [document] = await documentsOf(page, project);
      if (document?.replacement === null || document?.replacement === undefined) break;
      expect(document.replacement.status).not.toBe("failed");
      expect(found).toContain("25 days of annual leave");
      expect(found).not.toContain("28 days of annual leave");
      duringProcessing += 1;
    }
    expect(duringProcessing).toBeGreaterThan(0);

    const [replaced] = await documentsOf(page, project);
    expect([replaced?.name, replaced?.edition, replaced?.status]).toEqual(["p2-leave-2027.md", 2, "ready"]);
    const after = await texts();
    expect(after).toContain("28 days of annual leave");
    expect(after).not.toContain("25 days of annual leave");
  });

  test("a deleted Document stops being retrieved at once, and the delete is in the Audit log", async ({ signedInPage: page }) => {
    await createProject(page, "P2 deletes");
    const { organisation, project } = apiPaths(page);
    await page
      .getByLabel("Upload", { exact: true })
      .setInputFiles([
        markdown("p2-parking.md", "# Parking\n\nStaff parking permits come from reception in the north lobby."),
        markdown("p2-leave.md", "# Leave\n\nEveryone gets 25 days of annual leave."),
      ]);
    for (const name of ["p2-parking.md", "p2-leave.md"]) {
      await expect(documentRow(page, name).getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    }
    const names = async () => (await probe(page, project, "Where do I get a parking permit?", 5)).chunks.map((chunk) => chunk.document_name);
    expect(await names()).toContain("p2-parking.md");

    await rowAction(page, "p2-parking.md", "Delete");
    const confirm = page.getByRole("alertdialog", { name: "Delete p2-parking.md?" });
    await expect(confirm).toContainText("Its 1 chunk stops being retrieved at once.");
    await confirm.getByRole("button", { name: "Delete p2-parking.md" }).click();
    await expect(page.getByText("Deleted p2-parking.md.")).toBeVisible();

    // The very next retrieval no longer finds it; the other Document still is.
    const remaining = await names();
    expect(remaining).not.toContain("p2-parking.md");
    expect(remaining).toContain("p2-leave.md");

    expect(await auditCount(page, organisation, "document.deleted")).toBe(1);
    await openSection(page, "Organisation sections", "Settings");
    await openSection(page, "Organisation settings", "Audit");
    await expect(page.getByRole("table", { name: "Audit Events" }).getByRole("cell", { name: "document.deleted" })).toHaveCount(1);
  });

  test("an Editor sees a slide deck's Chunks with their heading and page number", async ({ signedInPage: page, makeAxeBuilder }) => {
    await createProject(page, "P2 slides");
    const deck = slideDeck("p2-onboarding.pptx", [
      { title: "Welcome", body: "New starters meet their buddy on their first morning." },
      { title: "Parking", body: "Staff parking permits come from reception in the north lobby." },
    ]);
    await page.getByLabel("Upload", { exact: true }).setInputFiles(deck);
    const row = documentRow(page, "p2-onboarding.pptx");
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });
    await row.getByRole("link", { name: "p2-onboarding.pptx" }).click();

    const chunks = page.getByRole("region", { name: "Chunks" });
    const welcome = chunks.getByRole("listitem").filter({ hasText: "meet their buddy" });
    const parking = chunks.getByRole("listitem").filter({ hasText: "parking permits" });
    await expect(welcome.getByText("Welcome", { exact: true })).toBeVisible();
    await expect(welcome.getByText("Page 1", { exact: true })).toBeVisible();
    await expect(parking.getByText("Parking", { exact: true })).toBeVisible();
    await expect(parking.getByText("Page 2", { exact: true })).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);
  });

  test("with OCR on, a scanned PDF's text is read and retrieved; with it off, it isn't", async ({ signedInPage: page }) => {
    test.slow();
    await createProject(page, "P2 scanned");
    const { project } = apiPaths(page);
    // A page of text drawn as an image, as a scanner makes it: there is no text layer. It is body
    // text, not headline-sized capitals: Docling's layout model reads large bold lines as section
    // headers, and a page of headers alone gives no Chunks, so it would fail with "No readable
    // text" even with OCR on.
    const [width, height] = [1240, 360];
    const pixels = await page.evaluate(
      ({ w, h }) => {
        const canvas = new OffscreenCanvas(w, h);
        const context = canvas.getContext("2d") as OffscreenCanvasRenderingContext2D;
        context.fillStyle = "#fff";
        context.fillRect(0, 0, w, h);
        context.fillStyle = "#000";
        context.font = "40px sans-serif";
        context.fillText("Staff parking permits come from reception", 60, 110);
        context.fillText("in the north lobby, on any weekday morning.", 60, 170);
        const { data } = context.getImageData(0, 0, w, h);
        let binary = "";
        for (let index = 0; index < data.length; index += 4) binary += String.fromCharCode(data[index] as number);
        return btoa(binary);
      },
      { w: width, h: height },
    );
    await page.getByLabel("Upload", { exact: true }).setInputFiles(scannedPdf("p2-scan.pdf", Buffer.from(pixels, "base64"), width, height));
    const row = documentRow(page, "p2-scan.pdf");
    await expect(row.getByRole("cell", { name: /^(Ready|Failed)/ })).toBeVisible({ timeout: 90_000 });
    const [scanned] = await documentsOf(page, project);
    const noText = /No readable text was found in this file\..*turn on OCR for this Project, then retry it\./;
    // A stack built with WITH_PDF=false has no PDF parser (docling-parse), so every PDF fails with
    // the generic conversion error. Only that exact error on a stack not declared PDF-capable is
    // skipped; with E2E_WITH_PDF=true (a stack built with WITH_PDF=true and BUNDLE_OCR_MODELS=true)
    // nothing is skipped, and any other error fails the test below.
    test.skip(
      process.env.E2E_WITH_PDF !== "true" && scanned?.error_message === NO_PDF_PARSER,
      "This stack can't convert PDFs (built with WITH_PDF=false); set E2E_WITH_PDF=true on a stack built with PDF and OCR support",
    );

    // OCR is off: the page's text isn't read, so the Document fails and says to turn OCR on.
    expect(scanned?.status).toBe("failed");
    await expect(row.getByRole("cell", { name: /^Failed/ })).toContainText(noText);
    const permits = async () => (await probe(page, project, "parking permits reception", 3)).chunks.map((chunk) => chunk.text).join("\n");

    await openSection(page, "Project sections", "Settings");
    await page.getByRole("checkbox", { name: "Read scanned PDFs with OCR" }).check();
    await expect(page.getByText(/OCR is on\./)).toBeVisible();
    await openSection(page, "Project sections", "Documents");
    await rowAction(page, "p2-scan.pdf", "Retry");
    // Waits on the Document's own status, so a run that fails again says why instead of timing out.
    const settled = async () => {
      const [document] = await documentsOf(page, project);
      return document?.status === "queued" || document?.status === "processing" ? "pending" : [document?.status, document?.error_message];
    };
    await expect.poll(settled, { timeout: 60_000 }).toEqual(["ready", null]);
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible();
    await expect.poll(async () => (await documentsOf(page, project))[0]?.chunk_count).toBeGreaterThan(0);
    expect(await permits()).toMatch(/PARKING\s+PERMITS/i);
  });

  test("changing the Embedding Model shows the re-embed's progress in Chunks while the old vectors keep serving, then switches in one step", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    // About 300 Chunks through the ingestion scan, then through the built-in model again.
    test.setTimeout(240_000);
    await createProject(page, "P2 re-embed progress");
    const { organisation, project } = apiPaths(page);
    const credential = await voyageCredential(page, organisation, "P2 progress embeddings");
    // Embedded first with Voyage (the gateway's fast fake), so moving to the built-in model takes a while.
    const chosen = await page.request.put(`${project}/embedding-model`, { data: { model_id: "voyage-3.5", credential_id: credential } });
    expect(chosen.status()).toBe(200);
    await page.reload();
    await page
      .getByLabel("Upload", { exact: true })
      .setInputFiles(manySections("p2-rota.md", 300, (index) => `Rota line ${String(index)}: team ${String(index)} reports to desk ${String(index * 7)}.`));
    await expect(documentRow(page, "p2-rota.md").getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 180_000 });
    const [rota] = await documentsOf(page, project);
    const total = rota?.chunk_count ?? 0;
    expect(total).toBeGreaterThanOrEqual(299);
    expect((await probe(page, project, "Who does team 12 report to?")).embedding_model_id).toBe("voyage-3.5");

    await openSection(page, "Project sections", "Settings");
    const setting = page.getByRole("region", { name: "Embedding Model" });
    await setting.getByRole("button", { name: "Change Embedding Model" }).click();
    const choose = page.getByRole("dialog", { name: "Change the Embedding Model" }).getByRole("form", { name: "Choose the Embedding Model" });
    await choose.getByLabel("Embedding Model").selectOption("multilingual-e5-small (built in)");
    await choose.getByRole("button", { name: "Use this model" }).click();

    // While it runs: a meter of Chunks embedded so far, and the model still serving.
    const progress = setting.getByRole("status");
    await expect(progress).toContainText(
      new RegExp(`^Re-embedding with multilingual-e5-small: \\d+ of ${String(total)} Chunks\\. Retrieval uses voyage-3\\.5 until it finishes\\.`),
    );
    const meter = progress.getByRole("meter", { name: "Re-embedding progress" });
    await expect(meter).toHaveAttribute("aria-valuemax", String(total));
    await expect(meter).toHaveAttribute("aria-valuetext", new RegExp(`^\\d+ of ${String(total)} Chunks$`));
    await expect(setting).toContainText("Documents are embedded with voyage-3.5.");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // Retrieval answers from one model's vectors at a time: Voyage's while the job runs. Only a
    // probe made wholly while the job runs (it is running before and after) is checked here; a
    // probe that straddles the switch is the defect the fixme'd test below covers.
    const reEmbedStatus = async () =>
      ((await (await page.request.get(`${project}/embedding-model`)).json()) as { re_embed: { status: string } }).re_embed.status;
    let whileRunning = 0;
    for (;;) {
      const before = await reEmbedStatus();
      if (before !== "running") break;
      const answer = await probe(page, project, "Who does team 12 report to?", 3);
      if ((await reEmbedStatus()) !== "running") break;
      expect([answer.embedding_model_id, answer.dimension]).toEqual(["voyage-3.5", 1024]);
      expect(answer.chunks).toHaveLength(3);
      whileRunning += 1;
    }
    expect(whileRunning).toBeGreaterThan(0);

    // Then it switches over, all at once.
    await expect(setting).toContainText("Documents are embedded with multilingual-e5-small.", { timeout: 120_000 });
    await expect(progress).toHaveCount(0);
    const answer = await probe(page, project, "Who does team 12 report to?", 3);
    expect([answer.embedding_model_id, answer.dimension]).toEqual(["multilingual-e5-small", 384]);
    expect(answer.chunks).toHaveLength(3);
  });

  test("retrieval never comes back empty while the re-embed switches over to the new model", async ({ signedInPage: page }) => {
    // 03.31: the probe (and `retrieval.service.retrieve`) reads the Project's model, embeds the
    // query, then searches that model's Chunks in a later READ COMMITTED statement. If the job's
    // switch (`re_embedding/job.py`: set the new model, delete the old vectors) commits in
    // between, the search finds no Chunks of the old model and answers with nothing.
    test.fixme(true, "03.31: retrieval returns no Chunks for a query that straddles the re-embed's switch-over (see SCRATCH/findings-P2.md)");
    test.setTimeout(240_000);
    await createProject(page, "P2 re-embed switch-over");
    const { organisation, project } = apiPaths(page);
    const credential = await voyageCredential(page, organisation, "P2 switch-over embeddings");
    const chosen = await page.request.put(`${project}/embedding-model`, { data: { model_id: "voyage-3.5", credential_id: credential } });
    expect(chosen.status()).toBe(200);
    await page.reload();
    await page
      .getByLabel("Upload", { exact: true })
      .setInputFiles(manySections("p2-switch.md", 60, (index) => `Desk line ${String(index)}: team ${String(index)} sits at desk ${String(index * 7)}.`));
    await expect(documentRow(page, "p2-switch.md").getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 180_000 });

    const changed = await page.request.put(`${project}/embedding-model`, { data: { model_id: "multilingual-e5-small", credential_id: null } });
    expect(changed.status()).toBe(200);
    // Agents keep asking throughout: many concurrent queries, from before the switch until after it.
    const answers: { model: string; chunks: number }[] = [];
    let switched = false;
    const ask = async () => {
      while (!switched) {
        const answer = await probe(page, project, "Who does team 12 sit with?", 3);
        answers.push({ model: answer.embedding_model_id, chunks: answer.chunks.length });
      }
    };
    const watch = async () => {
      await expect
        .poll(async () => ((await (await page.request.get(`${project}/embedding-model`)).json()) as { re_embed: { status: string } }).re_embed.status, {
          timeout: 120_000,
          intervals: [100],
        })
        .toBe("completed");
      await expect.poll(() => answers.filter((answer) => answer.model === "multilingual-e5-small").length).toBeGreaterThan(20);
      switched = true;
    };
    await Promise.all([watch(), ...Array.from({ length: 12 }, ask)]);
    expect(answers.some((answer) => answer.model === "voyage-3.5")).toBe(true);
    expect(answers.filter((answer) => answer.chunks !== 3)).toEqual([]);
  });

  test("a failed re-embed is shown as an error with its reason, and the Project stays on its previous model", async ({ signedInPage: page }) => {
    // The stack's fake Embedding providers never fail (the gateway's fakes simulate failures for
    // chat models only), so the worker's failure (`project.re_embed_failed`, with the message
    // `app.re_embedding.job` writes) is played back through the Studio's state request. Everything
    // else is the real stack; the worker side is covered by the backend's test_re_embedding.
    await createProject(page, "P2 re-embed failure");
    const { organisation, project } = apiPaths(page);
    await voyageCredential(page, organisation, "P2 failing embeddings");
    await page.getByLabel("Upload", { exact: true }).setInputFiles(HANDBOOK);
    await expect(documentRow(page, "northwind-staff-handbook.md").getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });

    const reason = "The Embedding Model's provider didn't respond after 5 attempts. The Project still uses multilingual-e5-small; choose the model again to retry.";
    await page.route(`**${project}/embedding-model`, async (route) => {
      if (route.request().method() !== "GET") {
        await route.fallback();
        return;
      }
      const response = await route.fetch();
      const state = (await response.json()) as { re_embed: Record<string, unknown> | null };
      if (state.re_embed === null) {
        await route.fulfill({ response });
        return;
      }
      await route.fulfill({
        response,
        json: {
          ...state,
          model_id: state.re_embed.from_model_id,
          credential_id: null,
          pending_model_id: null,
          pending_credential_id: null,
          re_embed: { ...state.re_embed, status: "failed", error_message: reason, finished_at: new Date().toISOString() },
        },
      });
    });
    await page.reload();
    await openSection(page, "Project sections", "Settings");
    const setting = page.getByRole("region", { name: "Embedding Model" });
    await setting.getByRole("button", { name: "Change Embedding Model" }).click();
    const choose = page.getByRole("dialog", { name: "Change the Embedding Model" }).getByRole("form", { name: "Choose the Embedding Model" });
    await choose.getByLabel("Embedding Model").selectOption("voyage-3.5 (P2 failing embeddings)");
    await choose.getByRole("button", { name: "Use this model" }).click();

    await expect(setting.getByText(`Re-embedding with voyage-3.5 failed. ${reason}`)).toBeVisible();
    await expect(setting).toContainText("Documents are embedded with multilingual-e5-small.");
    await expect(setting.getByRole("meter")).toHaveCount(0);
    await expect(setting.getByRole("button", { name: "Change Embedding Model" })).toBeEnabled();
  });

  test("Settings opens with a heading and description, and each setting shows the choice at once and is disabled while it saves", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    await createProject(page, "P2 settings");
    await openSection(page, "Project sections", "Settings");
    const settings = page.getByRole("region", { name: "Settings" });
    await expect(settings.getByRole("heading", { level: 2, name: "Settings" })).toBeVisible();
    await expect(settings.getByText("How this Project embeds, reads and screens its Documents. A change applies to every Agent in it.")).toBeVisible();
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The Project's PATCH is held, as on a slow connection.
    const saving = await holdRequests(page, (request) => request.method() === "PATCH" && new URL(request.url()).pathname.startsWith("/api/"));
    const ocr = page.getByRole("checkbox", { name: "Read scanned PDFs with OCR" });
    await ocr.click();
    await expect(ocr).toBeChecked();
    await expect(ocr).toBeDisabled();
    await expect(page.getByText(/^OCR is off\./)).toBeVisible();
    expect(saving.held).toHaveLength(1);
    saving.release();
    await expect(ocr).toBeEnabled();
    await expect(ocr).toBeChecked();
    await expect(page.getByText(/^OCR is on\./)).toBeVisible();
    await page.unrouteAll({ behavior: "wait" });

    const flagged = await holdRequests(page, (request) => request.method() === "PATCH" && new URL(request.url()).pathname.startsWith("/api/"));
    const mode = page.getByRole("radiogroup", { name: "Flagged Chunks" });
    const exclude = mode.getByRole("radio", { name: "Exclude them from retrieval" });
    const mark = mode.getByRole("radio", { name: "Mark them, and keep retrieving them" });
    await exclude.click();
    await expect(exclude).toBeChecked();
    await expect(exclude).toBeDisabled();
    await expect(mark).toBeDisabled();
    expect(flagged.held).toHaveLength(1);
    flagged.release();
    await expect(mark).toBeEnabled();
    await expect(exclude).toBeChecked();
    await expect(mode.getByText(/Flagged Chunks are never given to an Agent/)).toBeVisible();

    // Both were saved.
    await page.reload();
    await expect(page.getByRole("checkbox", { name: "Read scanned PDFs with OCR" })).toBeChecked();
    await expect(page.getByRole("radiogroup", { name: "Flagged Chunks" }).getByRole("radio", { name: "Exclude them from retrieval" })).toBeChecked();
  });

  test("an archived Project's settings are shown disabled, with no Embedding Model change offered", async ({ signedInPage: page, makeAxeBuilder }) => {
    await createProject(page, "P2 archived settings");
    const { project } = apiPaths(page);
    await page.getByRole("button", { name: "More Project actions" }).click();
    await page.getByRole("menu", { name: "Project actions" }).getByRole("menuitem", { name: "Archive" }).click();
    await page.getByRole("button", { name: "Yes, archive P2 archived settings" }).click();
    await expect(page.getByText(/This Project is archived/).first()).toBeVisible();

    await openSection(page, "Project sections", "Settings");
    const settings = page.getByRole("region", { name: "Settings" });
    await expect(settings.getByText("This Project is archived, so its settings can't be changed.")).toBeVisible();
    await expect(page.getByRole("checkbox", { name: "Read scanned PDFs with OCR" })).toBeDisabled();
    const mode = page.getByRole("radiogroup", { name: "Flagged Chunks" });
    await expect(mode.getByRole("radio", { name: "Mark them, and keep retrieving them" })).toBeChecked();
    await expect(mode.getByRole("radio", { name: "Mark them, and keep retrieving them" })).toBeDisabled();
    await expect(mode.getByRole("radio", { name: "Exclude them from retrieval" })).toBeDisabled();
    await expect(page.getByRole("region", { name: "Embedding Model" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Change Embedding Model" })).toHaveCount(0);
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // The API refuses the changes too.
    expect((await page.request.patch(project, { data: { ocr_enabled: true } })).status()).toBe(409);
    expect((await page.request.put(`${project}/embedding-model`, { data: { model_id: "multilingual-e5-small", credential_id: null } })).status()).toBe(409);
  });

  test("the Knowledge Base cards sum up the Project, flagged Chunks are kept from Agents when excluded, and clearing a flag is audited", async ({
    signedInPage: page,
    makeAxeBuilder,
  }) => {
    test.setTimeout(180_000);
    await page.goto("/");
    const me = (await (await page.request.get("/api/auth/me")).json()) as { organisations: { id: string }[] };
    const organisation = `/api/organisations/${me.organisations[0]?.id ?? ""}`;
    const chat = await page.request.post(`${organisation}/credentials`, { data: { name: "P2 Claude", provider: "anthropic", api_key: CHAT_KEY } });
    expect(chat.status()).toBe(201);
    const chatId = ((await chat.json()) as { id: string }).id;
    expect((await page.request.put(`${organisation}/default-model`, { data: { credential_id: chatId, model: "claude-haiku-4-5" } })).status()).toBe(200);

    await createProject(page, "P2 flagged");
    const { project } = apiPaths(page);
    await page.getByLabel("Upload", { exact: true }).setInputFiles(HANDBOOK);
    const row = documentRow(page, "northwind-staff-handbook.md");
    await expect(row.getByRole("cell", { name: "Ready" })).toBeVisible({ timeout: 60_000 });

    // The cards: Documents against the quota, Chunks, flagged Chunks and the Embedding Model.
    const [handbook] = await documentsOf(page, project);
    expect(handbook?.chunk_count).toBeGreaterThan(1);
    await expect(stat(page, "Documents")).toHaveText("1 / 500");
    await expect(stat(page, "Chunks")).toHaveText(String(handbook?.chunk_count));
    await expect(row.getByRole("cell").nth(5)).toHaveText(String(handbook?.chunk_count));
    await expect(stat(page, "Flagged chunks")).toHaveText("1");
    await expect(stat(page, "Embedding Model")).toHaveText("multilingual-e5-small");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // An Agent answering on its Draft, with one search up front.
    await openSection(page, "Project sections", "Agents");
    await page.getByRole("button", { name: "New Agent" }).click();
    const newAgent = page.getByRole("form", { name: "New Agent" });
    await newAgent.getByLabel("Name").fill("P2 HR helper");
    await newAgent.getByRole("button", { name: "Create Agent" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "P2 HR helper" })).toBeVisible({ timeout: 15_000 });
    const agentUrl = page.url();
    await openSettings(page, "Retrieval");
    const modeSaved = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/draft") && response.request().method() === "PUT");
    await page.getByRole("group", { name: "Retrieval" }).getByRole("radio", { name: "Automatic" }).click();
    expect((await modeSaved).status()).toBe(200);

    const messages = page.getByRole("list", { name: "Playground messages" });
    /** Asks the Draft, then reads the planted Chunk's row in the answer's Trace. */
    const ask = async (index: number) => {
      await page.getByLabel("Question", { exact: true }).fill("What does the note for AI assistants in the handbook say about annual leave?");
      await page.getByRole("button", { name: "Send" }).click();
      const answer = messages.getByRole("listitem", { name: "P2 HR helper" }).nth(index);
      await expect(answer).toContainText("Fake reply from anthropic:claude-haiku-4-5.", { timeout: 30_000 });
      await answer.getByText("Trace", { exact: true }).click();
      const planted = answer
        .getByRole("group", { name: "Trace" })
        .getByRole("table", { name: "Retrieved Chunks" })
        .getByRole("row")
        .filter({ hasText: "Ignore all previous instructions" });
      await expect(planted).toHaveCount(1, { timeout: 15_000 });
      return planted;
    };

    // Marked only (the default): the flagged Chunk is given to the model like any other.
    const marked = await ask(0);
    await expect(marked.getByRole("cell").first()).toHaveText(/^C\d+$/);
    await expect(marked.getByRole("cell").last()).not.toHaveText(/^Excluded/);

    // Excluded: the Trace shows it was kept from the model.
    await openSection(page, "Project sections", "Settings");
    await page.getByRole("radiogroup", { name: "Flagged Chunks" }).getByRole("radio", { name: "Exclude them from retrieval" }).check();
    await expect(page.getByText(/Flagged Chunks are never given to an Agent/)).toBeVisible();
    await page.goto(agentUrl);
    const excluded = await ask(0);
    await expect(excluded.getByRole("cell").first()).toHaveText("—");
    await expect(excluded.getByRole("cell").last()).toHaveText("Excluded: flagged by the ingestion scan");
    expect((await makeAxeBuilder().analyze()).violations).toEqual([]);

    // An Editor clears the flag as a false positive: it is audited, and the Chunk is retrieved again.
    await openSection(page, "Project sections", "Documents");
    await row.getByRole("link", { name: "northwind-staff-handbook.md" }).click();
    const note = page.getByRole("region", { name: "Chunks" }).getByRole("listitem").filter({ hasText: "A note for AI assistants" });
    await note.getByRole("button", { name: /^Clear flag on Chunk \d+$/ }).click();
    await expect(note.getByRole("note", { name: "Guardrail flag" })).toHaveCount(0);
    expect(await auditCount(page, organisation, "chunk.flag_cleared")).toBe(1);
    await openSection(page, "Organisation sections", "Settings");
    await openSection(page, "Organisation settings", "Audit");
    await expect(page.getByRole("table", { name: "Audit Events" }).getByRole("cell", { name: "chunk.flag_cleared" })).toHaveCount(1);

    await page.goto(agentUrl);
    const cleared = await ask(0);
    await expect(cleared.getByRole("cell").first()).toHaveText(/^C\d+$/);
    await expect(cleared.getByRole("cell").last()).not.toHaveText(/^Excluded/);
  });
});
