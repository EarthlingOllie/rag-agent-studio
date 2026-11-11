// Sandbox-only evidence for ticket 12-02, after 11-13's shots.test.ts. There is no compose stack
// here, so it serves the built Studio (apps/studio/dist) and answers the API with the unit tests'
// MSW fakes (apps/studio/src/test). It visits the pages 12-02 touches (the Projects page and a
// Project's page) and their Project details dialog in both modes, wide (1440) and narrow (390), in
// light and dark; screenshots each, runs axe (WCAG 2.2 AA tags) and checks horizontal overflow and
// that the dialog returns focus to its button on Escape. Writes shots-axe.log beside screenshots/.
import { createRequire } from "node:module";
import { readFile, writeFile } from "node:fs/promises";
import { createServer, type IncomingMessage, type Server } from "node:http";
import { extname, join } from "node:path";

import type { Browser, Page } from "@playwright/test";
import { http as mock, HttpResponse } from "msw";

import { fakeAccountApi } from "../../../../frontend/apps/studio/src/test/account";
import { fakeAgentsApi } from "../../../../frontend/apps/studio/src/test/agents";
import { adaSession, fakeAuthApi } from "../../../../frontend/apps/studio/src/test/auth";
import { aDocument, aTag, fakeDocumentsApi } from "../../../../frontend/apps/studio/src/test/documents";
import { fakeProjectsApi, hrProject } from "../../../../frontend/apps/studio/src/test/projects";
import { server } from "../../../../frontend/apps/studio/src/test/server";

const require = createRequire(join(process.cwd(), "package.json"));
const { default: AxeBuilder } = require("@axe-core/playwright");
const { chromium } = require("@playwright/test");
const { getResponse } = require("msw");

const DIST = join(process.cwd(), "apps/studio/dist");
const OUT = process.env.SHOTS_DIR ?? "shots";
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const ORG = adaSession.active_organisation_id;
const PROJECTS = `/organisations/${ORG}/projects`;
const PROJECT = `${PROJECTS}/${hrProject.id}`;
const TOO_LONG = { detail: [{ loc: ["body", "name"], msg: "too long" }] };

function signedIn() {
  server.resetHandlers();
  fakeAuthApi({ signedInAs: adaSession });
  fakeAccountApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeDocumentsApi({ tags: [aTag()], documents: [aDocument()] });
  fakeAgentsApi();
}

const TYPES: Record<string, string> = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png" };

async function body(request: IncomingMessage): Promise<Buffer | undefined> {
  if (request.method === "GET" || request.method === "HEAD") return undefined;
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks);
}

async function serve(): Promise<{ http: Server; base: string }> {
  const http = createServer((request, response) => {
    void (async () => {
      const url = new URL(request.url ?? "/", "http://localhost");
      if (url.pathname.startsWith("/api/")) {
        const fetchRequest = new Request(url, { method: request.method, headers: request.headers as HeadersInit, body: await body(request) });
        const answer = await getResponse(server.listHandlers(), fetchRequest);
        if (!answer) {
          response.writeHead(404, { "content-type": "application/json" }).end(JSON.stringify({ detail: "Not found" }));
          return;
        }
        response.writeHead(answer.status, Object.fromEntries(answer.headers));
        response.end(Buffer.from(await answer.arrayBuffer()));
        return;
      }
      const file = extname(url.pathname) ? join(DIST, url.pathname) : join(DIST, "index.html");
      try {
        const content = await readFile(file);
        response.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" }).end(content);
      } catch {
        response.writeHead(404).end();
      }
    })();
  });
  await new Promise<void>((resolve) => http.listen(0, "127.0.0.1", resolve));
  const address = http.address();
  return { http, base: `http://127.0.0.1:${String(typeof address === "object" && address ? address.port : 0)}` };
}

async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
  await page.locator("h1").first().waitFor();
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(200);
}

