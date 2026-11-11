// Sandbox-only: light and dark screenshots, and axe in both Appearances, of the Studio pages this
// ticket changes. There is no Docker daemon here, so instead of the compose stack it serves the
// built Studio (apps/studio/dist) and answers the API with fixed fixtures (the unit tests' Ada,
// HR handbook Project and handbook.pdf). Run from frontend/ after `pnpm build`:
//   SHOTS_DIR=../docs/tickets/11-studio-design/11-02-evidence/screenshots node ../docs/tickets/11-studio-design/11-02-evidence/shots.mjs
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { extname, join } from "node:path";

// Resolve Playwright and axe from frontend/ (the working directory), not from this folder.
const require = createRequire(join(process.cwd(), "package.json"));
const { default: AxeBuilder } = require("@axe-core/playwright");
const { chromium } = require("@playwright/test");

const DIST = join(process.cwd(), "apps/studio/dist");
const OUT = process.env.SHOTS_DIR ?? "shots";
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

const ORG = "0b6f3a3e-6f53-4a5e-9a39-6d2b8f0c1e02";
const PROJECT = "7c2d1e69-1e7f-4d2c-8e2f-2a2b7d1a0b01";
const DOC = "d0c00000-0000-4000-8000-000000000001";
const session = {
  member: { id: "6a1b0c58-0d6e-4c1b-9d1e-1f1a6c0f0a01", name: "Ada Lovelace", email: "ada@example.test", mfa_enabled: false },
  organisations: [{ id: ORG, name: "Analytical Engines", role: "owner", mfa_required: false }],
  active_organisation_id: ORG,
};
const project = {
  id: PROJECT, name: "HR handbook", description: "Policies for the HR Agent", created_at: "2026-10-01T09:30:00Z",
  archived_at: null, document_count: 1, agent_count: 0, embedding_model_id: "multilingual-e5-small", ocr_enabled: false,
  embedding_credential_id: null, flagged_chunk_mode: "mark",
};
const document = {
  id: DOC, name: "handbook.pdf", mime_type: "application/pdf", size_bytes: 2_621_440, content_hash: "a".repeat(64),
  status: "ready", error_message: null, error_category: null, attempt_count: 1, edition: 1, chunk_count: 1,
  flagged_chunk_count: 0, tags: [], created_at: "2026-11-05T09:00:00Z", updated_at: "2026-11-05T09:01:00Z", replacement: null,
};
const markdown = [
  "# Northwind staff handbook", "", "## Annual leave", "",
  "Everyone gets **25 days** of annual leave a year. Book it in `HR Portal` at least two weeks ahead.", "",
  "| Years of service | Extra days |", "| --- | --- |", "| 0 to 4 | 0 |", "| 5 or more | 3 |", "",
  "```", "leave = 25 + extra", "```", "", "- Carry over up to 5 days", "- Ask your manager first", "",
  "See [the policy page](https://example.test/policy).",
].join("\n");
const chunk = {
  id: "c0c00000-0000-4000-8000-000000000000", ordinal: 0, text: "Everyone gets 25 days of annual leave a year.",
  heading_path: ["Northwind staff handbook", "Annual leave"], page_start: 1, page_end: 1,
  embedding_model_id: "multilingual-e5-small", flag: null,
};

