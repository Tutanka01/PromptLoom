# Manim Generation Guidelines

This step produces a structured **blueprint** (what to teach, scene by scene, with narration
and synced beats). A separate authoring step then writes real, bespoke Manim code for each
scene from that blueprint, following `manim-skill.md`. If a generated scene fails, the worker
falls back to a deterministic template for that scene only.

So plan for variety: each scene should look designed for its own idea (a LaTeX equation that
transforms, a function plotted on axes, a labelled diagram, a code block, a data table) — not
the same row of cards every time.

## Duration

- Default target duration is 240 seconds.
- A default video must be treated as a 3-5 minute educational piece, not a short demo.
- For a 180-300 second target, use 8-12 scenes.
- Each scene should carry enough narration for roughly 20-40 seconds.

## Composition hint (`layout`)

Each scene picks one `layout` value as a *suggested* composition family — it guides the
authoring step but does not lock the visuals:

- `concept_map`
- `process_flow`
- `layered_system`
- `timeline`
- `equation_transform`
- `graph_plot`
- `comparison_table`
- `cycle_diagram`
- `spatial_model`
- `recap_map`

Pick the closest fit, then describe concrete visual actions for the beats. The authoring step
turns the scene into real Manim (LaTeX, axes, code, diagrams) guided by these hints.

## Beat Quality

Good beats map a spoken idea to a screen change:

- "Shrink the interval between two points until the secant line becomes a tangent."
- "Transform the average-rate expression into a limit expression."
- "Move focus from light capture, to carbon fixation, to energy storage."

Bad beats are too vague:

- "Make it nicer."
- "Show something."
- "Add more animation."

## Manim Principles

Use Manim as a precise animation system:

- compose scenes from explicit Mobjects;
- use stable positioning and relative layout;
- animate changes with `FadeIn`, `Create`, `Transform`, movement, and `.animate`;
- use focus/dim to guide attention;
- avoid static screens that only contain text cards.

References:

- https://docs.manim.community/en/stable/tutorials/quickstart.html
- https://docs.manim.community/en/stable/reference_index/animations.html
- https://docs.manim.community/en/stable/reference/manim.animation.updaters.html
