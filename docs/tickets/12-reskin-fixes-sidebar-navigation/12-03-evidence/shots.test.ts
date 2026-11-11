// Sandbox-only: light and dark screenshots, and axe in both Appearances, of the Organisation's
// Projects page (12-03) at 1440 and 390 wide: the active Projects, the archived ones (an Owner's
// and an Editor's view, and the toast after a restore), no Projects, no archived Projects, loading,
// a failed load, and the success notice after a Project is deleted.
// There is no Docker daemon here, so instead of the compose stack it serves the built Studio
// (apps/studio/dist) and answers the API with the unit tests' own MSW fakes (apps/studio/src/test),
// run through MSW's getResponse instead of a mocked fetch. See shots.config.mjs for the command.
import { createRequire } from "node:module";
import { readFile, writeFile } from "node:fs/promises";
import { createServer, type IncomingMessage } from "node:http";
import { extname, join } from "node:path";

import { fakeAccountApi } from "../../../../frontend/apps/studio/src/test/account";
import { adaSession, fakeAuthApi, type Session } from "../../../../frontend/apps/studio/src/test/auth";
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
const editorSession: Session = {
  ...adaSession,
  organisations: adaSession.organisations.map((organisation) => ({ ...organisation, role: "editor" as const })),
};

type Page = import("@playwright/test").Page;
interface Target {
  name: string;
  path: string;
  session?: Session;
  /** Replaces the default Projects fake. */
  setup?: () => void;
  /** What shows once the page is ready (after `act`). */
  ready: (page: Page) => Promise<void>;
  act?: (page: Page) => Promise<void>;
}

const PROJECTS = `/organisations/${ORG}/projects`;
// A long description shows the one-line cut.
const longProject = {
  ...salesProject,
  description:
    "Decks, pricing sheets, competitor notes and every customer-facing answer the sales team has agreed on for this year's launches.",
};
const table = (name: string) => async (page: Page) => {
  await page.getByRole("table", { name }).waitFor();
};
const heading = (name: string) => async (page: Page) => {
  await page.getByRole("heading", { name }).waitFor();
};
const archived = async (page: Page) => {
  await page.getByRole("radiogroup", { name: "Projects shown" }).getByRole("radio", { name: "Archived" }).click();
};
const PAGES: Target[] = [
  {
    name: "projects-active",
    path: PROJECTS,
    setup: () => fakeProjectsApi({ projects: [hrProject, longProject, oldProject] }),
    ready: table("Projects"),
  },
  { name: "projects-archived", path: PROJECTS, act: archived, ready: table("Archived Projects") },
  {
    name: "projects-archived-editor",
    path: PROJECTS,
    session: editorSession,
    act: archived,
    ready: table("Archived Projects"),
  },
  {
    name: "projects-restored",
    path: PROJECTS,
    act: async (page) => {
      await archived(page);
      await page.getByRole("button", { name: "Restore Old launch" }).click();
    },
    ready: async (page) => {
      await page.getByText("Old launch was restored.").waitFor();
      await heading("No archived Projects")(page);
    },
  },
  {
    name: "projects-none",
    path: PROJECTS,
    setup: () => fakeProjectsApi({ projects: [] }),
    ready: heading("No Projects yet"),
  },
  {
    name: "projects-loading",
    path: PROJECTS,
    // The Projects never answer, so the placeholder stays.
    setup: () => server.use(mswHttp.get("*/api/organisations/:organisationId/projects", () => new Promise(() => {}))),
    ready: async (page) => {
      await page.getByRole("status", { name: "Loading Projects" }).waitFor();
    },
  },
  {
    name: "projects-error",
    path: PROJECTS,
    setup: () =>
      server.use(
        mswHttp.get("*/api/organisations/:organisationId/projects", () => HttpResponse.json({ detail: "Boom" }, { status: 500 })),
      ),
    ready: heading("The Projects could not be loaded"),
  },
  {
    name: "projects-deleted",
    path: `${PROJECTS}?deleted=${encodeURIComponent("Retired handbook")}`,
    ready: async (page) => {
      await page.getByText("Retired handbook is being deleted permanently.").waitFor();
    },
  },
];

function signedIn(target: Target) {
  server.resetHandlers();
  const session = target.session ?? adaSession;
  fakeAuthApi({ signedInAs: session });
  fakeAccountApi({ signedInAs: session });
  if (target.setup) target.setup();
  else fakeProjectsApi();
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
