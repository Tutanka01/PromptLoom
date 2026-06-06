# Manim Generation Guidelines

This API does not ask the LLM to write raw Manim Python.

The LLM produces a structured blueprint. The worker turns that blueprint into deterministic Manim scenes from an approved visual grammar.

## Duration

- Default target duration is 240 seconds.
- A default video must be treated as a 3-5 minute educational piece, not a short demo.
- For a 180-300 second target, use 8-12 scenes.
- Each scene should carry enough narration for roughly 20-40 seconds.

## Visual Grammar

Approved layouts:

- `process_pipeline`
- `privilege_boundary`
- `memory_translation`
- `scheduler_timeline`
- `syscall_gate`
- `cpu_registers`
- `hardware_path`
- `recap_map`

The LLM must choose one layout per scene and describe concrete visual actions for the beats. The worker owns the Python implementation.

## Beat Quality

Good beats map a spoken idea to a screen change:

- "Animate a direct jump from user mode and block it at the privilege boundary."
- "Move the virtual address through the MMU and reveal the page-table entry."
- "Advance the scheduler timeline and switch the CPU lane from task A to task B."

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
