import { DEFAULT_THEME, fontStylesheetUrl, resolveTheme, schemesFor, themeStylesheet, type Theme } from "./theme";

const brand: Theme = {
  colours: {
    primary: { light: "#b91c1c", dark: "#f87171" },
    on_primary: { light: "#ffffff", dark: "#1f2937" },
    surface: { light: "#fafaf9", dark: "#1c1917" },
    on_surface: { light: "#1c1917", dark: "#fafaf9" },
    accent: { light: "#b45309", dark: "#fbbf24" },
    muted: { light: "#57534e", dark: "#a8a29e" },
  },
  radius: 4,
  font: "Source Sans 3",
  mode: "auto",
  launcher_type: "bubble",
  launcher_position: "bottom-left",
};

test("a Theme resolves to CSS custom properties for light mode", () => {
  expect(resolveTheme(brand, "light")).toEqual({
    "--theme-primary": "#b91c1c",
    "--theme-on-primary": "#ffffff",
    "--theme-surface": "#fafaf9",
    "--theme-on-surface": "#1c1917",
    "--theme-accent": "#b45309",
    "--theme-muted": "#57534e",
    "--theme-radius": "4px",
    "--theme-font-family": '"Source Sans 3", ui-sans-serif, system-ui, sans-serif',
  });
});

test("dark mode takes each colour token's dark value; radius and font stay", () => {
  expect(resolveTheme(brand, "dark")).toEqual({
    "--theme-primary": "#f87171",
    "--theme-on-primary": "#1f2937",
    "--theme-surface": "#1c1917",
    "--theme-on-surface": "#fafaf9",
    "--theme-accent": "#fbbf24",
    "--theme-muted": "#a8a29e",
    "--theme-radius": "4px",
    "--theme-font-family": '"Source Sans 3", ui-sans-serif, system-ui, sans-serif',
  });
});

test("a light or dark Theme shows one scheme; auto follows the Visitor's preference between both", () => {
  expect(schemesFor("light")).toEqual(["light"]);
  expect(schemesFor("dark")).toEqual(["dark"]);
  expect(schemesFor("auto")).toEqual(["light", "dark"]);
});

test("the stylesheet for a fixed mode sets that mode's properties on the selector", () => {
  expect(themeStylesheet({ ...brand, mode: "dark", radius: 0 }, ".widget")).toBe(
    ".widget{color-scheme:dark;--theme-primary:#f87171;--theme-on-primary:#1f2937;--theme-surface:#1c1917;" +
      "--theme-on-surface:#fafaf9;--theme-accent:#fbbf24;--theme-muted:#a8a29e;--theme-radius:0px;" +
      '--theme-font-family:"Source Sans 3", ui-sans-serif, system-ui, sans-serif;}',
  );
});

test("the stylesheet for auto mode switches to the dark values when the Visitor prefers dark", () => {
  const css = themeStylesheet({ ...DEFAULT_THEME, mode: "auto" });

  expect(css).toBe(
    ":root{color-scheme:light;--theme-primary:#4f46e5;--theme-on-primary:#ffffff;--theme-surface:#ffffff;" +
      "--theme-on-surface:#111827;--theme-accent:#0f766e;--theme-muted:#4b5563;--theme-radius:12px;" +
      '--theme-font-family:"Inter", ui-sans-serif, system-ui, sans-serif;}' +
      "@media (prefers-color-scheme: dark){:root{color-scheme:dark;--theme-primary:#818cf8;--theme-on-primary:#111827;" +
      "--theme-surface:#111827;--theme-on-surface:#f9fafb;--theme-accent:#2dd4bf;--theme-muted:#9ca3af;" +
      '--theme-radius:12px;--theme-font-family:"Inter", ui-sans-serif, system-ui, sans-serif;}}',
  );
});

test("allowlisted fonts load from Google Fonts by family name", () => {
  expect(fontStylesheetUrl("Inter")).toBe("https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap");
  expect(fontStylesheetUrl("Source Sans 3")).toBe(
    "https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600&display=swap",
  );
});