/** Each shot: where to start and what to do there before the screenshot. */
const SHOTS: { name: string; path: string; act?: (page: Page) => Promise<void> }[] = [
  { name: "projects", path: PROJECTS },
  {
    name: "new-project-dialog",
    path: PROJECTS,
    act: async (page) => {
      await page.getByRole("button", { name: "New Project" }).click();
      await page.getByRole("dialog", { name: "New Project" }).waitFor();
      await page.getByLabel("Name").fill("Product support");
      await page.getByLabel("Description").fill("Answers for customers");
    },
  },
  {
    name: "new-project-refused",
    path: PROJECTS,
    act: async (page) => {
      server.use(mock.post("*/api/organisations/:organisationId/projects", () => HttpResponse.json(TOO_LONG, { status: 422 })));
      await page.getByRole("button", { name: "New Project" }).click();
      const dialog = page.getByRole("dialog", { name: "New Project" });
      await dialog.getByLabel("Name").fill("Product support");
      await dialog.getByRole("button", { name: "Create Project" }).click();
      await dialog.getByRole("alert").waitFor();
    },
  },
  { name: "project", path: PROJECT },
  {
    name: "project-details-dialog",
    path: PROJECT,
    act: async (page) => {
      await page.getByRole("button", { name: "Edit details" }).click();
      await page.getByRole("dialog", { name: "Project details" }).waitFor();
    },
  },
  {
    name: "project-details-saved",
    path: PROJECT,
    act: async (page) => {
      await page.getByRole("button", { name: "Edit details" }).click();
      const dialog = page.getByRole("dialog", { name: "Project details" });
      await dialog.getByLabel("Name").fill("People team");
      await dialog.getByRole("button", { name: "Save" }).click();
      await page.getByRole("heading", { level: 1, name: "People team" }).waitFor();
      await page.getByText("Project details saved").waitFor();
    },
  },
];

const RUNS = [
  { suffix: "light", colorScheme: "light", viewport: { width: 1440, height: 900 } },
  { suffix: "dark", colorScheme: "dark", viewport: { width: 1440, height: 900 } },
  { suffix: "narrow-light", colorScheme: "light", viewport: { width: 390, height: 844 } },
  { suffix: "narrow-dark", colorScheme: "dark", viewport: { width: 390, height: 844 } },
] as const;

type Violation = { id: string; nodes: { target: string[] }[] };

test("12-02 pages and the Project details dialog, wide and narrow, light and dark", async () => {
  const { http, base } = await serve();
  const browser: Browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome" });
  const report: string[] = [];
  let failures = 0;
  for (const run of RUNS) {
    const context = await browser.newContext({ baseURL: base, viewport: run.viewport, colorScheme: run.colorScheme });
    for (const shot of SHOTS) {
      signedIn();
      const page = await context.newPage();
      await page.goto(shot.path);
      await settle(page);
      if (shot.act) await shot.act(page);
      await page.waitForTimeout(150);
      const seen = await page.evaluate(() => ({
        h1: document.querySelector("h1")?.textContent ?? "",
        dialog: document.querySelector('[role="dialog"]')?.getAttribute("aria-labelledby") ? document.querySelector('[role="dialog"] h2')?.textContent ?? "" : "none",
        overflow: document.documentElement.scrollWidth - window.innerWidth,
      }));
      await page.screenshot({ path: `${OUT}/${shot.name}-${run.suffix}.png`, fullPage: true });
      const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
      failures += results.violations.length + (seen.overflow > 0 ? 1 : 0);
      report.push(
        `${run.suffix.padEnd(13)} ${shot.name.padEnd(24)} h1 "${seen.h1}"; dialog "${seen.dialog}"; horizontal overflow ${String(Math.max(0, seen.overflow))}px; axe violations: ${String(results.violations.length)}` +
          (results.violations as Violation[]).map((v) => `\n    ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`).join(""),
      );
      await page.close();
    }
    // Escape closes each dialog unsaved and focus returns to the button that opened it.
    for (const [path, opener, title] of [
      [PROJECTS, "New Project", "New Project"],
      [PROJECT, "Edit details", "Project details"],
    ] as const) {
      signedIn();
      const page = await context.newPage();
      await page.goto(path);
      await settle(page);
      await page.getByRole("button", { name: opener }).focus();
      await page.keyboard.press("Enter");
      await page.getByRole("dialog", { name: title }).waitFor();
      const first = await page.evaluate(() => (document.activeElement as HTMLInputElement | null)?.name ?? "");
      await page.keyboard.press("Escape");
      await page.getByRole("dialog", { name: title }).waitFor({ state: "detached" });
      const back = await page.evaluate(() => document.activeElement?.textContent ?? "");
      const ok = first === "name" && back === opener;
      failures += ok ? 0 : 1;
      report.push(`${run.suffix.padEnd(13)} keyboard: ${opener} (Enter) opens "${title}" with focus on "${first}"; Escape closes it; focus back on "${back}": ${ok ? "ok" : "PROBLEM"}`);
      await page.close();
    }
    await context.close();
  }
  await browser.close();
  http.close();
  await writeFile(join(OUT, "..", "shots-axe.log"), `${report.join("\n")}\ntotal axe violations, overflows and focus problems: ${String(failures)}\n`);
  if (failures > 0) throw new Error(`${String(failures)} problems`);
});
