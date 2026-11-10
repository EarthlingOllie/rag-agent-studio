// Sandbox-only: light and dark screenshots, and axe in both Appearances, of a Project's Settings
// (12-06) at 1440 and 390 wide: the cards, the Embedding Model dialog (with the re-embed warning,
// and for a Project without Documents), a running and a failed Re-embed, and an archived Project.
// There is no Docker daemon here, so instead of the compose stack it serves the built Studio
// (apps/studio/dist) and answers the API with the unit tests' own MSW fakes (apps/studio/src/test),
// run through MSW's getResponse instead of a mocked fetch. See shots.config.mjs for the command.
import { createRequire } from "node:module";
import { readFile, writeFile } from "node:fs/promises";
import { createServer, type IncomingMessage } from "node:http";
import { extname, join } from "node:path";

import type { Schemas } from "../../../../frontend/packages/api-client/src";
import { fakeAccountApi } from "../../../../frontend/apps/studio/src/test/account";
import { fakeAgentsApi, hrHelper } from "../../../../frontend/apps/studio/src/test/agents";
import { adaSession, fakeAuthApi } from "../../../../frontend/apps/studio/src/test/auth";
import { fakeDocumentsApi } from "../../../../frontend/apps/studio/src/test/documents";
import { fakeProjectsApi, hrProject, oldProject, salesProject } from "../../../../frontend/apps/studio/src/test/projects";
import { server } from "../../../../frontend/apps/studio/src/test/server";

// Resolve Playwright, axe and MSW from frontend/ (the working directory).
const require = createRequire(join(process.cwd(), "package.json"));
const { default: AxeBuilder } = require("@axe-core/playwright");
const { chromium } = require("@playwright/test");
const { getResponse, http: mswHttp, HttpResponse } = require("msw");

const DIST = join(process.cwd(), "apps/studio/dist");
const OUT = process.env.SHOTS_DIR ?? "shots";
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const ORG = adaSession.active_organisation_id;
const VOYAGE = "5b0e6c1a-8f3e-4d8a-9c55-0d6f1c2b3a01";

type ReEmbed = Schemas["ReEmbedOut"];
const reEmbed = (overrides: Partial<ReEmbed>): ReEmbed => ({
  id: "0f6f2f1e-3d4c-4b5a-9e8d-7c6b5a4f3e2d",
  status: "running",
  from_model_id: "multilingual-e5-small",
  model_id: "voyage-3.5",
  credential_id: VOYAGE,
  embedded_chunks: 412,
  total_chunks: 1180,
  error_message: null,
  started_at: "2026-11-06T10:00:00Z",
  finished_at: null,
  ...overrides,
});

function signedIn(job: ReEmbed | null) {
  server.resetHandlers();
  fakeAuthApi({ signedInAs: adaSession });
  fakeAccountApi({ signedInAs: adaSession });
  fakeProjectsApi({ projects: [hrProject, salesProject, { ...oldProject, ocr_enabled: true }] });
  fakeDocumentsApi();
  fakeAgentsApi({ agents: [hrHelper] });
  server.use(
    mswHttp.get("*/api/organisations/:organisationId/embedding-models", () =>
      HttpResponse.json([
        { model_id: "multilingual-e5-small", name: "multilingual-e5-small (built in)", provider: "local", dimension: 384, tokenizer: "intfloat/multilingual-e5-small", token_limit: 512, credential_id: null, credential_name: null },
        { model_id: "voyage-3.5", name: "voyage-3.5", provider: "voyage", dimension: 1024, tokenizer: "voyageai/voyage-3.5", token_limit: 32000, credential_id: VOYAGE, credential_name: "Voyage production" },
      ]),
    ),
    mswHttp.get("*/api/organisations/:organisationId/projects/:projectId/embedding-model", () =>
      HttpResponse.json({
        model_id: "multilingual-e5-small",
        credential_id: null,
        pending_model_id: job?.status === "running" ? "voyage-3.5" : null,
        pending_credential_id: job?.status === "running" ? VOYAGE : null,
        re_embed: job,
      }),
    ),
  );
}

const P = (id: string) => `/organisations/${ORG}/projects/${id}/settings`;
const FAILED =
  "The Embedding Model's provider didn't respond after 4 attempts. The Project still uses multilingual-e5-small; choose the model again to retry.";

