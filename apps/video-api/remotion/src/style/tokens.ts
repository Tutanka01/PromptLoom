/**
 * Design tokens ported from the reference Manim style (`syscall_style.py`).
 * Dark academic palette, focus/dim attention model. This is the local design
 * system the Remotion component library reads from.
 */

export const colors = {
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
