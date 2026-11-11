// Sandbox-only: light and dark screenshots, and axe in both Appearances, of every page 11-12
// changed: the signed-out pages (sign in, sign up, MFA, reset, invites), the status page, the
// shell's loading, error and empty states, Profile and Security (each MFA step), and the account
// and section menus that now reach them. There is no Docker daemon here, so instead of the compose
// stack it serves the built Studio (apps/studio/dist) and answers the API with the unit tests' own
// MSW fakes, run through MSW's getResponse instead of a mocked fetch. See shots.config.mjs.
import { createRequire } from "node:module";
import { readFile, writeFile } from "node:fs/promises";
import { createServer, type IncomingMessage } from "node:http";
import { extname, join } from "node:path";

import { fakeAccountApi } from "../../../../frontend/apps/studio/src/test/account";
import { adaSession, fakeAuthApi } from "../../../../frontend/apps/studio/src/test/auth";
import { fakeAcceptApi, previewFor } from "../../../../frontend/apps/studio/src/test/invites";
import { fakeMfaApi, GOOD_CODE, SECRET } from "../../../../frontend/apps/studio/src/test/mfa";
import { server } from "../../../../frontend/apps/studio/src/test/server";

// Resolve Playwright, axe and MSW from frontend/ (the working directory).
const require = createRequire(join(process.cwd(), "package.json"));
const { default: AxeBuilder } = require("@axe-core/playwright");
const { chromium } = require("@playwright/test");
const { delay, getResponse, http, HttpResponse } = require("msw");

const DIST = join(process.cwd(), "apps/studio/dist");
const OUT = process.env.SHOTS_DIR ?? "shots";
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const ORG = adaSession.active_organisation_id;
const TOKEN = "invite-token-1";
const ACCOUNT_EMAIL = "ada@example.test";

type Page = {
  getByRole: (role: string, options?: { name?: string | RegExp }) => {
    click: () => Promise<void>;
    fill: (value: string) => Promise<void>;
    waitFor: () => Promise<void>;
    first: () => { waitFor: () => Promise<void> };
  };
  getByLabel: (label: string) => { fill: (value: string) => Promise<void> };
  locator: (selector: string) => { first: () => { waitFor: () => Promise<void> } };
};

type Shot = {
  name: string;
  path: string;
  setup?: () => void;
  /** What to do once the page is up, before the screenshot. */
  act?: (page: Page) => Promise<void>;
  /** The page never settles (a request that never answers): don't wait for the network. */
  pending?: true;
};

/**
 * A stand-in for the API's QR code (the unit tests' fake is an empty SVG): a 29-module grid with
 * the three finder squares, drawn like segno's (black on white, a 4-module border). Not scannable.
 */
function standInQrCode(): string {
  const size = 29;
  const finder = (x: number, y: number) =>
    [[0, 0], [size - 7, 0], [0, size - 7]].some(([fx, fy]) => {
      const dx = x - (fx as number);
      const dy = y - (fy as number);
      if (dx < 0 || dy < 0 || dx > 6 || dy > 6) return false;
      return dx === 0 || dy === 0 || dx === 6 || dy === 6 || (dx >= 2 && dx <= 4 && dy >= 2 && dy <= 4);
    });
  const inFinderZone = (x: number, y: number) => (x < 8 && y < 8) || (x >= size - 8 && y < 8) || (x < 8 && y >= size - 8);
  let seed = 7;
  const cells: string[] = [];
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      seed = (seed * 1103515245 + 12345) % 2147483648;
      const dark = inFinderZone(x, y) ? finder(x, y) : seed % 7 < 3;
      if (dark) cells.push(`M${String(x + 4)} ${String(y + 4)}h1v1h-1z`);
    }
  }
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${String(size + 8)} ${String(size + 8)}"><rect width="100%" height="100%" fill="#fff"/><path d="${cells.join("")}"/></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function signedIn() {
  fakeAuthApi({ signedInAs: adaSession });
  fakeAccountApi({ signedInAs: adaSession });
  fakeMfaApi();
  server.use(
    http.post("*/api/auth/mfa/enrolment", () =>
      HttpResponse.json({ secret: SECRET, otpauth_uri: `otpauth://totp/x?secret=${SECRET}`, qr_code: standInQrCode() }, { status: 201 }),
    ),
  );
}

async function submit(page: Page, button: string) {
  await page.getByRole("button", { name: button }).click();
}

