// Sandbox-only: light and dark screenshots, and axe in both Appearances, of the Agent page and its
// views (Playground with a folded and an open Trace, the configuration sections, Versions,
// Embed & limits, an archived Agent), the Agent and view switchers and the ⋯ menus open, and every
// dialog they lead to (Publish, Discard Draft, Archive, Delete permanently, Revert, Start Draft
// from). There is no Docker daemon here, so instead of the compose stack it serves the built Studio
// (apps/studio/dist) and answers the API with the unit tests' own MSW fakes (apps/studio/src/test:
// Ada, the HR handbook Project, HR helper live on v2 with a changed Draft, Pay helper not live, Old
// helper archived), run through MSW's getResponse instead of a mocked fetch. See shots.config.mjs
// for the command.
import { createRequire } from "node:module";
import { readFile, writeFile } from "node:fs/promises";
import { createServer, type IncomingMessage } from "node:http";
import { extname, join } from "node:path";

import type { Page } from "@playwright/test";

import { fakeAccountApi } from "../../../../frontend/apps/studio/src/test/account";
import { agentVersion, defaultDraft, fakeAgentsApi, hrHelper, oldHelper } from "../../../../frontend/apps/studio/src/test/agents";
import { adaSession, fakeAuthApi } from "../../../../frontend/apps/studio/src/test/auth";
import { fakeBrandingApi } from "../../../../frontend/apps/studio/src/test/branding";
import { fakeConversationsApi } from "../../../../frontend/apps/studio/src/test/conversations";
import { fakeCredentialsApi } from "../../../../frontend/apps/studio/src/test/credentials";
import { fakeProjectsApi, hrProject, instructionsVersion } from "../../../../frontend/apps/studio/src/test/projects";
import { server } from "../../../../frontend/apps/studio/src/test/server";
import { fakeThemeApi } from "../../../../frontend/apps/studio/src/test/theme";

// Resolve Playwright and axe from frontend/ (the working directory).
const require = createRequire(join(process.cwd(), "package.json"));
const { default: AxeBuilder } = require("@axe-core/playwright");
const { chromium } = require("@playwright/test");
const { getResponse } = require("msw");

const DIST = join(process.cwd(), "apps/studio/dist");
const OUT = process.env.SHOTS_DIR ?? "shots";
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const ORG = adaSession.active_organisation_id;
const P = `/organisations/${ORG}/projects/${hrProject.id}`;

const prompted = (system_prompt: string) => ({ ...defaultDraft, behaviour: { ...defaultDraft.behaviour, system_prompt } });
const v1 = agentVersion(1, { config: prompted("Answer from the HR handbook."), note: "First release" });
const v2 = agentVersion(2, {
  config: prompted("Answer from the HR handbook.\nBe brief."),
  note: "Shorter answers",
  instructions_version: { id: instructionsVersion(2).id, number: 2 },
});
/** Live on v2, with a Draft changed since. */
const live = {
  ...hrHelper,
  draft: prompted("Answer from the HR handbook.\nBe very brief."),
  live_version: { id: v2.id, number: 2 },
  has_unpublished_changes: true,
};
const payHelper = { ...hrHelper, id: "a9e00000-0000-4000-8000-000000000009", name: "Pay helper" };
const ada = { id: adaSession.member.id, name: adaSession.member.name };
const AGENT = `${P}/agents/${live.id}`;
const OLD = `${P}/agents/${oldHelper.id}`;

function signedIn() {
  server.resetHandlers();
  fakeAuthApi({ signedInAs: adaSession });
  fakeAccountApi({ signedInAs: adaSession });
  fakeProjectsApi({
    instructions: { [hrProject.id]: "Answer from the HR handbook only." },
    versions: {
      [hrProject.id]: { current_version_id: instructionsVersion(2).id, versions: [instructionsVersion(2), instructionsVersion(1)] },
    },
  });
  fakeAgentsApi({
    agents: [live, payHelper, { ...oldHelper, live_version: { id: v1.id, number: 1 } }],
    versions: { [live.id]: [v2, v1], [oldHelper.id]: [v1] },
    currentInstructions: { id: instructionsVersion(2).id, number: 2 },
    allowedOrigins: [],
    tokensUsed: 850_000,
    liveHistory: {
      [live.id]: [
        {
          from_version: { id: v1.id, number: 1 },
          to_version: { id: v2.id, number: 2 },
          action: "publish",
          actor: ada,
          occurred_at: "2026-11-06T10:05:00Z",
          bulk_operation_id: null,
        },
        { from_version: null, to_version: { id: v1.id, number: 1 }, action: "publish", actor: ada, occurred_at: "2026-11-05T09:00:00Z", bulk_operation_id: null },
      ],
    },
    diff: (from, to) => ({
      from: from === "draft" ? { kind: "draft", version: null } : { kind: "version", version: { id: v2.id, number: 2 } },
      to: to === "draft" ? { kind: "draft", version: null } : { kind: "version", version: { id: v2.id, number: 2 } },
      changes: [
        {
          path: "behaviour.system_prompt",
          before: "Answer from the HR handbook.\nBe brief.",
          after: "Answer from the HR handbook.\nBe very brief.",
          added: null,
          removed: null,
          lines: [
            { op: "equal", text: "Answer from the HR handbook." },
            { op: "delete", text: "Be brief." },
            { op: "insert", text: "Be very brief." },
          ],
        },
        { path: "behaviour.temperature", before: 0.7, after: 0.2, added: null, removed: null, lines: null },
      ],
      instructions: null,
    }),
  });
  fakeBrandingApi();
  fakeThemeApi();
  fakeCredentialsApi();
  fakeConversationsApi();
}

