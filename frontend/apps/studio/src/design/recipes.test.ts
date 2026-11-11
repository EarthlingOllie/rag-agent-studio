import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";

const SRC = join(import.meta.dirname, "..");

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sources(path);
    return /\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

/**
 * A module-level class string that draws a control's box (a fixed height, a rounded border): a
 * page's own BUTTON / INPUT. The design system's recipes are the one place such strings live.
 */
const CONTROL_STRING = /^(?:export )?const \w+ =\s*["`][^"`]*\bh-(?:8|9|10|11)\b[^"`]*\brounded[^"`]*["`]/m;

test("no Studio page defines its own button or input class string", () => {
  const offenders = sources(SRC)
    .filter((path) => !relative(SRC, path).startsWith("design"))
    .filter((path) => CONTROL_STRING.test(readFileSync(path, "utf8")))
    .map((path) => relative(SRC, path));
  expect(offenders).toEqual([]);
});
