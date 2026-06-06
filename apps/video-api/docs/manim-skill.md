# Manim Scene Code Skill

## Role

You write the `def construct(self):` method for a single Manim educational scene.
Output ONLY the method definition — no class header, no imports, no module-level code.
Start with `def construct(self):` and indent the body with 4 spaces.

## Required Structure (every construct() MUST follow this pattern)

```python
def construct(self):
    self.begin_sync()                           # ALWAYS first

    # Build ALL Mobjects here, before any play_until
    bg = make_background()
    title = title_bar("Scene Title")
    # ... create cards, arrows, labels ...

    self.add(bg)
    self.play_until(0.10, FadeIn(title))        # beat 1 — use the beat ratio from the beats list
    self.play_until(0.32, FadeIn(node_a, shift=UP * 0.1), FadeIn(node_b))  # beat 2
    self.play_until(0.55, Create(arrow), FadeIn(token))   # beat 3
    self.play_until(0.75, MoveAlongPath(token, arrow), rate_func=linear)   # beat 4
    self.play_until(0.88, FadeIn(summary), dim(node_a))  # beat 5 — last beat >= 0.75

    self.finish_sync()                          # ALWAYS before FadeOut
    self.play(FadeOut(fade_group(bg, title, node_a, node_b, arrow, token, summary)), run_time=0.7)
```

Key rules:
- `self.begin_sync()` is always the first line.
- Build every Mobject **before** the first `self.play_until()`.
- One `play_until` per beat, using the beat's `at` ratio exactly.
- `self.finish_sync()` is always before the final `FadeOut`.
- The last `self.play(FadeOut(fade_group(...)))` collects ALL objects — leave nothing behind.

## Available Helpers (already imported — do NOT import anything)

### Background & Layout
| Call | Returns | Notes |
|------|---------|-------|
| `make_background()` | VGroup | Dark background, always `self.add(bg)` first |
| `title_bar(label)` | VGroup | Title text + separator line at top |
| `card(label, width=3.0, height=0.95, color=USER, font_size=25)` | VGroup | Rounded card with accent line |
| `code_card(label, width=3.2, height=0.86, color=USER, font_size=22)` | VGroup | Monospace card (for code/formulas) |

### Text
| Call | Returns | Notes |
|------|---------|-------|
| `t(label, size=25, color=TEXT, weight=None)` | Text | Regular text. Use `weight=BOLD` for emphasis |
| `mono(label, size=22, color=TEXT)` | Text | Monospace text |

### Connectors & Effects
| Call | Returns | Notes |
|------|---------|-------|
| `connect(a, b, color=KERNEL)` | Arrow | Arrow from `a` right edge to `b` left edge |
| `glow(mob, color=KERNEL)` | VGroup | Highlight glow around any Mobject |
| `dim(mob)` | animation | Fade mob to ~30% opacity (use inside `play_until`) |
| `undim(mob)` | animation | Restore mob to full opacity |
| `flow_dot(path, color=KERNEL)` | Dot | Animated dot at path start, for `MoveAlongPath` |
| `fade_group(*items)` | VGroup | Groups items for `FadeOut`, skips `None` |

### Colors (dark academic palette)
```
USER     = "#3A86FF"   # blue     — user inputs, user-facing concepts
KERNEL   = "#FFBE0B"   # yellow   — core mechanisms, key ideas
SUCCESS  = "#06D6A0"   # green    — outputs, results, positive states
DANGER   = "#FB5607"   # red      — errors, prohibitions, failures
PURPLE   = "#9B5DE5"   # purple   — secondary concepts, middle steps
HARDWARE = "#6C757D"   # gray     — hardware, infrastructure, neutral
MUTED    = "#8A95A6"   # muted    — labels, annotations
TEXT     = "#ECF1F8"   # white    — body text
EDGE     = "#2A3344"   # dark     — borders, axis lines
PANEL_2  = "#202733"   # dark bg  — fill for shapes
```

### Font size constants
```
H1=42, H2=30, BODY=25, CAP=20, CODE=22
```

### Positioning
```python
ORIGIN, UP, DOWN, LEFT, RIGHT, UL, UR, DL, DR   # direction vectors
mob.move_to(ORIGIN + UP * 0.5)
mob.next_to(other, RIGHT, buff=0.3)
mob.to_edge(UP, buff=0.4)
mob.shift(LEFT * 1.5)
mob.scale(1.1)
```

## Manim Primitives (from `from manim import *`)

### Shapes
```python
RoundedRectangle(width=3, height=1, corner_radius=0.14, color=USER, stroke_width=2)
    .set_fill(PANEL_2, opacity=0.9)
Line(LEFT * 3, RIGHT * 3, color=EDGE, stroke_width=3)
DashedLine(start, end, color=DANGER, stroke_width=3)
Arrow(start, end, buff=0.1, color=KERNEL, stroke_width=3.5, max_tip_length_to_length_ratio=0.14)
ArcBetweenPoints(start, end, angle=-TAU / 6, color=KERNEL, stroke_width=3)
Dot(ORIGIN, radius=0.07, color=USER)
SurroundingRectangle(mob, buff=0.1, corner_radius=0.1, color=KERNEL)
```

