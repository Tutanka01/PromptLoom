from __future__ import annotations

from video_api.pipeline.llm import _coerce_blueprint_shape
from video_api.schemas import VideoBlueprint


def test_coerce_common_llm_schema_variants() -> None:
    data = {
        "title": "Linux Page Tables",
        "theme": "linux-fondamentaux",
        "slug": "linux-page-tables",
        "target_duration_seconds": 90,
        "audience": "Developers learning Linux memory management.",
        "teaching_goal": "Explain virtual to physical memory translation.",
        "style_notes": "Dark background with cards and arrows.",
        "scenes": [
            {
                "key": "Scene1_HookEN",
                "title": "Hook",
                "narration": "Every program sees its own memory, but physical RAM is shared by the whole machine.",
                "visual_description": "Show applications, page tables, and RAM.",
                "beats": [
                    {"spoken_idea": "Every program sees memory", "visual": "Show app address space."},
                    {"spoken_idea": "RAM is shared", "visual": "Show shared RAM."},
                    {"spoken_idea": "Page tables translate", "visual": "Show page table translation."},
                ],
            },
            {
                "key": "Scene2_CoreIdeaEN",
                "title": "Core Idea",
                "script": "The CPU asks the MMU to translate each virtual address into a physical frame.",
                "visual_plan": "Show CPU to MMU to RAM.",
                "beats": [
                    {"spoken_idea": "CPU asks", "visual_action": "Show CPU request."},
                    {"spoken_idea": "MMU translates", "visual_action": "Show MMU lookup."},
                    {"spoken_idea": "physical frame", "visual_action": "Show RAM frame."},
                ],
            },
            {
                "key": "Scene3_RecapEN",
                "title": "Recap",
                "voiceover": "Programs use virtual addresses, the MMU checks page tables, and RAM receives physical accesses.",
                "visual": "Show final three-step recap.",
                "beats": [
                    {"spoken_idea": "virtual addresses", "action": "Show virtual."},
                    {"spoken_idea": "page tables", "action": "Show table."},
                    {"spoken_idea": "physical accesses", "action": "Show RAM."},
                ],
            },
        ],
    }

    blueprint = VideoBlueprint.model_validate(_coerce_blueprint_shape(data))

    assert blueprint.scenes[0].text.startswith("Every program")
    assert blueprint.scenes[0].visual_intent.startswith("Show applications")
    assert blueprint.scenes[0].beats[-1].at >= 0.75


def test_coerce_absolute_beat_timestamps_to_scene_ratios() -> None:
    data = {
        "title": "Linux Syscalls",
        "theme": "linux-fondamentaux",
        "slug": "linux-syscalls",
        "target_duration_seconds": 90,
        "audience": "Developers learning Linux internals.",
        "teaching_goal": "Explain how syscalls cross into the kernel.",
        "style_notes": "Dark background with clear user kernel boundary visuals.",
        "scenes": [
            {
                "key": "Scene1_HookEN",
                "title": "Hook",
                "text": "A command looks direct, but it crosses a controlled kernel boundary to do protected work.",
                "visual_intent": "Show the command crossing into the kernel through a gate.",
                "beats": [
                    {"key": "command", "at": 0.0, "text_hint": "A command", "visual_action": "Show terminal."},
                    {"key": "gate", "at": 2.5, "text_hint": "controlled boundary", "visual_action": "Show gate."},
                    {"key": "kernel", "at": 5.0, "text_hint": "kernel work", "visual_action": "Show kernel."},
                ],
            },
            {
                "key": "Scene2_PathEN",
                "title": "Path",
                "text": "The wrapper loads a syscall number, the CPU enters the kernel, and the handler validates the request.",
                "visual_intent": "Show wrapper, CPU entry, dispatch table, and validation.",
                "beats": [
                    {"key": "wrapper", "at": 7.5, "text_hint": "wrapper", "visual_action": "Show wrapper."},
                    {"key": "entry", "at": 10.0, "text_hint": "CPU enters", "visual_action": "Show CPU entry."},
                    {"key": "table", "at": 12.5, "text_hint": "dispatch table", "visual_action": "Show table."},
                    {"key": "validate", "at": 15.0, "text_hint": "validates", "visual_action": "Show checks."},
                ],
            },
            {
                "key": "Scene3_RecapEN",
                "title": "Recap",
                "text": "Syscalls are the public doorway where user programs ask and the kernel decides.",
                "visual_intent": "Summarize user asks, kernel decides, result returns.",
                "beats": [
                    {"key": "ask", "at": 17.5, "text_hint": "programs ask", "visual_action": "Show ask."},
                    {"key": "decide", "at": 20.0, "text_hint": "kernel decides", "visual_action": "Show kernel."},
                    {"key": "return", "at": 22.5, "text_hint": "result returns", "visual_action": "Show return."},
                ],
            },
        ],
    }

    blueprint = VideoBlueprint.model_validate(_coerce_blueprint_shape(data))

    assert [beat.at for beat in blueprint.scenes[0].beats] == [0.12, 0.5, 0.88]
    assert [beat.at for beat in blueprint.scenes[1].beats] == [0.12, 0.373, 0.627, 0.88]
    assert all(0 <= beat.at <= 1 for scene in blueprint.scenes for beat in scene.beats)
