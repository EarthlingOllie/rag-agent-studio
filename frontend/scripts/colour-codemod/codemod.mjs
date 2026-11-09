// One-off colour codemod (ticket 11-03, spec 11): applies the class-mapping table from the
// `studio-reskin` skill (.claude/skills/studio-reskin/PATTERNS.md) to the class lists under
// apps/studio/src and to the Studio-only Markdown editor in packages/ui. It changes colour classes
// only: no markup, text, routes or tests. A class it cannot map with confidence, or that a test
// asserts, is left (or overridden, see PINS) and listed for review.
// Run from frontend/: `node scripts/colour-codemod/cli.mjs [--check]`. Deleted once applied.
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";

const STUDIO_SRC = "apps/studio/src";

/** A label when the class list gives the text a weight; a description or meta text otherwise. */
const slateText = (list) => (/\bfont-(medium|semibold|bold)\b/.test(list) ? "text-ink-2" : "text-muted");
/** White text sits on the fill in the same class list. */
const whiteText = (list) =>
  /\bbg-red-700\b/.test(list) ? "text-on-danger" : /\bbg-slate-900\b/.test(list) ? "text-on-accent" : undefined;

/**
 * The table. Keys are a class, or a class with its variant where that variant maps differently.
 * Values are the token class, or a function of the whole class list it sits in.
 */
export const MAPPING = {
  "bg-slate-50": "bg-canvas",
  "hover:bg-slate-50": "hover:bg-sunken",
  "bg-slate-100": "bg-sunken",
  "bg-slate-200": "bg-sunken",
  "bg-slate-500": "bg-muted",
  "bg-slate-600": "bg-muted",
  "bg-slate-700": "bg-chart-1",
  "hover:bg-slate-700": "hover:bg-accent-hover",
  "bg-slate-900": "bg-accent",
  "bg-white": "bg-surface",
  "text-slate-500": "text-muted",
  "text-slate-600": "text-muted",
  "text-slate-700": slateText,
  "text-slate-800": "text-ink",
  "text-slate-900": "text-ink",
  "text-white": whiteText,
  "border-slate-100": "border-line-soft",
  "border-slate-200": "border-line",
  "divide-slate-200": "divide-line",
  "border-slate-300": "border-field",
  "border-slate-400": "border-field",
  "outline-slate-500": "outline-accent",
  "outline-slate-900": "outline-accent",
  "text-blue-800": "text-accent",
  "bg-red-50": "bg-danger-soft",
  "bg-red-100": "bg-danger-soft",
  "bg-red-700": "bg-danger",
  "hover:bg-red-800": "hover:bg-danger/90",
  "text-red-700": "text-danger",
  "text-red-800": "text-danger",
  "text-red-900": "text-danger",
  "border-red-200": "border-danger-soft",
  "border-red-300": "border-danger",
  "border-red-700": "border-danger",
  "border-red-800": "border-danger",
  "bg-green-50": "bg-accent-soft",
  "bg-green-100": "bg-accent-soft",
  "bg-emerald-100": "bg-accent-soft",
  "text-green-900": "text-accent-ink",
  "text-emerald-800": "text-accent-ink",
  "text-emerald-900": "text-accent-ink",
  "border-green-200": "border-accent-soft",
  "bg-amber-50": "bg-flag-soft",
  "bg-amber-100": "bg-flag-soft",
  "text-amber-800": "text-flag",
  "text-amber-900": "text-flag",
  "text-amber-950": "text-flag",
  "border-amber-200": "border-flag-soft",
  "border-amber-300": "border-flag",
  "border-amber-500": "border-flag",
};

/**
 * Classes a unit test asserts (tests may not change in this ticket), by file and line. A pin with
 * an `override` keeps the class for the test and adds the token with Tailwind's important modifier,
 * which wins whatever the stylesheet order, so the element reads in both Appearances.
 */
export const PINS = {
  "apps/studio/src/projects/DocumentsTab.tsx": [
    { line: 131, cls: "border-slate-700" },
    { line: 170, cls: "text-slate-700", override: "text-muted" },
  ],
  "apps/studio/src/projects/VersionComparison.tsx": [{ line: 63, cls: "bg-amber-50", override: "bg-flag-soft" }],
};

/** Besides the Studio's own source: the Studio-only Markdown editor it imports from packages/ui. */
const EXTRA = ["packages/ui/src/MarkdownEditor.tsx"];

const LITERAL = /`(?:[^`\\]|\\.)*`|"(?:[^"\\\n]|\\.)*"/g;
const TOKEN = /[^\s"'`{}]+/g;
const PALETTE = /^(.*:)?((?:bg|text|border|divide|outline|ring)-(?:white|black|(?:slate|gray|zinc|red|green|amber|blue|emerald)-\d{2,3}))$/;

/** Recolours one file's source. Returns the new source and the palette classes it left. */
export function recolour(source, pins = []) {
  const left = [];
  const lineAt = (offset) => source.slice(0, offset).split("\n").length;
  const out = source.replace(LITERAL, (literal, start) =>
    literal.replace(TOKEN, (token, at) => {
      const match = PALETTE.exec(token);
      if (!match) return token;
      const [, variant = "", cls] = match;
      const line = lineAt(start + at);
      const pin = pins.find((p) => p.line === line && p.cls === token);
      if (pin) {
        if (!pin.override) {
          left.push({ line, cls: token, reason: "pinned by a test" });
          return token;
        }
        left.push({ line, cls: token, reason: `pinned by a test; ${pin.override}! applied over it` });
        return `${token} ${pin.override}!`;
      }
      const own = MAPPING[token];
      const rule = own ?? MAPPING[cls];
      const mapped = typeof rule === "function" ? rule(literal) : rule;
      if (mapped === undefined) {
        left.push({ line, cls: token, reason: "ambiguous" });
        return token;
      }
      return own === undefined ? `${variant}${mapped}` : mapped;
    }),
  );
  return { source: out, left };
}

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory() ? walk(join(dir, entry.name)) : [join(dir, entry.name)],
  );
}

/** Applies the table to every Studio source file except tests, test helpers and the design system. */
export function main(args, { cwd = process.cwd(), log = console.log, error = console.error, pins = PINS } = {}) {
  if (args.some((arg) => arg !== "--check")) {
    error("usage: colour-codemod [--check]");
    return 2;
  }
  const files = walk(join(cwd, STUDIO_SRC))
    .map((file) => relative(cwd, file))
    .filter((path) => /\.tsx?$/.test(path) && !/\.test\.tsx?$/.test(path) && !/^apps\/studio\/src\/(design|test)\//.test(path))
    .concat(EXTRA.filter((path) => existsSync(join(cwd, path))))
    .sort();
  let changed = 0;
  const report = [];
  for (const path of files) {
    const before = readFileSync(join(cwd, path), "utf8");
    const { source, left } = recolour(before, pins[path] ?? []);
    if (source !== before) {
      changed += 1;
      if (!args.includes("--check")) writeFileSync(join(cwd, path), source);
    }
    for (const item of left) report.push(`  ${path}:${String(item.line)} ${item.cls} (${item.reason})`);
  }
  const verb = args.includes("--check") ? "Would change" : "Changed";
  log(`${verb} ${String(changed)} file${changed === 1 ? "" : "s"}, left ${String(report.length)} classes:`);
  for (const line of report) log(line);
  return 0;
}
