import { defineConfig } from "@playwright/test";

import { STUDIO_URL } from "./e2e/fixtures/env";

const chromiumExecutable = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;

/**
 * Two projects:
 * - `harness` checks the shared fixtures themselves against an in-process fake Studio, so it needs no stack;
 * - `studio` runs against the real `docker compose` stack at E2E_BASE_URL (default http://localhost:5173).
 */
export default defineConfig({
  testDir: "./e2e",
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: STUDIO_URL,
    trace: "retain-on-failure",
    ...(chromiumExecutable ? { launchOptions: { executablePath: chromiumExecutable } } : {}),
  },
  projects: [
    { name: "harness", testMatch: "harness/**/*.spec.ts" },
    { name: "studio", testMatch: "tests/**/*.spec.ts" },
  ],
});