### Groups & Arrangement
```python
VGroup(mob1, mob2, mob3)
VGroup(...).arrange(RIGHT, buff=0.3)   # or DOWN, UP, LEFT
VGroup(...).arrange(RIGHT, buff=0.2).move_to(ORIGIN)
```

### Animations
```python
FadeIn(mob, shift=UP * 0.1)          # gentle entrance
FadeOut(mob)                          # exit
Create(mob)                           # draw stroke
Write(mob)                            # write text
Transform(from_mob, to_mob)           # morph one into another
LaggedStart(FadeIn(a), FadeIn(b), FadeIn(c), lag_ratio=0.15)   # staggered entrance
MoveAlongPath(dot, path, rate_func=linear)   # move dot along an Arrow or Line
mob.animate.set_stroke(KERNEL, width=4)      # animate property change
mob.animate.set_opacity(0.3)
mob.animate.scale(1.1)
mob.animate.move_to(new_position)
```

## The Sync Contract (CRITICAL — always follow this)

The `beats` list gives you the `at` ratios. Use them directly in `play_until`:

```python
# beats = [
#   {"at": 0.12, "visual_action": "Reveal two input points on graph"},
#   {"at": 0.35, "visual_action": "Draw vertical delta marker"},
#   {"at": 0.55, "visual_action": "Create secant line through points"},
#   {"at": 0.75, "visual_action": "Show slope values converging"},
#   {"at": 0.88, "visual_action": "Replace secant with tangent line"},
# ]

self.play_until(0.12, FadeIn(point_a), FadeIn(point_b))          # beat 1
self.play_until(0.35, Create(delta_v))                            # beat 2
self.play_until(0.55, Create(secant_line))                        # beat 3
self.play_until(0.75, Transform(slope_text, converging_text))     # beat 4
self.play_until(0.88, Transform(secant_line, tangent_line), FadeIn(summary))  # beat 5
```

Never skip a beat ratio. Never invent `at` values not in the beats list.

## Rules

1. **Build first, animate later** — create all Mobjects before the first `play_until`.
2. **One active idea per beat** — don't pack more than 3 animations in one `play_until`.
3. **Stable positions** — call `.move_to()` once; only move again via `.animate` inside `play_until`.
4. **Use `rate_func=linear`** for movement (`MoveAlongPath`, `animate.move_to`).
5. **Collect everything** — `fade_group(bg, title, all_mobs_you_created)` at the end.
6. **No `self.wait()`** — never call it directly; `finish_sync()` handles remaining time.
7. **No `self.time`** — use `self.now()` only if you truly need the current render time.
8. **Keep it readable** — one variable per Mobject, meaningful names (not `a`, `b`, `c`).
9. **Maximum one `MoveAlongPath` token per scene** — keep animation simple.

## Forbidden (will cause failure)

- `import` statements of any kind
- `open()`, `eval()`, `exec()`, `__import__()`, `compile()`
- `os`, `subprocess`, `sys`, `socket`, `requests`
- `self.wait()` (use `hold_until(ratio)` for pauses, or just let `finish_sync` handle it)
- `self.time` (old Manim API — use `self.now()`)
- Arbitrary Python not related to building or animating Mobjects

## Complete Example

**Scene spec:**
- layout: `process_flow`
- visual_intent: "Show data flowing through three pipeline stages: Parse, Transform, Output"
- beats: `[{at:0.10, action:"Reveal three stage cards"}, {at:0.32, action:"Draw arrows between stages"}, {at:0.52, action:"Token moves from Parse to Transform"}, {at:0.72, action:"Token moves from Transform to Output"}, {at:0.88, action:"Reveal result summary"}]`

**Output:**
```python
def construct(self):
    self.begin_sync()

    bg = make_background()
    title = title_bar("Three-Stage Pipeline")

    stage_parse = card("Parse", width=2.2, color=USER, font_size=22).move_to(LEFT * 4.0 + UP * 0.4)
    stage_transform = card("Transform", width=2.4, color=KERNEL, font_size=22).move_to(ORIGIN + UP * 0.4)
    stage_output = card("Output", width=2.2, color=SUCCESS, font_size=22).move_to(RIGHT * 4.0 + UP * 0.4)

    arrow_pt = connect(stage_parse, stage_transform, USER)
    arrow_to = connect(stage_transform, stage_output, KERNEL)
    token = flow_dot(arrow_pt, KERNEL)

    summary = t("data flows through three stages", 26, TEXT, BOLD).to_edge(DOWN, buff=0.55)

    self.add(bg)
    self.play_until(0.10, FadeIn(title), FadeIn(stage_parse, shift=UP * 0.1), FadeIn(stage_transform, shift=UP * 0.1), FadeIn(stage_output, shift=UP * 0.1))
    self.play_until(0.32, Create(arrow_pt), Create(arrow_to), FadeIn(token))
    self.play_until(0.52, MoveAlongPath(token, arrow_pt), rate_func=linear)
    self.play_until(0.72, MoveAlongPath(token, arrow_to), dim(stage_parse), rate_func=linear)
    self.play_until(0.88, FadeIn(summary), undim(stage_parse))

    self.finish_sync()
    self.play(FadeOut(fade_group(bg, title, stage_parse, stage_transform, stage_output, arrow_pt, arrow_to, token, summary)), run_time=0.7)
```