const SHOTS: Shot[] = [
  // Signed out.
  { name: "sign-in", path: "/sign-in", setup: () => fakeAuthApi() },
  {
    name: "sign-in-error",
    path: "/sign-in",
    setup: () => server.use(http.post("*/api/auth/sign-in", () => HttpResponse.json({ detail: "no" }, { status: 401 }))),
    act: async (page) => {
      await page.getByLabel("Email").fill(ACCOUNT_EMAIL);
      await page.getByLabel("Password").fill("not the password");
      await submit(page, "Sign in");
      await page.getByRole("alert").waitFor();
    },
  },
  { name: "sign-up", path: "/sign-up" },
  { name: "mfa-challenge", path: "/sign-in/mfa" },
  { name: "forgot-password", path: "/forgot-password" },
  {
    name: "forgot-password-sent",
    path: "/forgot-password",
    setup: () => server.use(http.post("*/api/auth/password-reset", () => new HttpResponse(null, { status: 202 }))),
    act: async (page) => {
      await page.getByLabel("Email").fill(ACCOUNT_EMAIL);
      await submit(page, "Send reset link");
      await page.getByRole("status").waitFor();
    },
  },
  { name: "reset-password", path: "/reset-password?token=reset-token" },
  { name: "reset-password-incomplete", path: "/reset-password" },
  {
    name: "accept-invite-create",
    path: `/accept-invite?token=${TOKEN}`,
    setup: () => fakeAcceptApi({ token: TOKEN, preview: previewFor("grace@example.test") }),
  },
  {
    name: "accept-invite-sign-in",
    path: `/accept-invite?token=${TOKEN}`,
    setup: () => fakeAcceptApi({ token: TOKEN, preview: previewFor("grace@example.test", { account_exists: true }) }),
  },
  {
    name: "accept-invite-wrong-account",
    path: `/accept-invite?token=${TOKEN}`,
    setup: () => {
      fakeAuthApi({ signedInAs: adaSession });
      fakeAcceptApi({ token: TOKEN, preview: previewFor("grace@example.test") });
    },
  },
  { name: "accept-invite-invalid", path: `/accept-invite?token=${TOKEN}`, setup: () => fakeAcceptApi({ token: TOKEN, preview: { status: 404 } }) },
  // The status page.
  { name: "status", path: "/status" },
  {
    name: "status-degraded",
    path: "/status",
    setup: () =>
      server.use(
        http.get("*/api/health", () => HttpResponse.json({ status: "error", checks: { database: "error", redis: "ok" } }, { status: 503 })),
        http.get("*/api/health/worker", () => HttpResponse.json({ status: "error", reply: null }, { status: 503 })),
      ),
  },
  // The shell's own states.
  { name: "shell-loading", path: "/", pending: true, setup: () => server.use(http.get("*/api/auth/me", () => delay("infinite"))) },
  { name: "shell-error", path: "/", setup: () => server.use(http.get("*/api/auth/me", () => new HttpResponse(null, { status: 500 }))) },
  {
    name: "no-organisation",
    path: "/",
    setup: () => fakeAuthApi({ signedInAs: { ...adaSession, organisations: [], active_organisation_id: null } }),
  },
  { name: "organisation-not-found", path: "/organisations/00000000-0000-4000-8000-000000000000/projects", setup: signedIn },
  // Profile and Security.
  { name: "profile", path: `/organisations/${ORG}/profile`, setup: signedIn },
  { name: "security", path: `/organisations/${ORG}/security`, setup: signedIn },
  {
    name: "security-enrol",
    path: `/organisations/${ORG}/security`,
    setup: signedIn,
    act: async (page) => {
      await submit(page, "Set up two-factor authentication");
      await page.getByRole("img", { name: "QR code for your authenticator app" }).waitFor();
    },
  },
  {
    name: "security-recovery-codes",
    path: `/organisations/${ORG}/security`,
    setup: signedIn,
    act: async (page) => {
      await submit(page, "Set up two-factor authentication");
      await page.getByLabel("Code from your app").fill(GOOD_CODE);
      await submit(page, "Turn on");
      await page.getByRole("list", { name: "Recovery codes" }).waitFor();
    },
  },
  {
    name: "security-on",
    path: `/organisations/${ORG}/security`,
    setup: () => {
      signedIn();
      fakeMfaApi({ enabled: true, remaining: 7 });
    },
  },
  {
    name: "security-loading",
    path: `/organisations/${ORG}/security`,
    pending: true,
    setup: () => {
      signedIn();
      server.use(http.get("*/api/auth/mfa", () => delay("infinite")));
    },
  },
  // The menus that reach Profile and Security.
  {
    name: "menu-account",
    path: `/organisations/${ORG}/projects`,
    setup: signedIn,
    act: async (page) => {
      await page.getByRole("button", { name: /^Ada Lovelace, Account$/ }).click();
      await page.getByRole("menu").waitFor();
    },
  },
  {
    name: "menu-sections-on-profile",
    path: `/organisations/${ORG}/profile`,
    setup: signedIn,
    act: async (page) => {
      await page.getByRole("button", { name: /, Organisation sections$/ }).click();
      await page.getByRole("menu").waitFor();
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

test("screenshots and axe in both Appearances", async () => {
  const httpServer = createServer((request, response) => {
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
  await new Promise<void>((resolve) => httpServer.listen(0, "127.0.0.1", resolve));
  const address = httpServer.address();
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
    for (const shot of SHOTS) {
      server.resetHandlers();
      shot.setup?.();
      const page = await context.newPage();
      await page.goto(shot.path);
      if (shot.pending) {
        await page.locator("[aria-busy=true]").first().waitFor();
      } else {
        await page.waitForLoadState("networkidle");
        await page.locator("h1, h2, [role=alert]").first().waitFor();
      }
      await page.evaluate(() => document.fonts.ready);
      if (shot.act) await shot.act(page);
      await page.waitForTimeout(250);
      const seen = await page.evaluate(() => ({
        path: location.pathname,
        heading: document.querySelector("h1, h2")?.textContent ?? "",
        topBar: document.querySelector("header") !== null,
        canvas: getComputedStyle(document.body).backgroundColor,
      }));
      await page.screenshot({ path: `${OUT}/${shot.name}-${appearance.label}.png`, fullPage: true });
      const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
      failures += results.violations.length;
      report.push(
        `${appearance.label.padEnd(11)} ${shot.name.padEnd(28)} at ${seen.path} "${seen.heading}"; top bar ${seen.topBar ? "yes" : "no"}; body ${seen.canvas}; axe violations: ${String(results.violations.length)}` +
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
  httpServer.close();
  // Vitest hides a passing test's console, so the report goes next to the screenshots' folder.
  await writeFile(join(OUT, "..", "shots-axe.log"), `${report.join("\n")}\ntotal axe violations: ${String(failures)}\n`);
  if (failures > 0) throw new Error(`${String(failures)} axe violations`);
});
