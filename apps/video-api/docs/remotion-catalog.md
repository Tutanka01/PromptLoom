---
name: remotion-catalog
description: The proposable component palette for Remotion STEM scene generation in video-api — what the LLM may compose, with signatures and when to use each.
---

# Remotion component catalog (STEM-general)

Two layers, both for explainer videos on **any STEM subject** (math, physics,
chemistry, biology, statistics, CS, engineering):

1. **Data-driven scene palette** — whole scene types the LLM *blueprint* picks by
   name + props (it writes no code). The reliable path. See the table below.
2. **Building blocks** — the catalog + layout primitives those scenes compose,
   also available to a bespoke `Custom` scene (free-form TSX). A Custom scene may
   import ONLY from `react`, `remotion`, and the barrel `"../../lib"` (which
   re-exports everything below); follow `remotion-skill.md`.

Everything lives under `apps/video-api/remotion/src/`. All scenes are 1920×1080
@ 60fps. A scene receives its length in frames as the **`dur` prop**; drive beats
off `p = useCurrentFrame() / dur` (NOT `useVideoConfig().durationInFrames`, which
is the whole video).

## Data-driven scene palette (`scenes/data/scenes.tsx`)

The blueprint composes these by `{component, props}`. Signatures: see
`remotion-engine.md`.

| Component | When the narration is about… |
|---|---|
| `TitleScene` | opening a video/section |
| `BulletScene` | a list / definition / recap |
| `FormulaScene` | equations, a derivation (KaTeX) |
| `CodeScene` | code / algorithms (Shiki, line-by-line) |
| `PlotScene` | a function / data / motion over time |
| `DiagramScene` | systems, relationships (nodes + edges) |
| `ComparisonScene` | two things contrasted (user vs kernel, before/after) |
| `LayeredSystemScene` | stacked layers (app / syscall / kernel / hardware) |
| `TimelineScene` | an ordered process / lifecycle |
| `TerminalScene` | a shell command + its output |
| `MemoryScene` | memory / page tables / registers / stack frames |
| `FlowScene` | data moving through stages (a syscall's path) |
| `BarChartScene` | quantities / benchmarks |
| `CounterScene` | one headline metric (throughput, size, count) |

## Pick a building block by subject

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
| `MemoryGrid` | `cells[{label?,sub?,color?,highlight?}], cols, x, y, reveal, accent` | **cells**: memory blocks, page-table entries, registers, stack frames, buffers |
| `FlowToken` | `from, to, progress, color, label, size` | a packet/token travelling a path (route it ABOVE/BELOW the row it describes) |
| `BarChart` | `bars[{label,value,color?}], width, height, grow, maxValue` | quantities / benchmarks (the discrete complement to `Plot`) |
| `Counter` | `value, progress, prefix, suffix, decimals, fontSize, color` | a number counting up to a metric |

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

## Scene transitions — automatic, do NOT author them

`MainComposition` renders a **persistent `AmbientBackground`** behind every scene
and each scene fades its own content in/out at its edges (`appear(p,0,0.06) *
tailFade(p,0.93)`), so consecutive scenes cross-dissolve through the continuous
background with **no hard cuts and no black frames**. Crucially this changes no
scene's start/duration, so the per-segment voiceover muxed by `assemble_en.sh`
stays in sync.

Do NOT use `@remotion/transitions`/`TransitionSeries` in a scene: it overlaps
neighbouring scenes, which shortens the timeline and desynchronises the audio.
Just fade your own content in at the start and out near `p=1` with `tailFade(p)`.

## Reference (study before authoring)

- `src/scenes/data/scenes.tsx` — the full data-driven palette; the clearest
  worked examples of composing the catalog + primitives (focus/dim, staggered
  reveals, the `Shell` envelope, the `dur`-driven beat pattern).
- `src/catalog/*` — each primitive is small and self-documenting.

## Provenance

`catalog/text.tsx` is curated/adapted from the MIT-licensed
`ali-abassi/remotion-templates` (a Remotion skill for AI coding agents).
`CodeBlock` uses [Shiki](https://shiki.style); `MathFormula` uses
[KaTeX](https://katex.org). The base of `remotion-skill.md` is Remotion's own LLM guidance
(https://www.remotion.dev/llms.txt).
