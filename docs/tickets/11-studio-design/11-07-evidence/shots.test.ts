// Sandbox-only: light and dark screenshots, and axe in both Appearances, of the Project
// Instructions page and every dialog it opens: the page itself (Draft, Publish, Agents behind,
// the Versions timeline and Compare with Diff), two Versions compared, an archived Project's
// read-only page, the revert ConfirmDialog, the rollout Dialog and its results, and the bulk-revert
// offer. There is no Docker daemon here, so instead of the compose stack it serves the built
// Studio (apps/studio/dist) and answers the API with the unit tests' own MSW fakes
// (apps/studio/src/test), run through MSW's getResponse instead of a mocked fetch. See
// shots.config.mjs for the command.
import { createRequire } from "node:module";
import { readFile, writeFile } from "node:fs/promises";
import { createServer, type IncomingMessage } from "node:http";
import { extname, join } from "node:path";

import { fakeAccountApi } from "../../../../frontend/apps/studio/src/test/account";
import { adaSession, fakeAuthApi } from "../../../../frontend/apps/studio/src/test/auth";
import { fakeBulkApi, rolloutAgent } from "../../../../frontend/apps/studio/src/test/bulk";
import { fakeProjectsApi, hrProject, instructionsVersion, oldProject } from "../../../../frontend/apps/studio/src/test/projects";
import { server } from "../../../../frontend/apps/studio/src/test/server";

// Resolve Playwright and axe from frontend/ (the working directory).
const require = createRequire(join(process.cwd(), "package.json"));
const { default: AxeBuilder } = require("@axe-core/playwright");
const { chromium } = require("@playwright/test");
const { getResponse } = require("msw");

type Page = {
  getByRole: (role: string, options?: { name?: string | RegExp }) => Locator;
  locator: (selector: string) => Locator;
};
type Locator = {
  click: () => Promise<void>;
  waitFor: () => Promise<void>;
  first: () => Locator;
  getByRole: (role: string, options?: { name?: string | RegExp }) => Locator;
  selectOption: (value: string) => Promise<unknown>;
};

const DIST = join(process.cwd(), "apps/studio/dist");
const OUT = process.env.SHOTS_DIR ?? "shots";
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const ORG = adaSession.active_organisation_id;
const INSTRUCTIONS = (projectId: string) => `/organisations/${ORG}/projects/${projectId}/instructions`;

const v1 = instructionsVersion(1, {
  markdown: "# House rules\n\nAnswer from the HR handbook only.\nBe kind.",
  note: "The Instructions as they were when Versions were introduced.",
  author: null,
  created_at: "2026-10-01T09:00:00Z",
});
const v2 = instructionsVersion(2, {
  markdown: "# House rules\n\nAnswer from the HR handbook only.\nBe kind.\nNever quote salaries.",
  note: "Never quote salaries",
  created_at: "2026-11-02T14:30:00Z",
  previous_version_id: v1.id,
});
const DRAFT = "# House rules\n\nAnswer from the HR handbook only, in British English.\nBe kind.\nNever quote salaries.\nPoint people to HR for anything personal.";
const pinV1 = { id: v1.id, number: 1 };
const pinV2 = { id: v2.id, number: 2 };

function signedIn() {
  server.resetHandlers();
  fakeAuthApi({ signedInAs: adaSession });
  fakeAccountApi({ signedInAs: adaSession });
  const history = { current_version_id: v2.id, versions: [v2, v1] };
  fakeProjectsApi({
    instructions: { [hrProject.id]: DRAFT, [oldProject.id]: v2.markdown },
    versions: { [hrProject.id]: history, [oldProject.id]: history },
    revertCandidates: [{ id: rolloutAgent(1, "", null, null).id, name: "HR helper", live_version: { id: "a2e00000-0000-4000-8000-000000000103", number: 3 } }],
  });
  fakeBulkApi({
    rollout: {
      current_version: pinV2,
      behind: 2,
      agents: [
        rolloutAgent(1, "HR helper", 3, pinV2),
        rolloutAgent(2, "Benefits FAQ", 4, pinV1, { behind: true, has_draft_changes: true }),
        rolloutAgent(3, "Payroll", 2, null, { behind: true }),
        rolloutAgent(4, "Onboarding (new)", null, null),
      ],
    },
  });
}

// `act` drives the page to the view; `ready` is what must be on screen before the screenshot.
const VIEWS: { name: string; path: string; act?: (page: Page) => Promise<void>; ready?: (page: Page) => Locator }[] = [
  { name: "instructions", path: INSTRUCTIONS(hrProject.id) },
  {
    name: "compare-v1-v2",
    path: INSTRUCTIONS(hrProject.id),
    act: async (page) => {
      await page.getByRole("combobox", { name: "From" }).selectOption(v1.id);
      await page.getByRole("combobox", { name: "To" }).selectOption(v2.id);
    },
    ready: (page) => page.getByRole("table", { name: "Changes from v1 to v2" }),
  },
  { name: "instructions-archived", path: INSTRUCTIONS(oldProject.id) },
  {
    name: "confirm-revert",
    path: INSTRUCTIONS(hrProject.id),
    act: async (page) => {
      await page.getByRole("button", { name: "Revert to v1" }).click();
    },
    ready: (page) => page.getByRole("alertdialog", { name: "Revert to v1?" }),
  },
  {
    name: "rollout-dialog",
    path: INSTRUCTIONS(hrProject.id),
    act: async (page) => {
      await page.getByRole("button", { name: "Roll out v2…" }).click();
    },
    ready: (page) => page.getByRole("checkbox", { name: "Benefits FAQ" }),
  },
  {
    name: "rollout-results",
    path: INSTRUCTIONS(hrProject.id),
    act: async (page) => {
      await page.getByRole("button", { name: "Roll out v2…" }).click();
      await page.getByRole("dialog").getByRole("button", { name: /^Publish to/ }).click();
    },
    ready: (page) => page.getByRole("list", { name: "Results" }),
  },
  {
    name: "bulk-revert-offer",
    path: INSTRUCTIONS(hrProject.id),
    act: async (page) => {
      await page.getByRole("button", { name: "Revert to v1" }).click();
      await page.getByRole("button", { name: "Yes, revert to v1" }).click();
    },
    ready: (page) => page.getByRole("dialog", { name: "Revert the Agents on Instructions v2?" }),
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
    for (const view of VIEWS) {
      signedIn();
      const page = await context.newPage();
      await page.goto(view.path);
      await page.waitForLoadState("networkidle");
      // The page has loaded: the Versions timeline and the Agents table are there.
      await page.getByRole("list", { name: "Instructions Versions" }).waitFor();
      await page.getByRole("table", { name: "Instructions each Agent runs with" }).waitFor();
      await page.evaluate(() => document.fonts.ready);
      if (view.act) await view.act(page);
      if (view.ready) await view.ready(page).first().waitFor();
      await page.waitForTimeout(300);
      const seen = await page.evaluate(() => ({
        path: location.pathname,
        dialog: document.querySelector("[role=dialog] h2, [role=alertdialog] h2")?.textContent ?? "",
        canvas: getComputedStyle(document.body).backgroundColor,
      }));
      await page.screenshot({ path: `${OUT}/${view.name}-${appearance.label}.png`, fullPage: true });
      const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
      failures += results.violations.length;
      report.push(
        `${appearance.label.padEnd(11)} ${view.name.padEnd(22)} at ${seen.path}${seen.dialog ? ` dialog "${seen.dialog}"` : ""}; body ${seen.canvas}; axe violations: ${String(results.violations.length)}` +
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
