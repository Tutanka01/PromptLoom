/**
 * Design tokens ported from the reference Manim style (`syscall_style.py`).
 * Dark academic palette, focus/dim attention model. This is the local design
 * system the Remotion component library reads from.
 */

/**
 * Default palette (dark academic, ported from `syscall_style.py`). Each value is
 * also the fallback baked into `colors` below, so an un-themed render is
 * byte-identical to before theming existed.
 */
const DEFAULT_PALETTE = {
  bg: "#0D1017",
  bgTop: "#12161F",
  panel: "#151A24",
  panel2: "#202733",
  edge: "#2A3344",
  text: "#ECF1F8",
  muted: "#8A95A6",
  user: "#3A86FF",
  kernel: "#FFBE0B",
  success: "#06D6A0",
  danger: "#FB5607",
  hardware: "#6C757D",
  purple: "#9B5DE5",
} as const;

export type ColorKey = keyof typeof DEFAULT_PALETTE;

/**
 * Scenes read colours from `colors.*`. Each entry resolves a CSS custom property
 * (set once per video at the composition root by `applyThemeVars`) with the
 * default palette as fallback. Because the values are plain strings, the 100+
 * existing `colors.x` usages need no change — including SVG, as long as the
 * value is applied via `style` (CSS variables do not resolve in SVG presentation
 * attributes like `stroke=`).
 */
export const colors = Object.fromEntries(
  (Object.keys(DEFAULT_PALETTE) as ColorKey[]).map((key) => [
    key,
    `var(--c-${key}, ${DEFAULT_PALETTE[key]})`,
  ]),
) as Record<ColorKey, string>;

/**
 * Alpha-blend any colour toward transparent. Unlike the old `${color}33` hex
 * suffix, this works when *color* is a `var(--c-*)` token (CSS variables can't
 * be string-concatenated). Uses `color-mix`, supported by Remotion's Chromium.
 * `a` is 0..1; in CSS (style props) only — not in SVG presentation attributes.
 */
export const alpha = (color: string, a: number): string =>
  `color-mix(in srgb, ${color} ${Math.round(a * 100)}%, transparent)`;

/**
 * Bounded art-direction palettes. The LLM picks one per video (`art_direction`
 * in the blueprint); `default` reproduces the original look exactly. Keep the
 * keys in sync with `REMOTION_THEMES` in schemas.py (parity-tested). All themes
 * are dark so the focus/dim model, drop shadows and ambient glows stay readable.
 */
export const THEMES = {
  default: { ...DEFAULT_PALETTE },
  blueprint: { bg: "#081020", bgTop: "#0C1830", panel: "#11203F", panel2: "#182C52", edge: "#243C63", text: "#E9F3FF", muted: "#93A8CC", user: "#4CC9F0", kernel: "#FFD166", success: "#64DFDF", danger: "#FF6B6B", hardware: "#6B7DA3", purple: "#9D8DF1" },
  forest: { bg: "#08140F", bgTop: "#0C1D16", panel: "#102A20", panel2: "#16382B", edge: "#21503C", text: "#E8F6EE", muted: "#88AC9B", user: "#2DD4BF", kernel: "#FCD34D", success: "#34D399", danger: "#FB7185", hardware: "#5F8775", purple: "#A78BFA" },
  synthwave: { bg: "#120A1F", bgTop: "#1A0F2E", panel: "#241541", panel2: "#321E57", edge: "#432A6E", text: "#F3EAFF", muted: "#A595C2", user: "#36E2EC", kernel: "#FFD300", success: "#2BF5A0", danger: "#FF4D8D", hardware: "#7E6CA8", purple: "#C77DFF" },
  carbon: { bg: "#0A0A0B", bgTop: "#121214", panel: "#18181B", panel2: "#232328", edge: "#34343B", text: "#F4F4F5", muted: "#9A9AA3", user: "#60A5FA", kernel: "#F59E0B", success: "#22C55E", danger: "#EF4444", hardware: "#71717A", purple: "#A78BFA" },
  plum: { bg: "#160C16", bgTop: "#1F1020", panel: "#2A1530", panel2: "#3A1E40", edge: "#512A56", text: "#FBEFF6", muted: "#B596AE", user: "#F072B6", kernel: "#FFC15E", success: "#5FD0A0", danger: "#FF6B6B", hardware: "#8A6E84", purple: "#C18BE0" },
} satisfies Record<string, Record<ColorKey, string>>;

export type ThemeName = keyof typeof THEMES;

export const THEME_NAMES = Object.keys(THEMES) as ThemeName[];

/**
 * CSS custom properties for one theme, to spread into the root element's style.
 * An unknown/stale name falls back to `default`, so a bad value never breaks a
 * render.
 */
export const applyThemeVars = (theme?: string): React.CSSProperties => {
  const palette = THEMES[(theme ?? "default") as ThemeName] ?? THEMES.default;
  const vars: Record<string, string> = {};
  for (const key of Object.keys(palette) as ColorKey[]) {
    vars[`--c-${key}`] = palette[key];
  }
  return vars as React.CSSProperties;
};

export const DIM_OPACITY = 0.32;

// Web-safe stand-ins for the macOS fonts used in the Manim reference
// (Helvetica Neue / Menlo are unavailable on Linux render workers; Inter +
// JetBrains-style mono read cleanly at small sizes — see Dockerfile note).
export const fonts = {
  sans: "'Inter', system-ui, -apple-system, 'Helvetica Neue', sans-serif",
  mono: "'JetBrains Mono', 'SF Mono', Menlo, monospace",
} as const;

// Font sizes from syscall_style.py, scaled. Manim font_size is in points on an
// 8-unit-tall frame; multiply by the unit→px factor / a tuned constant so text
// matches the reference optical size at 1080p.
export const fontSize = {
  h1: 52,
  h2: 38,
  body: 31,
  caption: 25,
  code: 28,
} as const;

/**
 * Manim places objects on a frame that is 8 units tall and ~14.22 wide, y-up,
 * centered at the origin. At 1080p that is exactly 135 px per Manim unit. This
 * helper maps Manim coordinates to CSS pixels (y-down, origin top-left) so
 * scenes ported from the reference keep their exact composition.
 */
export const PX_PER_UNIT = 135;
export const WIDTH = 1920;
export const HEIGHT = 1080;

export const mx = (x: number): number => WIDTH / 2 + x * PX_PER_UNIT;
export const my = (y: number): number => HEIGHT / 2 - y * PX_PER_UNIT;
export const mu = (units: number): number => units * PX_PER_UNIT;

/** Absolute-position style helper: place an element's CENTER at Manim (x, y). */
export const atCenter = (
  x: number,
  y: number,
  w: number,
  h: number,
): React.CSSProperties => ({
  position: "absolute",
  left: mx(x) - mu(w) / 2,
  top: my(y) - mu(h) / 2,
  width: mu(w),
  height: mu(h),
});
