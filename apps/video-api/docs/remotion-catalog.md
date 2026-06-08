---
name: remotion-catalog
description: The proposable component palette for Remotion STEM scene generation in video-api — what the LLM may compose, with signatures and when to use each.
---

# Remotion component catalog (STEM-general)

This is the **palette** offered to the scene generator for explainer videos on
**any STEM subject** (math, physics, chemistry, biology, statistics, CS,
engineering). Prefer composing these tested components (the reliable path); you
may also author a bespoke scene in free-form TSX, but then follow
`remotion-skill.md` and use these as worked examples. Everything lives under
`apps/video-api/remotion/src/`.

All scenes are 1920×1080 @ 60fps. Drive beats off
`p = useCurrentFrame() / useVideoConfig().durationInFrames`.

## Pick by subject

| If the narration is about… | Use |
|---|---|
| equations, definitions, derivations | `MathFormula` (KaTeX) |
| a function / data / motion over time | `Plot` (axes, curve, tangent, area, point) |
| code, algorithms, commands | `CodeBlock` (Shiki) |
| systems, processes, relationships | `Card` + `Arrow` + `Zone` (nodes/edges) |
| naming/labelling parts | `Caption`, `Pill`, `TitleBar` |
| emphasis on a word/term | `TextReveal`, `BlurReveal`, `ScaleBounce` |

## Core STEM building blocks — `catalog/`

| Component | Signature (key props) | Use for |
|---|---|---|
| `AmbientBackground` | `accent` | **default background** — continuous motion, never freezes |
| `MathFormula` | `tex, display, fontSize, color, delay, align` | **any LaTeX math**: calculus, linear algebra, physics, chemistry, stats, logic |
| `Plot` | `fn, xRange, yRange, color, drawProgress, tangentAt, pointAt, areaTo, xLabel, yLabel` | **function graphs**: derivatives/tangents, integrals/area, kinematics, distributions, signals |
| `CodeBlock` | `code, lang, fontSize, startAt, lineReveal, title, accent` | syntax-highlighted code revealed line by line (CS/algorithms) |
| `TextReveal` | `text, fontSize, color, delay, staggerDelay` | word-by-word heading reveal |
| `TypewriterText` | `text, fontSize, color, speed, showCursor` | typing a command/expression |
| `BlurReveal` | `text, fontSize, color, delay` | calm blur→sharp key statement / summary |
| `ScaleBounce` | `text, fontSize, color, delay` | spring emphasis on a single term |

## Layout primitives — `components/primitives`

Positioning uses Manim-style coordinates mapped to pixels via `style/tokens`
(`mx(x)`, `my(y)`, `mu(units)`; 1 unit = 135px; origin centered, y-up).

| Component | Signature (key props) | Use for |
|---|---|---|
| `TitleBar` | `label, opacity` | scene title + underline |
| `Card` | `x, y, w, h, accent, glow, opacity, fontPx, children` | a labelled node (any concept box) |
| `CodeCard` | Card, mono | short mono label |
| `Pill` | `x, y, w, label, color, opacity` | small tag / quantity chip |
| `Zone` | `x, y, w, h, color, fill, label, strokeWidth` | a region / grouping |
| `Arrow` | `from, to, color, width, progress, dashed` | connector / vector; `progress` 0..1 draws it |
| `Caption` | `x, y, label, color, size, opacity, width` | one-line annotation |
| `CrossMark` | `x, y, size, opacity` | red ✕ over a blocked/invalid path |
| `Terminal` | `x, y, w, h, text, typed, opacity` | terminal prompt box (CS) |
| `Background` | — | static dotted bg (prefer `AmbientBackground`) |

### Domain example components (one subject's pack, not the core)

`KernelBadge` and `HardwareBox` are kernel/OS-specific nodes — examples of how a
domain gets its own flavored components. Other subjects would add their own
(e.g. a molecule, a circuit symbol, a cell). Do not reach for these unless the
topic is operating systems.

## Scene transitions — `@remotion/transitions`

Presentations: `fade`, `slide`, `wipe`, `flip`, `clockWipe`, `none`. Timings:
`springTiming`, `linearTiming`.

```tsx
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";

<TransitionSeries>
  <TransitionSeries.Sequence durationInFrames={s1}><Audio src={a1} /><SceneOne /></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 24 })} />
  <TransitionSeries.Sequence durationInFrames={s2}><Audio src={a2} /><SceneTwo /></TransitionSeries.Sequence>
</TransitionSeries>
```

See `src/SyscallV2.tsx` for a working two-scene transition with audio.

## Reference scenes (study before authoring)

- `src/scenes/DerivativeDemo.tsx` — **calculus**: a plotted curve with a sweeping
  tangent + KaTeX limit definition. Shows the math/plot path. (different domain)
- `src/scenes/Scene1HookV2.tsx` — **CS/OS**: progressive disclosure with a Shiki
  code block, a routed flow, focus/dim. The pedagogy + layout bar.

## Provenance

`catalog/text.tsx` is curated/adapted from the MIT-licensed
`ali-abassi/remotion-templates` (a Remotion skill for AI coding agents).
`CodeBlock` uses [Shiki](https://shiki.style); `MathFormula` uses
[KaTeX](https://katex.org); transitions are official `@remotion/transitions`.
The base of `remotion-skill.md` is Remotion's own LLM guidance
(https://www.remotion.dev/llms.txt).
