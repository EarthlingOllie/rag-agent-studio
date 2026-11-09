// Vitest config for shots.test.ts only (not part of `pnpm test`). Run from frontend/:
//   SHOTS_DIR=../docs/tickets/11-studio-design/11-07-evidence/screenshots pnpm exec vitest run --config ../docs/tickets/11-studio-design/11-07-evidence/shots.config.mjs
import { fileURLToPath } from "node:url";
export default {
  root: process.cwd(),
  test: {
    environment: "node",
    globals: true,
    include: [fileURLToPath(new URL("./shots.test.ts", import.meta.url))],
    testTimeout: 900_000,
    coverage: { enabled: false },
  },
  server: { fs: { strict: false } },
};
