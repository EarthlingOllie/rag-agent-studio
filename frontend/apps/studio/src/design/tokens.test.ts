import { readFileSync } from "node:fs";
import { join } from "node:path";

import { contrastRatio } from "@studio/ui";

// Read from disk: under Vitest a CSS import (even `?raw`) is empty.
const css = readFileSync(join(import.meta.dirname, "tokens.css"), "utf8");

/** The `--ds-*` hex values declared inside the first block that follows `selector`. */
function block(selector: string): Record<string, string> {
  const start = css.indexOf(selector);
  expect(start, `${selector} is in tokens.css`).toBeGreaterThanOrEqual(0);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("}", start));
  const tokens: Record<string, string> = {};
  for (const [, name, value] of body.matchAll(/--ds-([a-z0-9-]+):\s*([^;]+);/g)) {
    tokens[name as string] = (value as string).trim();
  }
  return tokens;
}

const light = block(":root {");
const darkBySystem = block(':root:not([data-appearance="light"])');
const darkByChoice = block(':root[data-appearance="dark"]');

/** Text needs 4.5:1 (WCAG 1.4.3); non-text marks such as the status dot and focus ring need 3:1. */
const PAIRS: readonly [foreground: string, background: string, required: number][] = [
  ["ink", "canvas", 4.5],
  ["ink", "surface", 4.5],
  ["ink", "sunken", 4.5],
  ["ink-2", "surface", 4.5],
  ["muted", "canvas", 4.5],
  ["muted", "surface", 4.5],
  ["muted", "sunken", 4.5],
  ["accent", "surface", 4.5],
  ["accent", "canvas", 4.5],
  ["on-accent", "accent", 4.5],
  ["on-accent", "accent-hover", 4.5],
  ["accent-ink", "accent-soft", 4.5],
  ["sand-ink", "sand", 4.5],
  ["flag", "surface", 4.5],
  ["flag", "flag-soft", 4.5],
  ["danger", "surface", 4.5],
  ["danger", "danger-soft", 4.5],
  ["accent", "sunken", 3],
  // Text on a filled danger button (ConfirmDialog's destructive action).
  ["on-danger", "danger", 4.5],
  // The one data colour: chart lines, bars and meter fills are marks, so 3:1.
  ["chart-1", "surface", 3],
  ["chart-1", "canvas", 3],
];

describe.each([
  ["light", light],
  ["dark", darkByChoice],
])("the %s Appearance", (_name, tokens) => {
  it.each(PAIRS)("%s on %s meets %d:1", (foreground, background, required) => {
    const ratio = contrastRatio(tokens[foreground] as string, tokens[background] as string);
    expect(ratio).toBeGreaterThanOrEqual(required);
  });
});

it("declares every token in light and dark, and the system dark matches the chosen dark", () => {
  expect(Object.keys(darkByChoice).sort()).toEqual(Object.keys(light).sort());
  expect(darkBySystem).toEqual(darkByChoice);
});

/** Tokens that hold an image rather than a colour. */
const IMAGES = new Set(["chevron"]);

it("exposes every colour token to Tailwind as a colour", () => {
  for (const name of Object.keys(light).filter((name) => !IMAGES.has(name))) {
    expect(css).toContain(`--color-${name}: var(--ds-${name});`);
  }
});

it("keeps the chart colour apart from the UI accent, at the approved values", () => {
  expect([light["chart-1"], darkByChoice["chart-1"]]).toEqual(["#00897b", "#1fa393"]);
  expect(light["chart-1"]).not.toBe(light.accent);
  expect(darkByChoice["chart-1"]).not.toBe(darkByChoice.accent);
});

describe("the select chevron", () => {
  /** The stroke colour inside a chevron token's SVG (`%23536260` → `#536260`). */
  function stroke(token: string | undefined): string {
    return decodeURIComponent(/stroke='([^']+)'/.exec(decodeURIComponent(token ?? ""))?.[1] ?? "");
  }

  it("is declared in the light, system-dark and chosen-dark blocks, and the two darks match", () => {
    expect(light.chevron).toMatch(/^url\("data:image\/svg\+xml,/);
    expect(darkBySystem.chevron).toMatch(/^url\("data:image\/svg\+xml,/);
    expect(darkByChoice.chevron).toMatch(/^url\("data:image\/svg\+xml,/);
    expect(darkBySystem.chevron).toBe(darkByChoice.chevron);
    expect(darkByChoice.chevron).not.toBe(light.chevron);
  });

  it("draws the design system's chevron-down, stroked in each Appearance's muted colour", () => {
    for (const tokens of [light, darkByChoice]) {
      // The Icon component's chevronDown path, at its 24×24 grid and 1.8 stroke.
      expect(decodeURIComponent(tokens.chevron as string)).toContain("<path d='M7 10l5 5 5-5'/>");
      expect(decodeURIComponent(tokens.chevron as string)).toContain("stroke-width='1.8'");
      expect(stroke(tokens.chevron)).toBe(tokens.muted);
    }
    expect([stroke(light.chevron), stroke(darkByChoice.chevron)]).toEqual(["#536260", "#93a5a2"]);
  });
});