const menu = (button: RegExp, item?: string, dialog: "dialog" | "alertdialog" = "alertdialog") => async (page: Page) => {
  await page.getByRole("button", { name: button }).click();
  await page.getByRole("menu").waitFor();
  if (item === undefined) return;
  await page.getByRole("menu").getByRole("menuitem", { name: item }).click();
  await page.getByRole(dialog).waitFor();
};

/** Asks a question in the Playground and opens its answer's Trace. */
async function askAndTrace(page: Page) {
  await page.getByLabel("Question", { exact: true }).fill("How much annual leave do I get?");
  await page.getByRole("button", { name: "Send" }).click();
  const answer = page.getByRole("list", { name: "Playground messages" }).getByRole("listitem", { name: "HR helper" });
  await answer.getByText("Trace", { exact: true }).waitFor();
  await answer.getByText("Trace", { exact: true }).click();
  await answer.getByRole("table", { name: "Retrieved Chunks" }).waitFor();
}

async function openAllSections(page: Page) {
  for (const section of ["Retrieval", "Experience", "Guardrails"]) {
    await page.getByRole("complementary", { name: "Configuration" }).locator("summary", { hasText: section }).click();
  }
}

// `act` opens what the screenshot shows once the page has loaded.
const PAGES: { name: string; path: string; act?: (page: Page) => Promise<void> }[] = [
  { name: "agent-playground", path: AGENT },
  { name: "agent-playground-trace", path: AGENT, act: askAndTrace },
  { name: "agent-configuration-open", path: AGENT, act: openAllSections },
  { name: "agent-versions", path: `${AGENT}/versions` },
  { name: "agent-embed", path: `${AGENT}/embed` },
  { name: "agent-not-live", path: `${P}/agents/${payHelper.id}` },
  { name: "agent-archived", path: OLD },
  { name: "agent-archived-embed", path: `${OLD}/embed` },
  { name: "menu-agents", path: AGENT, act: menu(/, Agents$/) },
  { name: "menu-agent-views", path: AGENT, act: menu(/, Agent views$/) },
  { name: "menu-agent-actions", path: AGENT, act: menu(/^More Agent actions$/) },
  {
    name: "dialog-publish",
    path: AGENT,
    act: async (page) => {
      await page.getByRole("banner").getByRole("button", { name: "Publish" }).click();
      await page.getByRole("region", { name: "Changes to publish" }).getByRole("table").waitFor();
    },
  },
  { name: "confirm-discard", path: AGENT, act: menu(/^More Agent actions$/, "Discard Draft") },
  { name: "confirm-archive", path: AGENT, act: menu(/^More Agent actions$/, "Archive") },
  { name: "confirm-delete", path: OLD, act: menu(/^More Agent actions$/, "Delete permanently") },
  { name: "confirm-revert", path: `${AGENT}/versions`, act: menu(/^Actions for the Live Version$/, "Revert to v1", "dialog") },
  { name: "confirm-start-draft", path: `${AGENT}/versions`, act: menu(/^Actions for v1$/, "Start Draft from v1", "dialog") },
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
      signedIn();
      const page = await context.newPage();
      await page.goto(target.path);
      await page.waitForLoadState("networkidle");
      // The Agent page has loaded, its crumbs included.
      await page.getByRole("button", { name: /, Agent views$/ }).waitFor();
      await page.evaluate(() => document.fonts.ready);
      if (target.act) await target.act(page);
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(250);
      const seen = await page.evaluate(() => ({
        path: location.pathname,
        heading: document.querySelector("main h2")?.textContent ?? "",
        canvas: getComputedStyle(document.body).backgroundColor,
      }));
      await page.screenshot({ path: `${OUT}/${target.name}-${appearance.label}.png`, fullPage: true });
      const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
      failures += results.violations.length;
      report.push(
        `${appearance.label.padEnd(11)} ${target.name.padEnd(26)} at ${seen.path} "${seen.heading}"; body ${seen.canvas}; axe violations: ${String(results.violations.length)}` +
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
