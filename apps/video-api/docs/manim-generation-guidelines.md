# Manim Generation Guidelines

This API does not ask the LLM to write raw Manim Python.

The LLM produces a structured blueprint. The worker turns that blueprint into deterministic Manim scenes from an approved visual grammar.

## Duration

- Default target duration is 240 seconds.
- A default video must be treated as a 3-5 minute educational piece, not a short demo.
- For a 180-300 second target, use 8-12 scenes.
- Each scene should carry enough narration for roughly 20-40 seconds.

## Visual Grammar

Approved visual primitives:

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

The LLM must choose one visual primitive per scene and describe concrete visual actions for the beats. The worker owns the Python implementation.

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
