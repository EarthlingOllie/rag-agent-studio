import { contrastRatio, contrastWarnings, relativeLuminance } from "./contrast";
import { DEFAULT_THEME, type Theme } from "./theme";

// Reference values from the WCAG 2.2 definitions and WebAIM's contrast checker.
test.each([
  ["#000000", "#ffffff", 21],
  ["#ffffff", "#ffffff", 1],
  ["#767676", "#ffffff", 4.54],
  ["#777777", "#ffffff", 4.48],
  ["#0000ff", "#ffffff", 8.59],
  ["#ff0000", "#ffffff", 4.0],
  ["#ffffff", "#4f46e5", 6.29],
])("the contrast of %s on %s is %d:1", (foreground, background, ratio) => {
  expect(contrastRatio(foreground, background)).toBeCloseTo(ratio, 2);
  // Contrast is symmetric.
  expect(contrastRatio(background, foreground)).toBeCloseTo(ratio, 2);
});

test("relative luminance follows the sRGB formula, including the linear segment for dark channels", () => {
  expect(relativeLuminance("#000000")).toBe(0);
  expect(relativeLuminance("#FFFFFF")).toBe(1);
  // 0x0a / 255 = 0.0392, below the 0.04045 threshold: divided by 12.92.
  expect(relativeLuminance("#0a0a0a")).toBeCloseTo(0.003035, 6);
  expect(relativeLuminance("#808080")).toBeCloseTo(0.2159, 4);
});

function withColour(token: keyof Theme["colours"], light: string, dark: string, overrides: Partial<Theme> = {}): Theme {
  return { ...DEFAULT_THEME, ...overrides, colours: { ...DEFAULT_THEME.colours, [token]: { light, dark } } };
}

test("the default Theme passes WCAG AA in both modes", () => {
  expect(contrastWarnings({ ...DEFAULT_THEME, mode: "auto" })).toEqual([]);
});

test("a text pair below 4.5:1 is a warning naming the pair, the mode and the ratio", () => {
  const theme = withColour("on_primary", "#9999ff", "#111827");

  expect(contrastWarnings(theme)).toEqual([
    {
      scheme: "light",
      foreground: "on_primary",
      background: "primary",
      ratio: 2.5,
      required: 4.5,
      message: "Text on primary (#9999ff on #4f46e5) has a contrast of 2.50:1 in light mode. WCAG AA needs 4.5:1.",
    },
  ]);
});

test("the accent colour is a control colour, so it needs 3:1 against the surface", () => {
  // #2b9be8 on white is about 3.02:1: enough for a control, not for text.
  expect(contrastWarnings(withColour("accent", "#2b9be8", "#2dd4bf"))).toEqual([]);
  expect(contrastWarnings(withColour("accent", "#7cc4f2", "#2dd4bf"))).toEqual([
    expect.objectContaining({ foreground: "accent", background: "surface", required: 3, scheme: "light" }),
  ]);
});

test("muted text and surface text are checked against the surface", () => {
  const theme = withColour("muted", "#4b5563", "#374151");
  const pale = { ...theme, colours: { ...theme.colours, on_surface: { light: "#d1d5db", dark: "#f9fafb" } } };

  expect(contrastWarnings({ ...pale, mode: "auto" }).map((w) => [w.foreground, w.background, w.scheme])).toEqual([
    ["on_surface", "surface", "light"],
    ["muted", "surface", "dark"],
  ]);
});

test("only the modes the Theme uses are checked", () => {
  // The dark value fails; light mode never shows it, dark and auto do.
  const theme = withColour("muted", "#4b5563", "#1f2937");

  expect(contrastWarnings({ ...theme, mode: "light" })).toEqual([]);
  expect(contrastWarnings({ ...theme, mode: "dark" }).map((w) => w.scheme)).toEqual(["dark"]);
  expect(contrastWarnings({ ...theme, mode: "auto" }).map((w) => w.scheme)).toEqual(["dark"]);
});
