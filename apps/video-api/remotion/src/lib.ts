/**
 * Public surface for bespoke `Custom` scenes (the free-TSX escape hatch).
 *
 * A Custom scene lives at `src/jobScenes/<id>/<key>.tsx` and may import ONLY from
 * "react", "remotion", and this barrel `"../../lib"`. This file re-exports the
 * curated, tested design system — catalog primitives, layout primitives, design
 * tokens, coordinate helpers and the beat/cue animation helpers — plus the
 * handful of Remotion APIs a scene needs, so a generated scene has ONE stable,
 * type-checked import surface and can never reach unreviewed modules.
 *
 * Keep this barrel in sync with the scene-coder prompt (`remotion_scene_coder.py`,
 * `_SYSTEM`) and `docs/remotion-skill.md`. The unit test
 * `test_lib_barrel_exports_promised_symbols` enforces that every symbol the
 * prompt advertises "from ../../lib" is actually re-exported here.
 */

// --- Remotion core APIs ----------------------------------------------------
export {
  AbsoluteFill,
  Sequence,
  Series,
  Img,
  interpolate,
  interpolateColors,
  spring,
  useCurrentFrame,
  useVideoConfig,
  Easing,
} from "remotion";

// --- Catalog: rich, async-aware primitives ---------------------------------
export { AmbientBackground } from "./catalog/AmbientBackground";
export { MathFormula } from "./catalog/MathFormula";
export { CodeBlock } from "./catalog/CodeBlock";
export { Plot } from "./catalog/Plot";
export { TextReveal, TypewriterText, BlurReveal, ScaleBounce } from "./catalog/text";
export { MemoryGrid } from "./catalog/MemoryGrid";
export type { MemoryCell } from "./catalog/MemoryGrid";
export { FlowToken } from "./catalog/FlowToken";
export { BarChart } from "./catalog/BarChart";
export type { Bar } from "./catalog/BarChart";
export { Counter } from "./catalog/Counter";
export { Icon, ICON_NAMES } from "./catalog/Icon";

// --- Layout primitives -----------------------------------------------------
export {
  Background,
  TitleBar,
  Card,
  CodeCard,
  Pill,
  KernelBadge,
  HardwareBox,
  Zone,
  Arrow,
  Terminal,
  CrossMark,
  Caption,
} from "./components/primitives";

// --- Design tokens + Manim-coordinate helpers ------------------------------
// `colors` are themed CSS variables (the active palette is set per video at the
// composition root). For translucency use `alpha(color, 0.2)` — never the old
// `${color}33` hex suffix, which is invalid on a `var(--c-*)` value. In SVG,
// apply colours via `style={{ stroke/fill }}`, not presentation attributes.
export {
  colors,
  alpha,
  fonts,
  fontSize,
  DIM_OPACITY,
  PX_PER_UNIT,
  WIDTH,
  HEIGHT,
  mx,
  my,
  mu,
  atCenter,
} from "./style/tokens";

// --- Beat / cue animation helpers (narration-driven progress p in [0,1]) ---
export { beat, appear, dimAt, tailFade, cueOr, lastCue } from "./style/anim";
