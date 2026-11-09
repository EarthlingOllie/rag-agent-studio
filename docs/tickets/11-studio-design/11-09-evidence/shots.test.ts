// Sandbox-only: light and dark screenshots, and axe in both Appearances, of the Agents section in
// every state this ticket changed: the list with each Live state and alert, the Archived filter,
// the empty list, the New Agent dialog, the bulk bar, the Revert confirmation and the per-Agent
// results. There is no Docker daemon here, so instead of the compose stack it serves the built
// Studio (apps/studio/dist) and answers the API with the unit tests' own MSW fakes
// (apps/studio/src/test), run through MSW's getResponse instead of a mocked fetch. See
// shots.config.mjs for the command.
import { createRequire } from "node:module";
import { readFile, writeFile } from "node:fs/promises";
import { createServer, type IncomingMessage } from "node:http";
import { extname, join } from "node:path";

import { fakeAccountApi } from "../../../../frontend/apps/studio/src/test/account";
import { fakeAgentsApi, hrHelper, oldHelper } from "../../../../frontend/apps/studio/src/test/agents";
import { adaSession, fakeAuthApi } from "../../../../frontend/apps/studio/src/test/auth";
import { fakeBulkApi, rolloutAgent } from "../../../../frontend/apps/studio/src/test/bulk";
import { fakeProjectsApi, hrProject } from "../../../../frontend/apps/studio/src/test/projects";
import { server } from "../../../../frontend/apps/studio/src/test/server";

// Resolve Playwright and axe from frontend/ (the working directory).
const require = createRequire(join(process.cwd(), "package.json"));
const { default: AxeBuilder } = require("@axe-core/playwright");
const { chromium } = require("@playwright/test");
const { getResponse } = require("msw");

const DIST = join(process.cwd(), "apps/studio/dist");
const OUT = process.env.SHOTS_DIR ?? "shots";
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const ORG = adaSession.active_organisation_id;
const AGENTS = `/organisations/${ORG}/projects/${hrProject.id}/agents`;

const AGENT_LIST = [
  { ...hrHelper, live_version: { id: "a2e00000-0000-4000-8000-000000000103", number: 3 }, has_unpublished_changes: true },
  {
    ...hrHelper,
    id: "a9e00000-0000-4000-8000-000000000002",
    name: "Benefits FAQ",
    live_version: { id: "a2e00000-0000-4000-8000-000000000201", number: 1 },
    budget_exhausted: true,
  },
  { ...hrHelper, id: "a9e00000-0000-4000-8000-000000000004", name: "Payroll", block_rate_alert: true },
  oldHelper,
];

function signedIn(empty: boolean) {
  server.resetHandlers();
  fakeAuthApi({ signedInAs: adaSession });
  fakeAccountApi({ signedInAs: adaSession });
  fakeProjectsApi();
  fakeAgentsApi({ agents: empty ? [] : AGENT_LIST });
  fakeBulkApi({
    rollout: { current_version: null, behind: 0, agents: [rolloutAgent(1, "HR helper", 3, null), rolloutAgent(2, "Benefits FAQ", 1, null)] },
  });
}

type Page = {
  getByRole: (role: string, options?: { name?: string | RegExp; exact?: boolean }) => { click: () => Promise<void>; waitFor: () => Promise<void> };
};
const PAGES: { name: string; empty?: true; act?: (page: Page) => Promise<void> }[] = [
  { name: "agents" },
  { name: "agents-archived", act: (page) => page.getByRole("radio", { name: "Archived" }).click() },
  { name: "agents-empty", empty: true },
  {
    name: "new-agent",
    act: async (page) => {
      await page.getByRole("button", { name: "New Agent" }).click();
      await page.getByRole("dialog").waitFor();
    },
  },
  {
    name: "bulk-bar",
    act: async (page) => {
      await page.getByRole("checkbox", { name: "Select HR helper" }).click();
      await page.getByRole("checkbox", { name: "Select Benefits FAQ" }).click();
    },
  },
  {
    name: "confirm-revert",
    act: async (page) => {
      await page.getByRole("checkbox", { name: "Select HR helper" }).click();
      await page.getByRole("checkbox", { name: "Select Benefits FAQ" }).click();
      await page.getByRole("button", { name: "Revert" }).click();
      await page.getByRole("alertdialog").waitFor();
    },
  },
  {
    name: "revert-results",
    act: async (page) => {
      await page.getByRole("checkbox", { name: "Select HR helper" }).click();
      await page.getByRole("checkbox", { name: "Select Benefits FAQ" }).click();
      await page.getByRole("button", { name: "Revert" }).click();
      await page.getByRole("button", { name: "Yes, revert 2 Agents" }).click();
      await page.getByRole("list", { name: "Results" }).waitFor();
    },
  },
];

const TYPES: Record<string, string> = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".png": "image/png",
};

async function body(request: IncomingMessage): Promise<Buffer | undefined> {
  if (request.method === "GET" || request.method === "HEAD") return undefined;
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks);
}

test("screenshots and axe in both Appearances", async () => {
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
  for (const appearance of APPEARANCES) {
    const context = await browser.newContext({
      baseURL: base,
      viewport: { width: 1280, height: 800 },
      colorScheme: appearance.colorScheme,
    });
    if (appearance.chosen)
      await context.addInitScript((chosen: string) => window.localStorage.setItem("studio.appearance", chosen), appearance.chosen);
    for (const target of PAGES) {
      signedIn(target.empty === true);
      const page = await context.newPage();
      await page.goto(AGENTS);
      await page.waitForLoadState("networkidle");
      await page.getByRole("heading", { level: 2, name: "Agents", exact: true }).waitFor();
      await page.getByRole(target.empty ? "heading" : "table", { name: target.empty ? "No Agents yet" : "Agents", exact: true }).waitFor();
      await page.evaluate(() => document.fonts.ready);
      if (target.act) await target.act(page);
      await page.waitForTimeout(250);
      const seen = await page.evaluate(() => ({
        path: location.pathname,
        canvas: getComputedStyle(document.body).backgroundColor,
      }));
      await page.screenshot({ path: `${OUT}/${target.name}-${appearance.label}.png`, fullPage: true });
      const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
      failures += results.violations.length;
      report.push(
        `${appearance.label.padEnd(11)} ${target.name.padEnd(16)} at ${seen.path}; body ${seen.canvas}; axe violations: ${String(results.violations.length)}` +
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
  await browser.close();
  http.close();
  // Vitest hides a passing test's console, so the report goes next to the screenshots' folder.
  await writeFile(join(OUT, "..", "shots-axe.log"), `${report.join("\n")}\ntotal axe violations: ${String(failures)}\n`);
  if (failures > 0) throw new Error(`${String(failures)} axe violations`);
});
