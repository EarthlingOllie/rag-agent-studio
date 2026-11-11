// Sandbox-only: light and dark screenshots, and axe in both Appearances, of the Organisation cost
// page (12-04) at 1440 and 390 wide: by Project, by Agent, nothing spent, bad dates, loading, an
// Editor's view, and the Audit page whose filters moved to the same recipes.
// There is no Docker daemon here, so instead of the compose stack it serves the built Studio
// (apps/studio/dist) and answers the API with the unit tests' own MSW fakes (apps/studio/src/test),
// run through MSW's getResponse instead of a mocked fetch. See shots.config.mjs for the command.
import { createRequire } from "node:module";
import { readFile, writeFile } from "node:fs/promises";
import { createServer, type IncomingMessage } from "node:http";
import { extname, join } from "node:path";

import { fakeAccountApi } from "../../../../frontend/apps/studio/src/test/account";
import { fakeAuditApi } from "../../../../frontend/apps/studio/src/test/audit";
import { adaSession, fakeAuthApi, type Session } from "../../../../frontend/apps/studio/src/test/auth";
import { fakeCostApi } from "../../../../frontend/apps/studio/src/test/cost";
import { fakeProjectsApi } from "../../../../frontend/apps/studio/src/test/projects";
import { server } from "../../../../frontend/apps/studio/src/test/server";

// Resolve Playwright, axe and MSW from frontend/ (the working directory).
const require = createRequire(join(process.cwd(), "package.json"));
const { default: AxeBuilder } = require("@axe-core/playwright");
const { chromium } = require("@playwright/test");
const { getResponse, http: mswHttp } = require("msw");

const DIST = join(process.cwd(), "apps/studio/dist");
const OUT = process.env.SHOTS_DIR ?? "shots";
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const ORG = adaSession.active_organisation_id;
const editorSession: Session = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};

type Page = import("@playwright/test").Page;
interface Target {
  name: string;
  path: string;
  session?: Session;
  setup?: () => void;
  /** What shows once the page is ready (after `act`). */
  ready: (page: Page) => Promise<void>;
  act?: (page: Page) => Promise<void>;
}

const COST = `/organisations/${ORG}/cost`;
const table = (name: string) => async (page: Page) => {
  await page.getByRole("table", { name }).waitFor();
};
const PAGES: Target[] = [
  { name: "cost-by-project", path: COST, setup: () => fakeCostApi(), ready: table("Cost by Project") },
  {
    name: "cost-by-agent",
    path: COST,
    setup: () => fakeCostApi(),
    act: async (page) => {
      await page.getByRole("table", { name: "Cost by Project" }).waitFor();
      await page.getByRole("radio", { name: "Agent" }).click();
    },
    ready: table("Cost by Agent"),
  },
  {
    name: "cost-nothing-spent",
    path: COST,
    setup: () => fakeCostApi({ rows: { project: [], agent: [] } }),
    ready: async (page) => {
      await page.getByRole("heading", { name: "Nothing was spent in this period" }).waitFor();
    },
  },
  {
    name: "cost-bad-dates",
    path: COST,
    setup: () => fakeCostApi(),
    act: async (page) => {
      await page.getByRole("table", { name: "Cost by Project" }).waitFor();
      await page.getByLabel("From (UTC)").fill("2026-11-05");
      await page.getByLabel("To (UTC)").fill("2026-11-01");
    },
    ready: async (page) => {
      await page.getByRole("alert").filter({ hasText: "Check the dates" }).waitFor();
    },
  },
  {
    name: "cost-loading",
    path: COST,
    // The cost never answers, so the placeholder stays.
    setup: () => server.use(mswHttp.get("*/api/organisations/:organisationId/cost", () => new Promise(() => {}))),
    ready: async (page) => {
      await page.getByRole("status", { name: "Loading the cost" }).waitFor();
    },
  },
  {
    name: "cost-editor",
    path: COST,
    session: editorSession,
    setup: () => fakeCostApi(),
    ready: async (page) => {
      await page.getByRole("heading", { name: "Only Owners see the Organisation's spend" }).waitFor();
    },
  },
  {
    name: "audit",
    path: `/organisations/${ORG}/settings/audit`,
    setup: () => fakeAuditApi(),
    ready: async (page) => {
      await page.getByRole("cell", { name: "member.locked_out" }).waitFor();
    },
  },
];

function signedIn(target: Target) {
  server.resetHandlers();
  const session = target.session ?? adaSession;
  fakeAuthApi({ signedInAs: session });
  fakeAccountApi({ signedInAs: session });
  fakeProjectsApi();
  target.setup?.();
}

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
        signedIn(target);
        const page = await context.newPage();
        await page.goto(target.path);
        await page.getByRole("heading", { level: 1 }).waitFor();
        await page.evaluate(() => document.fonts.ready);
        if (target.act) await target.act(page);
        await target.ready(page);
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
          `${name.padEnd(40)} at ${seen.path}; body ${seen.canvas}; horizontal scroll: ${seen.overflow ? "YES" : "no"}; axe violations: ${String(results.violations.length)}` +
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
