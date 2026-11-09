// The palette ratchet (spec 11, docs/design/README.md): counts Tailwind palette-class uses in the
// Studio and fails when the count rises above the committed baseline, so the old look can only
// shrink. Each reskin PR lowers the baseline; when it reaches zero the baseline file is deleted and
// none are allowed.
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";

/** The `studio-reskin` skill's leftover check: palette colours, the `dark:` variant, white text or fills. */
export const PALETTE_CLASS = /(slate|gray|zinc|red|green|amber|blue|white|black)-[0-9]{2,3}|\bdark:|bg-white|text-white/g;

/** Where the Studio's source lives, relative to `frontend/`. */
export const STUDIO_SRC = "apps/studio/src";
/** The committed count, relative to `frontend/`. */
export const BASELINE_FILE = "palette-baseline.json";

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory() ? walk(join(dir, entry.name)) : [join(dir, entry.name)],
  );
}

/** Every palette-class use under `dir`: the total and the files that have any, by path. */
export function countPaletteUses(dir) {
  const files = walk(dir)
    .map((file) => ({ path: relative(dir, file), count: (readFileSync(file, "utf8").match(PALETTE_CLASS) ?? []).length }))
    .filter((file) => file.count > 0)
    .sort((a, b) => a.path.localeCompare(b.path));
  return { total: files.reduce((sum, file) => sum + file.count, 0), files };
}

const serialise = (count) => `${JSON.stringify({ count }, null, 2)}\n`;

/**
 * Compares the count with the baseline. Exit codes: 0 at or under it, 1 over it, 2 for a usage
 * error. `--write` lowers the baseline file to the current count (it never raises it).
 */
export function main(args, { cwd = process.cwd(), log = console.log, error = console.error } = {}) {
  if (args.some((arg) => arg !== "--write")) {
    error("usage: palette-ratchet [--write]");
    return 2;
  }
  const baselinePath = join(cwd, BASELINE_FILE);
  const hasBaseline = existsSync(baselinePath);
  const baseline = hasBaseline ? JSON.parse(readFileSync(baselinePath, "utf8")).count : 0;
  const { total, files } = countPaletteUses(join(cwd, STUDIO_SRC));
  const uses = `${String(total)} palette-class uses under ${STUDIO_SRC}`;

  if (total > baseline) {
    error(`${uses}, up from the baseline of ${String(baseline)}.`);
    for (const file of files) error(`  ${file.path}: ${String(file.count)}`);
    error("Use the design system's token utilities and recipes (docs/design/README.md) instead of Tailwind palette classes or dark:.");
    return 1;
  }
  if (total < baseline) {
    log(`${uses}, down from the baseline of ${String(baseline)}. Commit the lower baseline:`);
    if (args.includes("--write")) writeFileSync(baselinePath, serialise(total));
    log(`${BASELINE_FILE}: { "count": ${String(total)} }`);
    return 0;
  }
  log(`${uses} (${hasBaseline ? `baseline ${String(baseline)}` : "none allowed"}).`);
  return 0;
}