let signedIn = false;
function api(method, path) {
  const p = `/api/organisations/${ORG}/projects/${PROJECT}`;
  const routes = {
    "GET /api/health": { status: "ok", checks: { database: "ok", redis: "ok" } },
    "GET /api/health/worker": { status: "ok", reply: "pong" },
    [`GET /api/organisations/${ORG}`]: { id: ORG, name: "Analytical Engines", role: "owner", require_mfa: false, retention_days: 90 },
    [`GET /api/organisations/${ORG}/projects`]: [project],
    [`GET ${p}`]: project,
    [`GET ${p}/documents`]: [document],
    [`GET ${p}/documents/statuses`]: [],
    [`GET ${p}/documents/${DOC}`]: { ...document, markdown },
    [`GET ${p}/documents/${DOC}/chunks`]: { items: [chunk], total: 1, offset: 0, limit: 50 },
    [`GET ${p}/tags`]: [],
    [`GET ${p}/agents`]: [],
    [`GET ${p}/uploads/limits`]: { max_file_bytes: 52_428_800, max_files: 20 },
    [`GET ${p}/instructions/rollout`]: { current_version: null, behind: 0, agents: [] },
  };
  if (path === "/api/auth/me") return signedIn ? [200, session] : [401, { detail: "Not signed in" }];
  const body = routes[`${method} ${path}`];
  return body === undefined ? [404, { detail: "Not found" }] : [200, body];
}

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png" };
const server = createServer((request, response) => {
  void (async () => {
    const url = new URL(request.url ?? "/", "http://localhost");
    if (url.pathname.startsWith("/api/")) {
      const [status, body] = api(request.method ?? "GET", url.pathname);
      response.writeHead(status, { "content-type": "application/json" });
      response.end(JSON.stringify(body));
      return;
    }
    const file = extname(url.pathname) ? join(DIST, url.pathname) : join(DIST, "index.html");
    try {
      const content = await readFile(file);
      response.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
      response.end(content);
    } catch {
      response.writeHead(404).end();
    }
  })();
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(undefined)));
const base = `http://127.0.0.1:${String(server.address().port)}`;

const PAGES = [
  { name: "sign-in", path: "/sign-in", signedIn: false, ready: { role: "heading", name: "Sign in" } },
  { name: "sign-up", path: "/sign-up", signedIn: false, ready: { role: "heading", name: "Create your account" } },
  { name: "status", path: "/status", signedIn: false, ready: { role: "heading", name: /status/i } },
  { name: "projects", path: `/organisations/${ORG}/projects`, signedIn: true, ready: { role: "link", name: "HR handbook" } },
  { name: "documents", path: `/organisations/${ORG}/projects/${PROJECT}`, signedIn: true, ready: { role: "link", name: "handbook.pdf" } },
  { name: "document-viewer", path: `/organisations/${ORG}/projects/${PROJECT}/documents/${DOC}`, signedIn: true, ready: { role: "heading", name: "Annual leave" } },
];

const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome" });
const report = [];
let failures = 0;
// light and dark: no choice made, so the system preference decides. chosen-dark: the system says
// light but the Member chose dark (localStorage), which initAppearance() applies before rendering.
const APPEARANCES = [
  { label: "light", colorScheme: "light", chosen: undefined },
  { label: "dark", colorScheme: "dark", chosen: undefined },
  { label: "chosen-dark", colorScheme: "light", chosen: "dark" },
];
for (const appearance of APPEARANCES) {
  const context = await browser.newContext({ baseURL: base, viewport: { width: 1280, height: 800 }, colorScheme: appearance.colorScheme });
  if (appearance.chosen) await context.addInitScript((chosen) => window.localStorage.setItem("studio.appearance", chosen), appearance.chosen);
  const page = await context.newPage();
  for (const target of PAGES) {
    signedIn = target.signedIn;
    await page.goto(target.path);
    await page.getByRole(target.ready.role, { name: target.ready.name }).first().waitFor();
    await page.evaluate(() => document.fonts.ready);
    const seen = await page.evaluate(() => ({
      font: getComputedStyle(document.body).fontFamily.split(",")[0],
      canvas: getComputedStyle(document.body).backgroundColor,
      attribute: document.documentElement.dataset.appearance ?? "(none: system)",
    }));
    await page.screenshot({ path: `${OUT}/${target.name}-${appearance.label}.png`, fullPage: true });
    const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
    failures += results.violations.length;
    report.push(`${appearance.label.padEnd(11)} ${target.name.padEnd(16)} font ${seen.font}; body ${seen.canvas}; data-appearance ${seen.attribute}; axe violations: ${String(results.violations.length)}` +
      results.violations.map((v) => `\n    ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`).join(""));
  }
  await context.close();
}
await browser.close();
server.close();
console.log(report.join("\n"));
console.log(`total axe violations: ${String(failures)}`);
process.exit(failures === 0 ? 0 : 1);
