// The one-off colour codemod (ticket 11-03): the `studio-reskin` skill's class-mapping table,
// applied to class lists only. Run with Node's coverage thresholds, like the palette ratchet.
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";

import { main, recolour } from "./codemod.mjs";

test("maps palette classes to token utilities inside a class list, keeping every other class", () => {
  const { source } = recolour('<div className="rounded border border-slate-200 bg-white p-4 text-slate-900">x</div>');
  assert.equal(source, '<div className="rounded border border-line bg-surface p-4 text-ink">x</div>');
});

test("keeps variants such as hover: and disabled: on the mapped class", () => {
  const { source } = recolour('"px-3 hover:bg-slate-100 disabled:text-slate-600 disabled:border-slate-400 focus:outline-slate-900"');
  assert.equal(source, '"px-3 hover:bg-sunken disabled:text-muted disabled:border-field focus:outline-accent"');
});

test("a variant with its own row in the table wins over the plain class", () => {
  assert.equal(recolour('"bg-slate-50 hover:bg-slate-50"').source, '"bg-canvas hover:bg-sunken"');
});

test("slate-700 text is a label (ink-2) when the list sets a weight, otherwise muted", () => {
  assert.equal(recolour('"text-xs font-medium text-slate-700"').source, '"text-xs font-medium text-ink-2"');
  assert.equal(recolour('"text-sm text-slate-700"').source, '"text-sm text-muted"');
});

test("white text follows the fill in the same class list: on-accent on a primary, on-danger on a destructive one", () => {
  assert.equal(recolour('"bg-slate-900 text-white hover:bg-slate-700"').source, '"bg-accent text-on-accent hover:bg-accent-hover"');
  assert.equal(recolour('"bg-red-700 text-white hover:bg-red-800"').source, '"bg-danger text-on-danger hover:bg-danger/90"');
});

test("maps the notice colours: red to danger, green and emerald to accent, amber to flag", () => {
  assert.equal(
    recolour('"border-red-200 bg-red-50 text-red-800" "border-green-200 bg-green-50 text-green-900" "bg-emerald-100 text-emerald-800" "border-amber-300 bg-amber-50 text-amber-950"').source,
    '"border-danger-soft bg-danger-soft text-danger" "border-accent-soft bg-accent-soft text-accent-ink" "bg-accent-soft text-accent-ink" "border-flag bg-flag-soft text-flag"',
  );
});

test("works inside template literals and ternaries", () => {
  assert.equal(recolour('className={`p-6 ${on ? "border-slate-300" : "text-red-700"}`}').source, 'className={`p-6 ${on ? "border-field" : "text-danger"}`}');
});

test("leaves what it cannot map and reports it as ambiguous, with its line", () => {
  const result = recolour('"p-1"\n"border-slate-700 text-white bg-slate-200"');
  assert.equal(result.source, '"p-1"\n"border-slate-700 text-white bg-sunken"');
  assert.deepEqual(result.left, [
    { line: 2, cls: "border-slate-700", reason: "ambiguous" },
    { line: 2, cls: "text-white", reason: "ambiguous" },
  ]);
});

test("leaves a class a test pins, and reports it as pinned", () => {
  const result = recolour('"text-slate-700"\n"text-slate-700"', [{ line: 2, cls: "text-slate-700" }]);
  assert.equal(result.source, '"text-muted"\n"text-slate-700"');
  assert.deepEqual(result.left, [{ line: 2, cls: "text-slate-700", reason: "pinned by a test" }]);
});

test("a pinned class can take its token as an important override, so the test still finds the class and both Appearances read", () => {
  const result = recolour('"block text-slate-700"', [{ line: 1, cls: "text-slate-700", override: "text-muted" }]);
  assert.equal(result.source, '"block text-slate-700 text-muted!"');
  assert.deepEqual(result.left, [{ line: 1, cls: "text-slate-700", reason: "pinned by a test; text-muted! applied over it" }]);
});

