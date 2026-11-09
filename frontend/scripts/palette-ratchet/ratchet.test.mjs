// The palette ratchet (`pnpm palette-ratchet`): Tailwind palette classes in the Studio may only go
// down. Run with Node's coverage thresholds by the `palette-ratchet` package script.
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";

import { countPaletteUses, main } from "./ratchet.mjs";

/** A fixture frontend: files under `apps/studio/src` with known palette uses, plus a baseline. */
function fixture(files, baseline) {
  const root = mkdtempSync(join(tmpdir(), "palette-ratchet-"));
  for (const [path, text] of Object.entries(files)) {
    mkdirSync(dirname(join(root, path)), { recursive: true });
    writeFileSync(join(root, path), text);
  }
  if (baseline !== undefined) writeFileSync(join(root, "palette-baseline.json"), `${JSON.stringify({ count: baseline })}\n`);
  return root;
}

// Five uses: slate-700, dark:, bg-white, text-red-800 (as red-800), text-white.
const FIVE = {
  "apps/studio/src/App.tsx": '<div className="bg-slate-700 dark:bg-black text-white">\n',
  "apps/studio/src/projects/Page.tsx": '<p className="bg-white text-red-800 border-line">ok</p>\n',
  "apps/studio/src/design/tokens.css": ":root { --ds-ink: #15201f; }\n",
  // Outside apps/studio/src: never counted.
  "packages/ui/src/primitives.tsx": '<div className="bg-slate-900 text-white" />\n',
  "apps/widget/src/Widget.tsx": '<div className="bg-gray-100" />\n',
};

function run(root, ...args) {
  const out = [];
  const err = [];
  const code = main(args, { cwd: root, log: (line) => out.push(line), error: (line) => err.push(line) });
  return { code, out: out.join("\n"), err: err.join("\n") };
}

test("counts palette classes, dark: variants and white text or backgrounds under apps/studio/src only", () => {
  const root = fixture(FIVE);
  assert.deepEqual(countPaletteUses(join(root, "apps/studio/src")), {
    total: 5,
    files: [
      { path: "App.tsx", count: 3 },
      { path: "projects/Page.tsx", count: 2 },
    ],
  });
});

test("token utilities are not palette classes", () => {
  const root = fixture({
    "apps/studio/src/Page.tsx":
      '<div className="bg-surface text-ink border-line text-on-accent bg-danger-soft text-muted ordered-list w-120 grid-cols-12" />\n',
  });
  assert.equal(countPaletteUses(join(root, "apps/studio/src")).total, 0);
});

test("a `dark` key or a colour named in prose is not a class; the dark: variant is", () => {
  const root = fixture({
    "apps/studio/src/theme.ts": 'const primary = { light: "#4f46e5", dark: "#818cf8" };\nconst { light, dark } = row;\n',
    "apps/studio/src/Page.tsx": '<div className="dark:bg-black dark:[color:red] dark:!p-0" />\n',
  });
  assert.deepEqual(countPaletteUses(join(root, "apps/studio/src")), { total: 3, files: [{ path: "Page.tsx", count: 3 }] });
});

test("the same count as the baseline passes", () => {
  const { code, out, err } = run(fixture(FIVE, 5));
  assert.equal(code, 0);
  assert.match(out, /5 palette-class uses under apps\/studio\/src \(baseline 5\)/);
  assert.equal(err, "");
});

test("a rise fails and names the files that have them", () => {
  const root = fixture({ ...FIVE, "apps/studio/src/New.tsx": '<button className="bg-blue-600">New</button>\n' }, 5);
  const { code, err } = run(root);
  assert.equal(code, 1);
  assert.match(err, /6 palette-class uses under apps\/studio\/src, up from the baseline of 5/);
  assert.match(err, /New\.tsx: 1/);
  assert.match(err, /Use the design system's token utilities and recipes/);
  // The baseline is never raised by the check.
  assert.deepEqual(JSON.parse(readFileSync(join(root, "palette-baseline.json"), "utf8")), { count: 5 });
});

test("a fall passes and prints the new baseline to commit", () => {
  const root = fixture(FIVE, 9);
  const { code, out } = run(root);
  assert.equal(code, 0);
  assert.match(out, /5 palette-class uses under apps\/studio\/src, down from the baseline of 9/);
  assert.match(out, /palette-baseline\.json[\s\S]*\{ "count": 5 \}/);
  assert.deepEqual(JSON.parse(readFileSync(join(root, "palette-baseline.json"), "utf8")), { count: 9 });
});

test("--write lowers the baseline to the new count, but never raises it", () => {
  const lower = fixture(FIVE, 9);
  assert.equal(run(lower, "--write").code, 0);
  assert.equal(readFileSync(join(lower, "palette-baseline.json"), "utf8"), '{\n  "count": 5\n}\n');

  const higher = fixture(FIVE, 2);
  assert.equal(run(higher, "--write").code, 1);
  assert.deepEqual(JSON.parse(readFileSync(join(higher, "palette-baseline.json"), "utf8")), { count: 2 });
});

test("with no baseline file none are allowed", () => {
  const dirty = run(fixture(FIVE));
  assert.equal(dirty.code, 1);
  assert.match(dirty.err, /5 palette-class uses under apps\/studio\/src, up from the baseline of 0/);

  const clean = run(fixture({ "apps/studio/src/App.tsx": '<div className="bg-canvas" />\n' }));
  assert.equal(clean.code, 0);
  assert.match(clean.out, /0 palette-class uses under apps\/studio\/src \(none allowed\)/);
});

test("an unknown argument is a usage error", () => {
  const { code, err } = run(fixture(FIVE, 5), "--frobnicate");
  assert.equal(code, 2);
  assert.match(err, /usage: palette-ratchet \[--write\]/);
});
