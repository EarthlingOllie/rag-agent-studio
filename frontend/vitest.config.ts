import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    include: ["apps/*/src/**/*.test.{ts,tsx}", "packages/*/src/**/*.test.{ts,tsx}"],
    setupFiles: ["apps/studio/src/test/setup.ts"],
    restoreMocks: true,
    coverage: {
      provider: "v8",
      include: ["apps/*/src/**/*.{ts,tsx}", "packages/*/src/**/*.{ts,tsx}"],
      // ADR-0008: the generated API client is the only frontend exclusion besides test code.
      exclude: ["**/*.gen.ts", "**/*.test.{ts,tsx}", "**/src/test/**", "**/*.d.ts"],
      reporter: ["text", "lcov", "json-summary"],
      thresholds: { lines: 100, branches: 100, functions: 100, statements: 100 },
    },
  },
});
