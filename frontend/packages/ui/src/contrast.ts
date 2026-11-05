/**
 * WCAG 2.2 contrast between the Theme's colour pairs. A failing pair is a warning, never a
 * block: the Owner decides.
 */
import { type ColourScheme, type ColourToken, schemesFor, type Theme } from "./theme";

/** Relative luminance of a `#rrggbb` colour (WCAG 2.2, from sRGB). */
export function relativeLuminance(hex: string): number {
  const [red, green, blue] = [1, 3, 5].map((start) => {
    const channel = parseInt(hex.slice(start, start + 2), 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

/** The contrast ratio of two colours, from 1 to 21; the order doesn't matter. */
export function contrastRatio(first: string, second: string): number {
  const [lighter, darker] = [relativeLuminance(first), relativeLuminance(second)].sort((a, b) => b - a) as [number, number];
  return (lighter + 0.05) / (darker + 0.05);
}

/** Text needs 4.5:1 (WCAG 1.4.3); the accent marks controls and focus, which need 3:1 (1.4.11). */
const PAIRS: readonly { foreground: ColourToken; background: ColourToken; required: number; label: string }[] = [
  { foreground: "on_primary", background: "primary", required: 4.5, label: "Text on primary" },
  { foreground: "on_surface", background: "surface", required: 4.5, label: "Text on surface" },
  { foreground: "muted", background: "surface", required: 4.5, label: "Muted text on surface" },
  { foreground: "accent", background: "surface", required: 3, label: "Accent on surface" },
];

export interface ContrastWarning {
  scheme: ColourScheme;
  foreground: ColourToken;
  background: ColourToken;
  /** Rounded down to two decimals. */
  ratio: number;
  required: number;
  message: string;
}

/** Every colour pair that fails WCAG AA in a colour scheme the Theme shows. */
export function contrastWarnings(theme: Theme): ContrastWarning[] {
  return schemesFor(theme.mode).flatMap((scheme) =>
    PAIRS.flatMap(({ foreground, background, required, label }) => {
      const fore = theme.colours[foreground][scheme];
      const back = theme.colours[background][scheme];
      const ratio = contrastRatio(fore, back);
      if (ratio >= required) return [];
      // Rounded down, so a failing ratio never displays as the required one.
      const shown = Math.floor(ratio * 100) / 100;
      return [
        {
          scheme,
          foreground,
          background,
          ratio: shown,
          required,
          message: `${label} (${fore} on ${back}) has a contrast of ${shown.toFixed(2)}:1 in ${scheme} mode. WCAG AA needs ${String(required)}:1.`,
        },
      ];
    }),
  );
}
