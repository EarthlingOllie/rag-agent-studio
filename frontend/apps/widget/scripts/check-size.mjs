// CI's size budget for the Embed Snippet's loader (`dist/embed.js`): it runs on every host page,
// so it must stay tiny. Run after `pnpm --filter @studio/widget build`.
import { readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";

const BUDGET_BYTES = 2048;
const BUDGET_GZIP_BYTES = 1024;

// A path argument checks another file (used to show the budget failing).
const path = process.argv[2] ?? new URL("../dist/embed.js", import.meta.url);
const source = readFileSync(path);
const gzipped = gzipSync(source).length;
console.log(`embed.js: ${String(source.length)} bytes, ${String(gzipped)} gzipped (budget ${String(BUDGET_BYTES)} and ${String(BUDGET_GZIP_BYTES)})`);
if (source.length > BUDGET_BYTES || gzipped > BUDGET_GZIP_BYTES) {
  console.error("embed.js is over its size budget.");
  process.exit(1);
}
