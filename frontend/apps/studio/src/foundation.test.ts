import { readFileSync } from "node:fs";
import { join } from "node:path";

// The page shell and global stylesheet, read from disk: under Vitest a CSS import is empty and
// index.html is never loaded. This is the contract the browser gets before any route renders.
const html = readFileSync(join(import.meta.dirname, "..", "index.html"), "utf8");
const indexCss = readFileSync(join(import.meta.dirname, "index.css"), "utf8");
const tokensCss = readFileSync(join(import.meta.dirname, "design", "tokens.css"), "utf8");

/** The colour tokens tokens.css exposes to Tailwind (`--color-canvas` → `canvas`). */
const tokenColours = new Set([...tokensCss.matchAll(/--color-([a-z0-9-]+):/g)].map(([, name]) => name));

describe("the Studio's page", () => {
  it("loads the design tokens straight after Tailwind, so every token utility exists", () => {
    const imports = [...indexCss.matchAll(/^@import\s+"([^"]+)";/gm)].map(([, path]) => path);
    expect(imports).toEqual(["tailwindcss", "./design/tokens.css"]);
  });

  it("loads Instrument Sans and IBM Plex Mono, the fonts the tokens name", () => {
    const stylesheet = /<link\s[^>]*href="(https:\/\/fonts\.googleapis\.com\/css2\?[^"]+)"[^>]*rel="stylesheet"/.exec(html);
    expect(stylesheet, "a Google Fonts stylesheet link").not.toBeNull();
    const families = new URL((stylesheet as RegExpExecArray)[1] as string).searchParams.getAll("family");
    expect(families.map((family) => family.split(":")[0])).toEqual(["Instrument Sans", "IBM Plex Mono"]);
    expect(html).toContain('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />');
    expect(tokensCss).toContain('--font-sans: "Instrument Sans"');
    expect(tokensCss).toContain('--font-mono: "IBM Plex Mono"');
  });

  it("takes its background, text colour and focus ring from tokens", () => {
    const body = /body\s*\{([^}]*)\}/.exec(tokensCss)?.[1] ?? "";
    expect(body).toContain("background-color: var(--ds-canvas);");
    expect(body).toContain("color: var(--ds-ink);");
    const focus = /:focus-visible\s*\{([^}]*)\}/.exec(tokensCss)?.[1] ?? "";
    expect(focus).toContain("outline: 2px solid var(--ds-accent);");
  });

  it("styles rendered markdown with tokens, not palette colours", () => {
    const markdown = indexCss.slice(indexCss.indexOf(".markdown"));
    // Every colour utility (`bg-*`, `text-*`, `border-*` naming a colour) must name a token.
    const colours = [...markdown.matchAll(/\b(?:bg|text|border)-([a-z]+(?:-[a-z0-9]+)*)/g)]
      .map(([, name]) => name as string)
      .filter((name) => !/^(?:left|right|top|bottom|collapse|xl|lg|sm|xs|base|\d.*)$/.test(name));
    expect(colours.length).toBeGreaterThan(0);
    expect(colours.filter((name) => !tokenColours.has(name))).toEqual([]);
    expect(markdown).toMatch(/\.markdown th, \.markdown td \{[^}]*border-line/);
    // Code sets its own text colour too: on the sunken fill, the surrounding text colour may not
    // contrast (a page still on palette colours keeps dark text in the dark Appearance).
    expect(markdown).toMatch(/\.markdown code \{[^}]*bg-sunken[^}]*text-ink/);
    expect(markdown).toMatch(/\.markdown pre \{[^}]*bg-sunken[^}]*text-ink/);
  });
});
