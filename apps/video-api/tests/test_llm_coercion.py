from __future__ import annotations

from video_api.pipeline.llm import _coerce_blueprint_shape
from video_api.schemas import VideoBlueprint


def test_coerce_common_llm_schema_variants() -> None:
    data = {
        "title": "Photosynthesis Basics",
        "theme": "biology",
        "slug": "photosynthesis-basics",
        "target_duration_seconds": 90,
        "discipline": "biology",
        "level": "intro",
        "objectives": ["Explain how light energy becomes chemical energy."],
        "audience": "Students learning cell biology.",
        "teaching_goal": "Explain how photosynthesis turns light, water, and carbon dioxide into stored chemical energy.",
        "style_notes": "Dark background with cards, cycles, and arrows.",
        "scenes": [
            {
                "key": "Scene1_HookEN",
                "title": "Hook",
                "narration": "Plants look still, but inside each leaf, light starts a chain of energy transfers. Sunlight is absorbed by pigments, electrons are pushed to higher energy levels, and that captured energy is passed along step by step. Nothing visible moves, yet a steady flow of energy is already running through every chloroplast in the leaf.",
                "visual_description": "Show sunlight, a leaf, chloroplasts, and stored sugar.",
                "scene_type": "cycle_diagram",
                "beats": [
                    {"spoken_idea": "Plants look still", "visual": "Show a leaf."},
                    {"spoken_idea": "light starts", "visual": "Show sunlight entering."},
                    {"spoken_idea": "energy transfers", "visual": "Show arrows through chloroplast stages."},
                ],
            },
            {
                "key": "Scene2_CoreIdeaEN",
                "title": "Core Idea",
                "script": "The light reactions capture energy, and the Calvin cycle uses that energy to build sugar molecules. In the first stage, water is split and energy carriers are charged up. In the second stage, those carriers power a cycle that fixes carbon dioxide into stable sugar. The two stages depend on each other, one supplying energy and the other supplying structure.",
                "visual_plan": "Show light reactions feeding the Calvin cycle.",
                "visual_layout": "process_flow",
                "beats": [
                    {"spoken_idea": "light reactions", "visual_action": "Show light reaction block."},
                    {"spoken_idea": "Calvin cycle", "visual_action": "Show cycle block."},
                    {"spoken_idea": "build sugar", "visual_action": "Show sugar product."},
                ],
            },
            {
                "key": "Scene3_RecapEN",
                "title": "Recap",
                "voiceover": "Photosynthesis connects light capture, carbon fixation, and energy storage in one system. Light is harvested, carbon is pulled from the air, and the result is chemical energy locked inside sugar. That stored energy then feeds the plant and, eventually, almost every other living thing that depends on it.",
                "visual": "Show final three-step recap.",
                "beats": [
                    {"spoken_idea": "light capture", "action": "Show light capture."},
                    {"spoken_idea": "carbon fixation", "action": "Show carbon fixation."},
                    {"spoken_idea": "energy storage", "action": "Show storage."},
                ],
            },
        ],
    }

    blueprint = VideoBlueprint.model_validate(_coerce_blueprint_shape(data))

    assert blueprint.subject_area == "biology"
    assert blueprint.difficulty == "intro"
    assert blueprint.learning_objectives == ["Explain how light energy becomes chemical energy."]
    assert blueprint.scenes[0].text.startswith("Plants look")
    assert blueprint.scenes[0].visual_intent.startswith("Show sunlight")
    assert blueprint.scenes[0].layout == "cycle_diagram"
    assert blueprint.scenes[0].beats[-1].at >= 0.75


