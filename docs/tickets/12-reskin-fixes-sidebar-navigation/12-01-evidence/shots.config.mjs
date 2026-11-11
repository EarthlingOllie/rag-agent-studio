// Vitest config for shots.test.ts only (not part of `pnpm test`). Run from frontend/:
//   SHOTS_DIR=../docs/tickets/12-reskin-fixes-sidebar-navigation/12-01-evidence/screenshots pnpm exec vitest run --config ../docs/tickets/12-reskin-fixes-sidebar-navigation/12-01-evidence/shots.config.mjs
import { fileURLToPath } from "node:url";
export default {
  root: process.cwd(),
  test: {
    environment: "node",
    globals: true,
    include: [fileURLToPath(new URL("./shots.test.ts", import.meta.url))],
    testTimeout: 1_800_000,
    coverage: { enabled: false },
  },
  server: { fs: { strict: false } },
};
