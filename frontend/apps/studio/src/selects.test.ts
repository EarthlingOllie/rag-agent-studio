// Every select draws the design system's chevron from one base rule (design/tokens.css); its box
// comes from a `field` recipe, which also tells the rule where the chevron sits. This keeps pages
// from growing their own select class strings again.
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";

import { field } from "./design";

const SELECT_RECIPES = ["select", "selectCompact", "pill"] as const;

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sources(path);
    return /\.tsx$/.test(entry.name) && !/\.test\.tsx$/.test(entry.name) ? [path] : [];
  });
}

/** Each `<select …>` opening tag's className, as written: `{field.pill}` or `"h-9 …"`. */
function selectClasses(): string[] {
  return sources(import.meta.dirname).flatMap((path) => {
    const code = readFileSync(path, "utf8");
    return code
      .split(/<select\b/)
      .slice(1)
      .map((rest) => {
        const tag = rest.split(/<option|<\/select>|>\n\s*\{/)[0] as string;
        const className = /className=(\{[^}]+\}|"[^"]*")/.exec(tag)?.[1] ?? "(none)";
        return `${relative(import.meta.dirname, path)}: ${className}`;
      });
  });
}

test("every select in the Studio takes its classes from a field recipe, none from its own string", () => {
  const selects = selectClasses();
  expect(selects.length).toBeGreaterThan(20);
  const recipe = new RegExp(`: \\{\`?(?:\\$\\{)?fields?\\.(?:${SELECT_RECIPES.join("|")})\\b`);
  expect(selects.filter((select) => !recipe.test(select))).toEqual([]);
});

test.each(SELECT_RECIPES)("field.%s puts the chevron as far from the right as its text from the left", (name) => {
  const recipe = field[name];
  const left = /(?:^|\s)p[xl]-([\d.]+)(?:\s|$)/.exec(recipe)?.[1];
  expect(left, `field.${name} sets its left padding`).toBeDefined();
  expect(recipe).toContain(`[--select-inset:--spacing(${left as string})]`);
});