test("links in running text take the accent, and every focus outline the accent", () => {
  assert.equal(recolour('"[&_a]:text-blue-800 focus:outline-slate-500"').source, '"[&_a]:text-accent focus:outline-accent"');
});

test("ignores text outside string literals and object keys that only look like variants", () => {
  const code = 'const c = { light: "#fff", dark: "#000" }; // bg-white in a comment\n';
  assert.deepEqual(recolour(code), { source: code, left: [] });
});

function fixture(files) {
  const root = mkdtempSync(join(tmpdir(), "colour-codemod-"));
  for (const [path, text] of Object.entries(files)) {
    mkdirSync(dirname(join(root, path)), { recursive: true });
    writeFileSync(join(root, path), text);
  }
  return root;
}

test("rewrites the Studio's source files in place, skipping tests and the design system, and lists what it left", () => {
  const root = fixture({
    "apps/studio/src/Page.tsx": '<p className="text-slate-900 border-slate-700">ok</p>\n',
    "apps/studio/src/Page.test.tsx": 'expect(x).toHaveClass("text-slate-900");\n',
    "apps/studio/src/design/Badge.tsx": '"bg-white"\n',
    "apps/studio/src/test/theme.ts": '"bg-white"\n',
    "apps/studio/src/index.css": ".x { color: red; }\n",
    "apps/studio/src/Pinned.tsx": '"text-slate-700"\n',
    "packages/ui/src/MarkdownEditor.tsx": '"bg-white"\n',
    "packages/ui/src/ChatWindow.tsx": '"bg-white"\n',
  });
  const logs = [];
  const code = main([], { cwd: root, log: (line) => logs.push(line), pins: { "apps/studio/src/Pinned.tsx": [{ line: 1, cls: "text-slate-700" }] } });
  assert.equal(code, 0);
  const read = (path) => readFileSync(join(root, "apps/studio/src", path), "utf8");
  assert.equal(read("Page.tsx"), '<p className="text-ink border-slate-700">ok</p>\n');
  assert.equal(read("Page.test.tsx"), 'expect(x).toHaveClass("text-slate-900");\n');
  assert.equal(read("design/Badge.tsx"), '"bg-white"\n');
  assert.equal(read("test/theme.ts"), '"bg-white"\n');
  assert.equal(read("Pinned.tsx"), '"text-slate-700"\n');
  assert.equal(readFileSync(join(root, "packages/ui/src/MarkdownEditor.tsx"), "utf8"), '"bg-surface"\n');
  assert.equal(readFileSync(join(root, "packages/ui/src/ChatWindow.tsx"), "utf8"), '"bg-white"\n');
  assert.deepEqual(logs, [
    "Changed 2 files, left 2 classes:",
    "  apps/studio/src/Page.tsx:1 border-slate-700 (ambiguous)",
    "  apps/studio/src/Pinned.tsx:1 text-slate-700 (pinned by a test)",
  ]);
  const again = [];
  main(["--check"], { cwd: root, log: (line) => again.push(line), pins: { "apps/studio/src/Pinned.tsx": [{ line: 1, cls: "text-slate-700" }] } });
  assert.equal(again[0], "Would change 0 files, left 2 classes:");
});

test("--check reports without writing, and an unknown argument is a usage error", () => {
  const root = fixture({ "apps/studio/src/Page.tsx": '"bg-white"\n', "packages/ui/src/MarkdownEditor.tsx": '"p-1"\n' });
  const logs = [];
  assert.equal(main(["--check"], { cwd: root, log: (line) => logs.push(line), pins: {} }), 0);
  assert.equal(readFileSync(join(root, "apps/studio/src/Page.tsx"), "utf8"), '"bg-white"\n');
  assert.deepEqual(logs, ["Would change 1 file, left 0 classes:"]);
  const errors = [];
  assert.equal(main(["--nope"], { cwd: root, error: (line) => errors.push(line) }), 2);
  assert.deepEqual(errors, ["usage: colour-codemod [--check]"]);
});