def test_coerce_legacy_kernel_layouts_to_generic_primitives() -> None:
    data = {
        "title": "Legacy Layouts",
        "theme": "cs",
        "slug": "legacy-layouts",
        "target_duration_seconds": 90,
        "audience": "Students.",
        "teaching_goal": "Explain compatibility mapping from older visual layouts.",
        "style_notes": "Use neutral visual primitives.",
        "scenes": [
            {
                "key": "Scene1_HookEN",
                "title": "Hook",
                "layout": "memory_translation",
                "text": "This scene has enough narration to validate while preserving an older layout name. The point of the test is that an outdated layout label is still accepted and quietly mapped onto a current visual primitive. We keep the spoken text long enough here so the blueprint clears the narration budget for its target duration as well.",
                "visual_intent": "Show an old layout mapped to a spatial model.",
                "beats": [
                    {"key": "aa", "at": 0.1, "text_hint": "first", "visual_action": "Show first."},
                    {"key": "bb", "at": 0.5, "text_hint": "second", "visual_action": "Show second."},
                    {"key": "cc", "at": 0.88, "text_hint": "third", "visual_action": "Show third."},
                ],
            },
            {
                "key": "Scene2_CoreIdeaEN",
                "title": "Core",
                "layout": "scheduler_timeline",
                "text": "This scene has enough narration to validate while preserving another older layout name. A legacy timeline label should resolve to the generic timeline primitive without any manual intervention. Again we keep the narration long enough to satisfy the duration budget so the coercion behaviour is what the assertion actually checks.",
                "visual_intent": "Show an old timeline layout mapped to a timeline primitive.",
                "beats": [
                    {"key": "aa", "at": 0.1, "text_hint": "first", "visual_action": "Show first."},
                    {"key": "bb", "at": 0.5, "text_hint": "second", "visual_action": "Show second."},
                    {"key": "cc", "at": 0.88, "text_hint": "third", "visual_action": "Show third."},
                ],
            },
            {
                "key": "Scene3_RecapEN",
                "title": "Recap",
                "layout": "syscall_gate",
                "text": "This scene has enough narration to validate while preserving a final older layout name. An older gate-style label should be mapped onto the process flow primitive that replaces it. The narration is deliberately padded so the whole blueprint clears its narration budget and the test stays focused on layout mapping.",
                "visual_intent": "Show an old gate layout mapped to a process flow primitive.",
                "beats": [
                    {"key": "aa", "at": 0.1, "text_hint": "first", "visual_action": "Show first."},
                    {"key": "bb", "at": 0.5, "text_hint": "second", "visual_action": "Show second."},
                    {"key": "cc", "at": 0.88, "text_hint": "third", "visual_action": "Show third."},
                ],
            },
        ],
    }

    blueprint = VideoBlueprint.model_validate(_coerce_blueprint_shape(data))

    assert [scene.layout for scene in blueprint.scenes] == ["spatial_model", "timeline", "process_flow"]


def test_coerce_absolute_beat_timestamps_to_scene_ratios() -> None:
    data = {
        "title": "Newton Second Law",
        "theme": "physics",
        "slug": "newton-second-law",
        "target_duration_seconds": 90,
        "subject_area": "physics",
        "audience": "Students learning introductory mechanics.",
        "teaching_goal": "Explain how net force, mass, and acceleration connect.",
        "style_notes": "Dark background with clear vectors, equations, and motion diagrams.",
        "scenes": [
            {
                "key": "Scene1_HookEN",
                "title": "Hook",
                "layout": "concept_map",
                "text": "A moving cart changes speed only when the forces on it do not balance out. If you push it and friction pushes back with the same strength, the cart simply keeps its current motion. The interesting moment is when one side wins, because that leftover, unbalanced force is what we call the net force on the cart.",
                "visual_intent": "Show a cart, force arrows, and the idea of net force.",
                "beats": [
                    {"key": "cart", "at": 0.0, "text_hint": "moving cart", "visual_action": "Show cart."},
                    {"key": "forces", "at": 2.5, "text_hint": "forces", "visual_action": "Show force arrows."},
                    {"key": "net", "at": 5.0, "text_hint": "do not balance", "visual_action": "Show net force."},
                ],
            },
            {
                "key": "Scene2_PathEN",
                "title": "Path",
                "layout": "equation_transform",
                "text": "Newton's second law says net force equals mass times acceleration, so acceleration grows with force and shrinks with mass. Double the net force on the same cart and it accelerates twice as hard. Keep the force fixed but double the mass and the same push produces only half the acceleration, which is why heavy objects feel sluggish.",
                "visual_intent": "Transform the verbal relationship into F equals m times a.",
                "beats": [
                    {"key": "force", "at": 7.5, "text_hint": "net force", "visual_action": "Highlight force."},
                    {"key": "mass", "at": 10.0, "text_hint": "mass", "visual_action": "Highlight mass."},
                    {"key": "accel", "at": 12.5, "text_hint": "acceleration", "visual_action": "Highlight acceleration."},
                    {"key": "relation", "at": 15.0, "text_hint": "grows with force", "visual_action": "Show proportional relation."},
                ],
            },
            {
                "key": "Scene3_RecapEN",
                "title": "Recap",
                "layout": "recap_map",
                "text": "The key model is simple: combine the forces, compare that net force with the mass, and the result is acceleration. First add every force as a vector to find the net push. Then divide that net force by the mass, and the number you get is exactly how quickly the object speeds up or slows down.",
                "visual_intent": "Summarize force combination, mass comparison, and acceleration result.",
                "beats": [
                    {"key": "combine", "at": 17.5, "text_hint": "combine the forces", "visual_action": "Show combined vector."},
                    {"key": "compare", "at": 20.0, "text_hint": "compare with mass", "visual_action": "Show mass relation."},
                    {"key": "result", "at": 22.5, "text_hint": "result is acceleration", "visual_action": "Show acceleration arrow."},
                ],
            },
        ],
    }

    blueprint = VideoBlueprint.model_validate(_coerce_blueprint_shape(data))

    assert [beat.at for beat in blueprint.scenes[0].beats] == [0.12, 0.5, 0.88]
    assert [beat.at for beat in blueprint.scenes[1].beats] == [0.12, 0.373, 0.627, 0.88]
    assert all(0 <= beat.at <= 1 for scene in blueprint.scenes for beat in scene.beats)