type Page = import("@playwright/test").Page;
const openChange = async (page: Page) => {
  await page.getByRole("button", { name: "Change Embedding Model" }).click();
  await page.getByRole("dialog", { name: "Change the Embedding Model" }).getByRole("combobox", { name: "Embedding Model" }).waitFor();
};
const PAGES: { name: string; path: string; job?: ReEmbed; act?: (page: Page) => Promise<void> }[] = [
  { name: "project-settings", path: P(hrProject.id) },
  { name: "dialog-embedding-model", path: P(hrProject.id), act: openChange },
  { name: "dialog-embedding-model-no-documents", path: P(salesProject.id), act: openChange },
  { name: "re-embed-running", path: P(hrProject.id), job: reEmbed({}) },
  { name: "re-embed-failed", path: P(hrProject.id), job: reEmbed({ status: "failed", error_message: FAILED }) },
  { name: "project-settings-archived", path: P(oldProject.id) },
  {
    name: "flagged-saving",
    path: P(hrProject.id),
    act: async (page) => {
      // The save never answers, so the card stays in its saving state: the choice shown, disabled.
      server.use(mswHttp.patch("*/api/organisations/:organisationId/projects/:projectId", () => new Promise(() => {})));
      await page.getByRole("radio", { name: "Exclude them from retrieval" }).check();
    },
  },
];

const TYPES: Record<string, string> = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".woff2": "font/woff2",
};

async function body(request: IncomingMessage): Promise<Buffer | undefined> {
  if (request.method === "GET" || request.method === "HEAD") return undefined;
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks);
}

test("screenshots and axe in both Appearances, wide and narrow", async () => {
  const http = createServer((request, response) => {
    void (async () => {
      const url = new URL(request.url ?? "/", "http://localhost");
      if (url.pathname.startsWith("/api/")) {
        const fetchRequest = new Request(url, {
          method: request.method,
          headers: request.headers as HeadersInit,
          body: await body(request),
        });
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
  const base = `http://127.0.0.1:${String(typeof address === "object" && address ? address.port : 0)}`;

  const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome" });
  const report: string[] = [];
  let failures = 0;
  // light and dark: no choice made, so the system preference decides. chosen-dark: the system says
  // light but the Member chose dark (localStorage), which initAppearance() applies before rendering.
  const APPEARANCES = [
    { label: "light", colorScheme: "light", chosen: undefined },
    { label: "dark", colorScheme: "dark", chosen: undefined },
    { label: "chosen-dark", colorScheme: "light", chosen: "dark" },
  ];
  const WIDTHS = [
    { label: "wide", width: 1440, height: 900 },
    { label: "narrow", width: 390, height: 844 },
  ];
  for (const size of WIDTHS) {
    for (const appearance of APPEARANCES) {
      const context = await browser.newContext({
        baseURL: base,
        viewport: { width: size.width, height: size.height },
        colorScheme: appearance.colorScheme,
      });
      if (appearance.chosen)
        await context.addInitScript((chosen: string) => window.localStorage.setItem("studio.appearance", chosen), appearance.chosen);
      for (const target of PAGES) {
        signedIn(target.job ?? null);
        const page = await context.newPage();
        await page.goto(target.path);
        await page.waitForLoadState("networkidle");
        await page.getByRole("heading", { level: 2, name: "Settings" }).waitFor();
        await page.getByRole("region", { name: "OCR" }).waitFor();
        await page.evaluate(() => document.fonts.ready);
        if (target.act) await target.act(page);
        await page.waitForTimeout(250);
        const seen = await page.evaluate(() => ({
          path: location.pathname,
          canvas: getComputedStyle(document.body).backgroundColor,
          overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
        }));
        const name = `${target.name}-${size.label}-${appearance.label}`;
        await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
        const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
        failures += results.violations.length + (seen.overflow ? 1 : 0);
        report.push(
          `${name.padEnd(56)} at ${seen.path}; body ${seen.canvas}; horizontal scroll: ${seen.overflow ? "YES" : "no"}; axe violations: ${String(results.violations.length)}` +
            results.violations
              .map(
                (v: { id: string; nodes: { target: string[]; failureSummary?: string }[] }) =>
                  `\n    ${v.id}: ${v.nodes.map((n) => `${n.target.join(" ")} [${(n.failureSummary ?? "").split("\n").slice(1).join(" ").trim()}]`).join(", ")}`,
              )
              .join(""),
        );
        await page.close();
      }
      await context.close();
    }
  }
  await browser.close();
  http.close();
  // Vitest hides a passing test's console, so the report goes next to the screenshots' folder.
  await writeFile(join(OUT, "..", "shots-axe.log"), `${report.join("\n")}\ntotal axe violations and horizontal scrolls: ${String(failures)}\n`);
  if (failures > 0) throw new Error(`${String(failures)} axe violations or horizontal scrolls`);
});
